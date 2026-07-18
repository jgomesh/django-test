"""Business logic for creating orders safely under concurrency.

The single source of truth for order creation. Both the DRF API
(``POST /api/v1/pedidos/``) and the storefront "Comprar" button call
``create_order`` so the stock-consistency guarantees live in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from catalog.models import Product

from .models import Order, OrderItem


class OrderError(Exception):
    """Base class for domain errors raised while creating an order."""


class InsufficientStockError(OrderError):
    """Raised when a product does not have enough stock for the request."""

    def __init__(self, product: Product, requested: int, available: int) -> None:
        self.product = product
        self.requested = requested
        self.available = available
        super().__init__(
            f"Estoque insuficiente para '{product.nome}': "
            f"solicitado {requested}, disponível {available}."
        )


class ProductNotFoundError(OrderError):
    """Raised when a requested product does not exist."""


class InvalidOrderError(OrderError):
    """Raised when the order payload itself is invalid (e.g. empty)."""


@dataclass(frozen=True)
class OrderLine:
    """A normalized request line: which product and how many units."""

    product_id: int
    quantity: int


def _normalize_items(items: list[dict]) -> list[OrderLine]:
    """Validate and normalize raw item payloads into OrderLine objects.

    Each item may reference a product by ``product_id`` or by ``sku``. Repeated
    references to the same product are merged so a single row lock is enough.
    """
    if not items:
        raise InvalidOrderError("O pedido precisa conter ao menos um item.")

    # Resolve every reference to a concrete product id up front.
    merged: dict[int, int] = {}
    for raw in items:
        quantity = raw.get("quantity")
        if quantity is None or int(quantity) <= 0:
            raise InvalidOrderError("A quantidade de cada item deve ser >= 1.")
        quantity = int(quantity)

        product_id = raw.get("product_id")
        sku = raw.get("sku")
        if product_id is None and sku is None:
            raise InvalidOrderError("Cada item deve informar 'product_id' ou 'sku'.")

        try:
            if product_id is not None:
                resolved_id = (
                    Product.objects.filter(ativo=True)
                    .values_list("id", flat=True)
                    .get(pk=product_id)
                )
            else:
                resolved_id = (
                    Product.objects.filter(ativo=True)
                    .values_list("id", flat=True)
                    .get(sku=sku)
                )
        except Product.DoesNotExist as exc:
            ref = product_id if product_id is not None else sku
            raise ProductNotFoundError(f"Produto não encontrado: {ref}.") from exc

        merged[resolved_id] = merged.get(resolved_id, 0) + quantity

    return [OrderLine(product_id=pid, quantity=qty) for pid, qty in merged.items()]


@transaction.atomic
def create_order(user: AbstractBaseUser, items: list[dict]) -> Order:
    """Create an order for ``user`` from ``items``, guaranteeing stock safety.

    ``items`` is a list of dicts, each with ``quantity`` plus either
    ``product_id`` or ``sku``.

    Concurrency guarantee: every product row is locked with
    ``select_for_update`` (in a stable id order to avoid deadlocks) before its
    stock is checked and decremented, all inside a single atomic transaction.
    Two buyers racing for the last unit can never drive stock negative -- one
    succeeds and the other gets an :class:`InsufficientStockError`.

    Because we hold the row lock for the whole check-then-decrement, a plain
    ``save()`` on the freshly-locked instance is race-free (no ``F()`` needed).
    """
    lines = _normalize_items(items)

    # Lock rows in a deterministic order (sorted by id) to avoid deadlocks
    # when several products are bought in one order.
    lines.sort(key=lambda line: line.product_id)
    product_ids = [line.product_id for line in lines]

    locked = {
        product.id: product
        for product in Product.objects.select_for_update()
        .filter(id__in=product_ids)
        .order_by("id")
    }

    order = Order.objects.create(usuario=user)
    order_items: list[OrderItem] = []
    valor_total = Decimal("0.00")

    for line in lines:
        product = locked[line.product_id]
        if line.quantity > product.quantidade_estoque:
            raise InsufficientStockError(
                product, line.quantity, product.quantidade_estoque
            )

        product.quantidade_estoque -= line.quantity
        product.save(update_fields=["quantidade_estoque"])

        order_items.append(
            OrderItem(
                pedido=order,
                produto=product,
                quantidade=line.quantity,
                preco_unitario=product.preco,
            )
        )
        valor_total += product.preco * line.quantity

    OrderItem.objects.bulk_create(order_items)
    order.valor_total = valor_total
    order.save(update_fields=["valor_total"])
    return order
