from django.urls import path

from .views import OrderDetailAPIView, OrderListCreateAPIView

app_name = "orders"

urlpatterns = [
    path("pedidos/", OrderListCreateAPIView.as_view(), name="order-list-create"),
    path("pedidos/<int:pk>/", OrderDetailAPIView.as_view(), name="order-detail"),
]
