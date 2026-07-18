from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from catalog.models import Category, Product

User = get_user_model()


def make_products(category: Category, count: int, prefix: str) -> None:
    for i in range(count):
        Product.objects.create(
            nome=f"{prefix} {i}",
            sku=f"{prefix}-{i}",
            slug=f"{prefix}-{i}".lower(),
            preco=Decimal("10.00"),
            quantidade_estoque=5,
            categoria=category,
        )


class ProductListAPITests(APITestCase):
    def setUp(self):
        self.eletronicos = Category.objects.create(
            nome="Eletrônicos", slug="eletronicos"
        )
        self.livros = Category.objects.create(nome="Livros", slug="livros")
        self.url = reverse("catalog:product-list")

    def test_list_is_public(self):
        make_products(self.eletronicos, 3, "ELE")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

    def test_inactive_products_excluded(self):
        make_products(self.eletronicos, 1, "ELE")
        Product.objects.create(
            nome="Inativo",
            sku="INA-1",
            slug="ina-1",
            preco=Decimal("5.00"),
            quantidade_estoque=1,
            categoria=self.eletronicos,
            ativo=False,
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)

    def test_pagination_page_size(self):
        make_products(self.eletronicos, 15, "ELE")
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 15)
        self.assertEqual(len(resp.data["results"]), 10)  # PAGE_SIZE
        self.assertIsNotNone(resp.data["next"])

    def test_filter_by_categoria_id(self):
        make_products(self.eletronicos, 2, "ELE")
        make_products(self.livros, 3, "LIV")
        resp = self.client.get(self.url, {"categoria": self.livros.id})
        self.assertEqual(resp.data["count"], 3)

    def test_filter_by_categoria_slug(self):
        make_products(self.eletronicos, 2, "ELE")
        make_products(self.livros, 3, "LIV")
        resp = self.client.get(self.url, {"categoria_slug": "eletronicos"})
        self.assertEqual(resp.data["count"], 2)

    def test_no_n_plus_one_queries(self):
        """Query count must not grow with the number of products."""
        make_products(self.eletronicos, 3, "ELE")
        with CaptureQueriesContext(connection) as ctx_small:
            self.client.get(self.url)
        small = len(ctx_small.captured_queries)

        make_products(self.eletronicos, 6, "MORE")  # 9 total, still one page
        with CaptureQueriesContext(connection) as ctx_big:
            self.client.get(self.url)
        big = len(ctx_big.captured_queries)

        self.assertEqual(small, big)


class ProductAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@example.com", "pw")
        self.client.force_login(self.admin)
        self.category = Category.objects.create(nome="Cat", slug="cat")
        # Distinctive names that do NOT collide with the filter sidebar labels
        # ("Em estoque" / "Esgotado").
        self.in_stock = Product.objects.create(
            nome="ProdutoAlpha",
            sku="IN-1",
            slug="in-1",
            preco=Decimal("10.00"),
            quantidade_estoque=5,
            categoria=self.category,
        )
        self.out_stock = Product.objects.create(
            nome="ProdutoBeta",
            sku="OUT-1",
            slug="out-1",
            preco=Decimal("10.00"),
            quantidade_estoque=0,
            categoria=self.category,
        )

    def test_stock_filter_in_stock(self):
        url = reverse("admin:catalog_product_changelist")
        resp = self.client.get(url, {"stock_status": "in"})
        self.assertContains(resp, "ProdutoAlpha")
        self.assertNotContains(resp, "ProdutoBeta")

    def test_stock_filter_out_of_stock(self):
        url = reverse("admin:catalog_product_changelist")
        resp = self.client.get(url, {"stock_status": "out"})
        self.assertContains(resp, "ProdutoBeta")
        self.assertNotContains(resp, "ProdutoAlpha")

    def test_search_by_sku(self):
        url = reverse("admin:catalog_product_changelist")
        resp = self.client.get(url, {"q": "IN-1"})
        self.assertContains(resp, "ProdutoAlpha")
        self.assertNotContains(resp, "ProdutoBeta")
