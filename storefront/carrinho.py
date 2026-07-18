from decimal import Decimal

from catalog.models import Product

SESSION_KEY = "carrinho"


class Carrinho:
    """Session-backed shopping cart: ``{product_id: quantity}``.

    Ephemeral by design (no DB model) -- it only becomes a real Order once
    ``finalizar_compra`` hands its items to ``orders.services.create_order``.
    """

    def __init__(self, request):
        self.session = request.session
        self._dados: dict[str, int] = self.session.get(SESSION_KEY, {})

    def adicionar(self, produto: Product, quantidade: int = 1) -> None:
        pid = str(produto.id)
        self._dados[pid] = self._dados.get(pid, 0) + quantidade
        self._salvar()

    def atualizar(self, product_id: int, quantidade: int) -> None:
        pid = str(product_id)
        if quantidade <= 0:
            self._dados.pop(pid, None)
        else:
            self._dados[pid] = quantidade
        self._salvar()

    def remover(self, product_id: int) -> None:
        self._dados.pop(str(product_id), None)
        self._salvar()

    def limpar(self) -> None:
        self._dados = {}
        self._salvar()

    def _salvar(self) -> None:
        self.session[SESSION_KEY] = self._dados
        self.session.modified = True

    def __len__(self) -> int:
        return sum(self._dados.values())

    def itens(self) -> list[dict]:
        """One dict per cart line: produto, quantidade, subtotal.

        Only active products are returned -- if a product was deactivated
        after being added to the cart, it silently drops out here (and the
        stale session entry is cleared) instead of being purchasable again.
        """
        if not self._dados:
            return []
        produtos = Product.objects.filter(
            id__in=[int(pid) for pid in self._dados], ativo=True
        ).select_related("categoria")
        linhas = []
        ids_validos = set()
        for produto in produtos:
            quantidade = self._dados.get(str(produto.id), 0)
            ids_validos.add(str(produto.id))
            linhas.append(
                {
                    "produto": produto,
                    "quantidade": quantidade,
                    "subtotal": produto.preco * quantidade,
                }
            )
        if ids_validos != set(self._dados):
            self._dados = {
                pid: qtd for pid, qtd in self._dados.items() if pid in ids_validos
            }
            self._salvar()
        return linhas

    def total(self) -> Decimal:
        return sum((linha["subtotal"] for linha in self.itens()), Decimal("0.00"))

    def to_service_items(self) -> list[dict]:
        return [
            {"product_id": int(pid), "quantity": quantidade}
            for pid, quantidade in self._dados.items()
        ]
