import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import OperationalError, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Category, Product
from orders.models import Order, OrderItem
from orders.services import (
    InsufficientStockError,
    InvalidOrderError,
    ProductNotFoundError,
    create_order,
)

User = get_user_model()


def make_product(**kwargs) -> Product:
    category = kwargs.pop("categoria", None) or Category.objects.create(
        nome="Cat", slug=f"cat-{Category.objects.count()}"
    )
    defaults = {
        "nome": "Produto",
        "sku": f"SKU-{Product.objects.count()}",
        "slug": f"produto-{Product.objects.count()}",
        "preco": Decimal("10.00"),
        "quantidade_estoque": 5,
        "categoria": category,
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


class CreateOrderServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="x")
        self.category = Category.objects.create(nome="Cat", slug="cat")

    def test_successful_order_decrements_stock_and_snapshots_price(self):
        p = make_product(
            categoria=self.category,
            preco=Decimal("25.00"),
            quantidade_estoque=10,
            sku="A1",
            slug="a1",
        )
        order = create_order(self.user, [{"product_id": p.id, "quantity": 3}])

        p.refresh_from_db()
        self.assertEqual(p.quantidade_estoque, 7)
        self.assertEqual(order.usuario, self.user)
        self.assertEqual(order.valor_total, Decimal("75.00"))
        item = order.itens.get()
        self.assertEqual(item.quantidade, 3)
        self.assertEqual(item.preco_unitario, Decimal("25.00"))

    def test_price_snapshot_is_frozen_after_product_price_change(self):
        p = make_product(
            categoria=self.category,
            preco=Decimal("50.00"),
            sku="A2",
            slug="a2",
        )
        order = create_order(self.user, [{"product_id": p.id, "quantity": 1}])
        p.preco = Decimal("999.00")
        p.save()
        self.assertEqual(order.itens.get().preco_unitario, Decimal("50.00"))

    def test_order_by_sku(self):
        p = make_product(
            categoria=self.category,
            sku="SKU-XYZ",
            slug="xyz",
            quantidade_estoque=4,
        )
        order = create_order(self.user, [{"sku": "SKU-XYZ", "quantity": 2}])
        p.refresh_from_db()
        self.assertEqual(p.quantidade_estoque, 2)
        self.assertEqual(order.itens.get().produto_id, p.id)

    def test_insufficient_stock_raises_and_rolls_back(self):
        p = make_product(
            categoria=self.category, quantidade_estoque=1, sku="A3", slug="a3"
        )
        with self.assertRaises(InsufficientStockError):
            create_order(self.user, [{"product_id": p.id, "quantity": 2}])
        p.refresh_from_db()
        self.assertEqual(p.quantidade_estoque, 1)  # unchanged
        self.assertEqual(Order.objects.count(), 0)  # rolled back

    def test_multiple_items_one_insufficient_rolls_back_all(self):
        p1 = make_product(
            categoria=self.category, quantidade_estoque=5, sku="B1", slug="b1"
        )
        p2 = make_product(
            categoria=self.category, quantidade_estoque=1, sku="B2", slug="b2"
        )
        with self.assertRaises(InsufficientStockError):
            create_order(
                self.user,
                [
                    {"product_id": p1.id, "quantity": 2},
                    {"product_id": p2.id, "quantity": 3},
                ],
            )
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.quantidade_estoque, 5)
        self.assertEqual(p2.quantidade_estoque, 1)
        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_product_references_are_merged(self):
        p = make_product(
            categoria=self.category, quantidade_estoque=5, sku="C1", slug="c1"
        )
        order = create_order(
            self.user,
            [
                {"product_id": p.id, "quantity": 2},
                {"product_id": p.id, "quantity": 1},
            ],
        )
        p.refresh_from_db()
        self.assertEqual(p.quantidade_estoque, 2)
        self.assertEqual(order.itens.count(), 1)
        self.assertEqual(order.itens.get().quantidade, 3)

    def test_empty_items_raises(self):
        with self.assertRaises(InvalidOrderError):
            create_order(self.user, [])

    def test_zero_quantity_raises(self):
        p = make_product(categoria=self.category, sku="D1", slug="d1")
        with self.assertRaises(InvalidOrderError):
            create_order(self.user, [{"product_id": p.id, "quantity": 0}])

    def test_missing_product_reference_raises(self):
        with self.assertRaises(InvalidOrderError):
            create_order(self.user, [{"quantity": 1}])

    def test_unknown_product_raises(self):
        with self.assertRaises(ProductNotFoundError):
            create_order(self.user, [{"product_id": 999999, "quantity": 1}])

    def test_inactive_product_cannot_be_ordered_by_id(self):
        p = make_product(categoria=self.category, ativo=False, sku="INA-1")
        with self.assertRaises(ProductNotFoundError):
            create_order(self.user, [{"product_id": p.id, "quantity": 1}])

    def test_inactive_product_cannot_be_ordered_by_sku(self):
        make_product(categoria=self.category, ativo=False, sku="INA-2")
        with self.assertRaises(ProductNotFoundError):
            create_order(self.user, [{"sku": "INA-2", "quantity": 1}])


class ConcurrencyTests(TransactionTestCase):
    """Two buyers race for the last unit; stock must never go negative."""

    def test_last_unit_race_never_oversells(self):
        category = Category.objects.create(nome="Cat", slug="cat")
        product = Product.objects.create(
            nome="Último",
            sku="LAST-1",
            slug="last-1",
            preco=Decimal("10.00"),
            quantidade_estoque=1,
            categoria=category,
        )
        u1 = User.objects.create_user("racer1", password="x")
        u2 = User.objects.create_user("racer2", password="x")

        barrier = threading.Barrier(2)

        def buy(user_id: int) -> str:
            try:
                barrier.wait()
                create_order(
                    User.objects.get(pk=user_id),
                    [{"product_id": product.id, "quantity": 1}],
                )
                return "ok"
            except InsufficientStockError:
                return "insufficient"
            except OperationalError:
                # In-memory shared-cache SQLite (the test database) does NOT
                # invoke the busy handler for cache locks, so the losing writer
                # may fail fast with "database is locked" at BEGIN IMMEDIATE
                # instead of blocking and then reading fresh stock. Its
                # transaction never started, so there is no oversell. A
                # file-based SQLite (dev/prod) blocks and returns a clean
                # InsufficientStockError instead -- see the single-threaded
                # test_insufficient_stock_raises_and_rolls_back for that path.
                return "locked"
            finally:
                # Release the per-thread DB connection.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, [u1.id, u2.id]))

        product.refresh_from_db()
        # The critical invariant: stock is never driven negative.
        self.assertEqual(product.quantidade_estoque, 0)
        self.assertEqual(results.count("ok"), 1)  # exactly one winner
        losers = [r for r in results if r != "ok"]
        self.assertEqual(len(losers), 1)
        self.assertIn(losers[0], {"insufficient", "locked"})
        self.assertEqual(Order.objects.count(), 1)  # no oversell
        self.assertEqual(OrderItem.objects.count(), 1)


class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("api-user", password="x")
        self.access_token = str(RefreshToken.for_user(self.user).access_token)
        self.category = Category.objects.create(nome="Cat", slug="cat")
        self.product = make_product(
            categoria=self.category,
            quantidade_estoque=5,
            sku="API-1",
            slug="api-1",
            preco=Decimal("20.00"),
        )
        self.url = reverse("orders:order-list-create")

    def auth(self) -> None:
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

    def test_requires_authentication(self):
        resp = self.client.post(
            self.url,
            {"itens": [{"produto": self.product.id, "quantidade": 1}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_order_success(self):
        self.auth()
        resp = self.client.post(
            self.url,
            {"itens": [{"produto": self.product.id, "quantidade": 2}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["valor_total"], "40.00")
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantidade_estoque, 3)
        self.assertEqual(Order.objects.get().usuario, self.user)

    def test_order_owner_is_request_user_not_payload(self):
        other = User.objects.create_user("victim", password="x")
        self.auth()
        resp = self.client.post(
            self.url,
            {
                "usuario": other.id,  # attempt to spoof ownership
                "itens": [{"produto": self.product.id, "quantidade": 1}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Order.objects.get().usuario, self.user)

    def test_create_order_insufficient_stock_returns_400(self):
        self.auth()
        resp = self.client.post(
            self.url,
            {"itens": [{"produto": self.product.id, "quantidade": 99}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Estoque insuficiente", resp.data["detail"])

    def test_create_order_by_sku(self):
        self.auth()
        resp = self.client.post(
            self.url,
            {"itens": [{"sku": "API-1", "quantidade": 1}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_empty_items_rejected_by_serializer(self):
        self.auth()
        resp = self.client.post(self.url, {"itens": []}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_list_only_returns_own_orders(self):
        other = User.objects.create_user("other", password="x")
        create_order(other, [{"product_id": self.product.id, "quantity": 1}])
        create_order(self.user, [{"product_id": self.product.id, "quantity": 1}])
        self.auth()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_idor_cannot_read_another_users_order(self):
        other = User.objects.create_user("other", password="x")
        other_order = create_order(
            other, [{"product_id": self.product.id, "quantity": 1}]
        )
        self.auth()
        resp = self.client.get(reverse("orders:order-detail", args=[other_order.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_can_read_own_order_detail(self):
        order = create_order(
            self.user, [{"product_id": self.product.id, "quantity": 1}]
        )
        self.auth()
        resp = self.client.get(reverse("orders:order-detail", args=[order.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], order.pk)

    def test_token_endpoint_issues_jwt(self):
        User.objects.create_user("tokuser", password="secret123")
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "tokuser", "password": "secret123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_token_refresh_endpoint(self):
        user = User.objects.create_user("refreshuser", password="secret123")
        refresh = RefreshToken.for_user(user)
        resp = self.client.post(
            reverse("token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)


class OrderAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root", "root@example.com", "pw")
        self.client.force_login(self.admin)
        self.buyer = User.objects.create_user("buyer", password="x")
        self.category = Category.objects.create(nome="Cat", slug="cat")
        self.product = make_product(
            categoria=self.category, quantidade_estoque=10, sku="Z1", slug="z1"
        )

    def _make_order(self) -> Order:
        return create_order(
            self.buyer, [{"product_id": self.product.id, "quantity": 1}]
        )

    def test_marcar_como_pago_action(self):
        o1 = self._make_order()
        o2 = self._make_order()
        url = reverse("admin:orders_order_changelist")
        resp = self.client.post(
            url,
            {
                "action": "marcar_como_pago",
                "_selected_action": [str(o1.pk), str(o2.pk)],
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        o1.refresh_from_db()
        o2.refresh_from_db()
        self.assertEqual(o1.status, Order.Status.PAGO)
        self.assertEqual(o2.status, Order.Status.PAGO)

    def test_order_change_page_shows_item_inline(self):
        order = self._make_order()
        url = reverse("admin:orders_order_change", args=[order.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "itens")  # inline verbose name present

    def test_valor_total_is_not_an_editable_input(self):
        order = self._make_order()
        url = reverse("admin:orders_order_change", args=[order.pk])
        resp = self.client.get(url)
        self.assertNotContains(resp, 'name="valor_total"')
        self.assertContains(resp, f"R$ {order.valor_total}")

    def test_valor_total_reflects_live_item_sum(self):
        order = self._make_order()
        order.valor_total = Decimal("999999.00")  # stale/tampered stored value
        order.save(update_fields=["valor_total"])

        url = reverse("admin:orders_order_change", args=[order.pk])
        resp = self.client.get(url)
        real_total = sum((item.subtotal for item in order.itens.all()), Decimal("0.00"))
        self.assertContains(resp, f"R$ {real_total}")
        self.assertNotContains(resp, "R$ 999999.00")

    def test_preco_unitario_is_not_an_editable_input(self):
        order = self._make_order()
        url = reverse("admin:orders_order_change", args=[order.pk])
        resp = self.client.get(url)
        self.assertNotContains(resp, 'name="itens-0-preco_unitario"')

    def test_new_item_added_via_admin_uses_products_current_price(self):
        order = self._make_order()
        self.product.preco = Decimal("777.00")
        self.product.save(update_fields=["preco"])

        other_product = make_product(
            categoria=self.category, quantidade_estoque=10, sku="Z2", slug="z2"
        )
        other_product.preco = Decimal("42.50")
        other_product.save(update_fields=["preco"])

        url = reverse("admin:orders_order_change", args=[order.pk])
        existing_item = order.itens.get()
        post_data = {
            "usuario": str(order.usuario_id),
            "status": order.status,
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "1",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": str(existing_item.pk),
            "itens-0-pedido": str(order.pk),
            "itens-0-produto": str(existing_item.produto_id),
            "itens-0-quantidade": str(existing_item.quantidade),
            "itens-1-id": "",
            "itens-1-pedido": str(order.pk),
            "itens-1-produto": str(other_product.pk),
            "itens-1-quantidade": "2",
            "_save": "Salvar",
        }
        resp = self.client.post(url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        new_item = order.itens.get(produto=other_product)
        self.assertEqual(new_item.preco_unitario, Decimal("42.50"))

        # The pre-existing item's frozen historical price is untouched, even
        # though the product's current price changed to 777.00 in this test.
        existing_item.refresh_from_db()
        self.assertNotEqual(existing_item.preco_unitario, Decimal("777.00"))

    def test_creating_order_from_scratch_in_admin_sets_correct_valor_total(self):
        """A brand new Order made directly via "Adicionar pedido" (not
        through orders.services.create_order) must still end up with a
        correct *stored* valor_total -- the API and storefront read that
        field directly, they don't recompute it live like the admin does.
        """
        url = reverse("admin:orders_order_add")
        post_data = {
            "usuario": str(self.buyer.id),
            "status": "pendente",
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": "",
            "itens-0-produto": str(self.product.id),
            "itens-0-quantidade": "12",
            "_save": "Salvar",
        }
        resp = self.client.post(url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        order = Order.objects.get(usuario=self.buyer)
        self.assertEqual(order.valor_total, self.product.preco * 12)

    def test_removing_item_via_inline_updates_stored_valor_total(self):
        order = self._make_order()
        item = order.itens.get()
        url = reverse("admin:orders_order_change", args=[order.pk])
        post_data = {
            "usuario": str(order.usuario_id),
            "status": order.status,
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "1",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": str(item.pk),
            "itens-0-pedido": str(order.pk),
            "itens-0-produto": str(item.produto_id),
            "itens-0-quantidade": str(item.quantidade),
            "itens-0-DELETE": "on",
            "_save": "Salvar",
        }
        resp = self.client.post(url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.itens.count(), 0)
        self.assertEqual(order.valor_total, Decimal("0.00"))
