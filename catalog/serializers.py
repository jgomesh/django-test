from rest_framework import serializers

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "nome", "slug", "descricao"]


class ProductSerializer(serializers.ModelSerializer):
    categoria = CategorySerializer(read_only=True)
    em_estoque = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "nome",
            "sku",
            "slug",
            "preco",
            "quantidade_estoque",
            "em_estoque",
            "imagem",
            "categoria",
            "ativo",
        ]
