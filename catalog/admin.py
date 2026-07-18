from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Category, Product


class StockStatusFilter(admin.SimpleListFilter):
    """Custom filter to segment products by stock availability."""

    title = "status de estoque"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return [("in", "Em estoque"), ("out", "Esgotado")]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == "in":
            return queryset.filter(quantidade_estoque__gt=0)
        if self.value() == "out":
            return queryset.filter(quantidade_estoque=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sku",
        "categoria",
        "preco",
        "quantidade_estoque",
        "ativo",
    )
    list_filter = ("categoria", StockStatusFilter, "ativo")
    search_fields = ("nome", "sku")
    list_select_related = ("categoria",)
    prepopulated_fields = {"slug": ("nome",)}
