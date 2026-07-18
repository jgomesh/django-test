from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions

from .filters import ProductFilter
from .models import Product
from .serializers import ProductSerializer


class ProductListAPIView(generics.ListAPIView):
    """Public, paginated product list, filterable by category.

    ``select_related('categoria')`` avoids the N+1 query that would otherwise
    fire once per product when serializing the nested category.
    """

    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProductFilter

    def get_queryset(self):
        return (
            Product.objects.filter(ativo=True)
            .select_related("categoria")
            .order_by("nome")
        )
