from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Product


class Order(models.Model):
    """Pedido feito por um usuário."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGO = "pago", "Pago"
        CANCELADO = "cancelado", "Cancelado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="pedidos",
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    valor_total = models.DecimalField(
        "valor total", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    data_criacao = models.DateTimeField("data de criação", auto_now_add=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-data_criacao"]

    def __str__(self) -> str:
        return f"Pedido #{self.pk} ({self.get_status_display()})"


class OrderItem(models.Model):
    """Item de um pedido, com preço unitário congelado no momento da compra."""

    pedido = models.ForeignKey(
        Order,
        verbose_name="pedido",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    produto = models.ForeignKey(
        Product,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="itens_pedido",
    )
    quantidade = models.PositiveIntegerField("quantidade")
    preco_unitario = models.DecimalField(
        "preço unitário", max_digits=10, decimal_places=2
    )

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self) -> str:
        return f"{self.quantidade}x {self.produto} (Pedido #{self.pedido_id})"

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade
