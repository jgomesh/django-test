from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from orders.models import Order

User = get_user_model()


class StorefrontViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(nome="Cat", slug="cat")
        self.product = Product.objects.create(
            nome="Fone",
            sku="F-1",
            slug="fone",
            preco=Decimal("99.90"),
            quantidade_estoque=3,
            categoria=self.category,
        )
        self.user = User.objects.create_user("shopper", password="pw12345")

    def test_home_renders(self):
        resp = self.client.get(reverse("storefront:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Fone")
        self.assertContains(resp, "Cat")

    def test_home_filters_by_categoria(self):
        outra = Category.objects.create(nome="Outra", slug="outra")
        Product.objects.create(
            nome="Caneca",
            sku="C-1",
            slug="caneca",
            preco=Decimal("20.00"),
            quantidade_estoque=1,
            categoria=outra,
        )
        resp = self.client.get(reverse("storefront:home"), {"categoria": "cat"})
        self.assertContains(resp, "Fone")
        self.assertNotContains(resp, "Caneca")

    def test_home_search_by_query(self):
        resp = self.client.get(reverse("storefront:home"), {"q": "fon"})
        self.assertContains(resp, "Fone")

    def test_product_detail_renders(self):
        resp = self.client.get(reverse("storefront:product_detail", args=["fone"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Fone")

    def test_product_detail_404_for_inactive(self):
        self.product.ativo = False
        self.product.save()
        resp = self.client.get(reverse("storefront:product_detail", args=["fone"]))
        self.assertEqual(resp.status_code, 404)

    def test_comprar_requires_login(self):
        resp = self.client.post(reverse("storefront:comprar", args=["fone"]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/entrar/", resp.url)
        self.assertEqual(Order.objects.count(), 0)

    def test_comprar_get_not_allowed(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("storefront:comprar", args=["fone"]))
        self.assertEqual(resp.status_code, 405)

    def test_comprar_creates_order(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("storefront:comprar", args=["fone"]), follow=True
        )
        self.assertEqual(resp.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.usuario, self.user)
        self.assertEqual(order.valor_total, Decimal("99.90"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantidade_estoque, 2)
        self.assertContains(resp, "criado com sucesso")

    def test_comprar_out_of_stock_shows_error(self):
        self.product.quantidade_estoque = 0
        self.product.save()
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("storefront:comprar", args=["fone"]), follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(resp, "Estoque insuficiente")

    def test_login_page_renders(self):
        resp = self.client.get(reverse("storefront:login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Entrar")

    def test_login_and_logout_flow(self):
        resp = self.client.post(
            reverse("storefront:login"),
            {"username": "shopper", "password": "pw12345"},
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(reverse("storefront:logout"))
        self.assertEqual(resp.status_code, 302)


class CarrinhoTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(nome="Cat", slug="cat")
        self.p1 = Product.objects.create(
            nome="Fone",
            sku="F-1",
            slug="fone",
            preco=Decimal("99.90"),
            quantidade_estoque=5,
            categoria=self.category,
        )
        self.p2 = Product.objects.create(
            nome="Mouse",
            sku="M-1",
            slug="mouse",
            preco=Decimal("50.00"),
            quantidade_estoque=5,
            categoria=self.category,
        )
        self.user = User.objects.create_user("shopper", password="pw12345")
        self.client.force_login(self.user)

    def test_adicionar_ao_carrinho_requires_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/entrar/", resp.url)

    def test_adicionar_ao_carrinho(self):
        resp = self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 2},
            follow=True,
        )
        self.assertContains(resp, "Fone")
        self.assertContains(resp, "R$ 199,80")  # 2 x 99.90

    def test_adicionar_ao_carrinho_accumulates_quantity(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 2},
        )
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 3},
        )
        resp = self.client.get(reverse("storefront:carrinho"))
        self.assertContains(resp, "R$ 499,50")  # 5 x 99.90

    def test_carrinho_header_badge_shows_item_count(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 2},
        )
        resp = self.client.get(reverse("storefront:home"))
        self.assertEqual(resp.context["cart_count"], 2)

    def test_atualizar_item_carrinho(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 1},
        )
        self.client.post(
            reverse("storefront:atualizar_item_carrinho", args=[self.p1.id]),
            {"quantidade": 4},
        )
        resp = self.client.get(reverse("storefront:carrinho"))
        self.assertContains(resp, "R$ 399,60")  # 4 x 99.90

    def test_atualizar_item_carrinho_to_zero_removes_it(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 1},
        )
        self.client.post(
            reverse("storefront:atualizar_item_carrinho", args=[self.p1.id]),
            {"quantidade": 0},
        )
        resp = self.client.get(reverse("storefront:carrinho"))
        self.assertContains(resp, "carrinho está vazio")

    def test_remover_do_carrinho(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 1},
        )
        self.client.post(reverse("storefront:remover_do_carrinho", args=[self.p1.id]))
        resp = self.client.get(reverse("storefront:carrinho"))
        self.assertContains(resp, "carrinho está vazio")

    def test_finalizar_compra_creates_single_order_with_multiple_items(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 2},
        )
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["mouse"]),
            {"quantidade": 3},
        )
        resp = self.client.post(reverse("storefront:finalizar_compra"), follow=True)
        order = Order.objects.get()
        self.assertEqual(order.usuario, self.user)
        self.assertEqual(order.itens.count(), 2)
        self.assertEqual(order.valor_total, Decimal("349.80"))  # 199.80 + 150.00

        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.quantidade_estoque, 3)
        self.assertEqual(self.p2.quantidade_estoque, 2)

        self.assertRedirects(resp, reverse("storefront:home"))
        self.assertContains(resp, "criado com sucesso")

        # Cart is cleared after a successful checkout.
        resp = self.client.get(reverse("storefront:carrinho"))
        self.assertContains(resp, "carrinho está vazio")

    def test_finalizar_compra_empty_cart_shows_error(self):
        resp = self.client.post(reverse("storefront:finalizar_compra"), follow=True)
        self.assertContains(resp, "carrinho está vazio")
        self.assertEqual(Order.objects.count(), 0)

    def test_finalizar_compra_insufficient_stock_rolls_back_whole_order(self):
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["fone"]),
            {"quantidade": 2},
        )
        self.client.post(
            reverse("storefront:adicionar_ao_carrinho", args=["mouse"]),
            {"quantidade": 999},
        )
        resp = self.client.post(reverse("storefront:finalizar_compra"), follow=True)
        self.assertContains(resp, "Estoque insuficiente")
        self.assertEqual(Order.objects.count(), 0)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.quantidade_estoque, 5)  # untouched, all-or-nothing
