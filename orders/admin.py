from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("produto",)
    fields = ("produto", "quantidade", "preco_unitario", "subtotal")
    readonly_fields = ("subtotal",)

    def subtotal(self, obj: OrderItem) -> str:
        if obj.pk is None:
            return "-"
        return f"R$ {obj.subtotal}"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "status", "valor_total", "data_criacao")
    list_filter = ("status", "data_criacao")
    search_fields = ("id", "usuario__username")
    date_hierarchy = "data_criacao"
    inlines = [OrderItemInline]
    actions = ["marcar_como_pago"]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related("usuario")

    @admin.action(description="Marcar como Pago")
    def marcar_como_pago(self, request: HttpRequest, queryset: QuerySet) -> None:
        updated = queryset.update(status=Order.Status.PAGO)
        self.message_user(request, f"{updated} pedido(s) marcado(s) como Pago.")
