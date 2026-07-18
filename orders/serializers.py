from rest_framework import serializers

from .models import Order, OrderItem


class OrderItemInputSerializer(serializers.Serializer):
    """One line of an incoming order: a product reference plus a quantity."""

    produto = serializers.IntegerField(required=False, min_value=1)
    sku = serializers.CharField(required=False)
    quantidade = serializers.IntegerField(min_value=1)

    def validate(self, attrs: dict) -> dict:
        if attrs.get("produto") is None and not attrs.get("sku"):
            raise serializers.ValidationError(
                "Informe 'produto' (id) ou 'sku' para cada item."
            )
        return attrs


class OrderCreateSerializer(serializers.Serializer):
    """Payload for ``POST /api/v1/pedidos/``: a non-empty list of items."""

    itens = OrderItemInputSerializer(many=True, allow_empty=False)

    def to_service_items(self) -> list[dict]:
        """Translate validated payload into ``create_order`` item dicts."""
        items: list[dict] = []
        for item in self.validated_data["itens"]:
            items.append(
                {
                    "product_id": item.get("produto"),
                    "sku": item.get("sku"),
                    "quantity": item["quantidade"],
                }
            )
        return items


class OrderItemSerializer(serializers.ModelSerializer):
    produto = serializers.IntegerField(source="produto_id", read_only=True)
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "produto",
            "produto_nome",
            "quantidade",
            "preco_unitario",
            "subtotal",
        ]


class OrderSerializer(serializers.ModelSerializer):
    itens = OrderItemSerializer(many=True, read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "valor_total", "data_criacao", "itens"]
