from rest_framework import generics, permissions, status
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer
from .services import OrderError, create_order


class OrderListCreateAPIView(generics.ListAPIView):
    """List the authenticated user's orders and create new ones.

    IDOR protection: ``get_queryset`` is always scoped to ``request.user`` and
    the created order's owner is taken from ``request.user`` -- never from the
    request payload -- so a user can neither read nor spoof another user's order.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(usuario=self.request.user)
            .prefetch_related("itens__produto")
            .order_by("-data_criacao")
        )

    def post(self, request: Request, *args, **kwargs) -> Response:
        payload = OrderCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            order = create_order(request.user, payload.to_service_items())
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        order = (
            Order.objects.filter(pk=order.pk).prefetch_related("itens__produto").get()
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailAPIView(generics.RetrieveAPIView):
    """Retrieve a single order, scoped to its owner (IDOR-safe)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(usuario=self.request.user).prefetch_related(
            "itens__produto"
        )
