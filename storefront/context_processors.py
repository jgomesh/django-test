from .carrinho import Carrinho


def carrinho_count(request):
    """Exposes ``cart_count`` to every template (used by the header badge)."""
    if not hasattr(request, "session"):
        return {"cart_count": 0}
    return {"cart_count": len(Carrinho(request))}
