from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Category, Product
from orders.services import OrderError, create_order


def home(request: HttpRequest) -> HttpResponse:
    """Landing page: active products, filterable by category tab and search.

    ``select_related("categoria")`` avoids an N+1 when the template reads
    ``produto.categoria`` (e.g. for the stock/category badges).
    """
    categoria_slug = request.GET.get("categoria", "").strip()
    query = request.GET.get("q", "").strip()

    produtos = (
        Product.objects.filter(ativo=True).select_related("categoria").order_by("nome")
    )
    if categoria_slug:
        produtos = produtos.filter(categoria__slug=categoria_slug)
    if query:
        produtos = produtos.filter(nome__icontains=query)

    categorias = Category.objects.order_by("nome")
    return render(
        request,
        "storefront/home.html",
        {
            "categorias": categorias,
            "produtos": produtos,
            "categoria_selecionada": categoria_slug,
            "query": query,
        },
    )


def product_detail(request: HttpRequest, slug: str) -> HttpResponse:
    produto = get_object_or_404(
        Product.objects.select_related("categoria"), slug=slug, ativo=True
    )
    return render(request, "storefront/product_detail.html", {"produto": produto})


@require_POST
@login_required
def comprar(request: HttpRequest, slug: str) -> HttpResponse:
    """Handle the "Comprar" button: create a 1-unit order for the product.

    Delegates to the shared ``create_order`` service so stock consistency is
    identical to the API path.
    """
    produto = get_object_or_404(Product, slug=slug, ativo=True)
    try:
        order = create_order(request.user, [{"product_id": produto.id, "quantity": 1}])
    except OrderError as exc:
        messages.error(request, str(exc))
        return redirect("storefront:product_detail", slug=slug)

    messages.success(
        request,
        f"Pedido #{order.pk} criado com sucesso! Total: R$ {order.valor_total}.",
    )
    return redirect("storefront:product_detail", slug=slug)
