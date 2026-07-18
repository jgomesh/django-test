import django_filters

from .models import Product


class ProductFilter(django_filters.FilterSet):
    """Filter products by category (accepts either the category id or slug).

    Uses django-filter's declarative FilterSet so user-supplied values are
    always bound as query parameters -- never string-interpolated into SQL.
    """

    categoria = django_filters.NumberFilter(field_name="categoria_id")
    categoria_slug = django_filters.CharFilter(
        field_name="categoria__slug", lookup_expr="exact"
    )

    class Meta:
        model = Product
        fields = ["categoria", "categoria_slug"]
