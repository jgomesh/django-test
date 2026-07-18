from decimal import Decimal

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("produto",)
    fields = ("produto", "quantidade", "preco_unitario_exibido", "subtotal")
    readonly_fields = ("preco_unitario_exibido", "subtotal")

    @admin.display(description="preço unitário")
    def preco_unitario_exibido(self, obj: OrderItem) -> str:
        if obj.pk is None:
            return "-"
        return f"R$ {obj.preco_unitario}"

    def subtotal(self, obj: OrderItem) -> str:
        if obj.pk is None:
            return "-"
        return f"R$ {obj.subtotal}"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "status", "valor_total_exibido", "data_criacao")
    list_filter = ("status", "data_criacao")
    search_fields = ("id", "usuario__username")
    date_hierarchy = "data_criacao"
    fields = ("usuario", "status", "valor_total_exibido", "data_criacao")
    readonly_fields = ("valor_total_exibido", "data_criacao")
    inlines = [OrderItemInline]
    actions = ["marcar_como_pago"]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related("usuario")

    def save_formset(self, request: HttpRequest, form, formset, change: bool) -> None:
        """New OrderItems get the product's *current registered price* --
        ``preco_unitario`` isn't in the inline form at all (it's readonly), so
        without this it would fail the NOT NULL constraint. Existing items
        keep their frozen historical price untouched.

        Also re-syncs the stored ``Order.valor_total`` from the real items
        afterwards. An order created/edited straight from the admin bypasses
        ``orders.services.create_order`` (which is what normally keeps that
        field correct), so without this it would silently save as 0.00 --
        wrong everywhere else that reads the *stored* field (the API,
        storefront "meus pedidos"), even though the admin's own display
        recomputes it live and would have masked the problem here.
        """
        if formset.model is not OrderItem:
            formset.save()
            return

        instances = formset.save(commit=False)
        for obj in instances:
            if obj.pk is None:
                obj.preco_unitario = obj.produto.preco
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

        order = form.instance
        order.valor_total = sum(
            (item.subtotal for item in order.itens.all()), Decimal("0.00")
        )
        order.save(update_fields=["valor_total"])

    @admin.display(description="valor total")
    def valor_total_exibido(self, obj: Order | None) -> str:
        """Always the live sum of the order's items -- never a free-typed input.

        This is deliberately NOT the stored ``Order.valor_total`` field, so it
        stays correct on this page even before the first save_formset run
        (e.g. rendering right after an add) syncs the stored field.
        """
        if obj is None or obj.pk is None:
            return "-"
        total = sum((item.subtotal for item in obj.itens.all()), Decimal("0.00"))
        return f"R$ {total}"

    @admin.action(description="Marcar como Pago")
    def marcar_como_pago(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(status=Order.Status.PAGO)
        self.message_user(request, f"{updated} pedido(s) marcado(s) como Pago.")
