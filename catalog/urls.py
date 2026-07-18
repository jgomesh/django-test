from django.urls import path

from .views import ProductListAPIView

app_name = "catalog"

urlpatterns = [
    path("produtos/", ProductListAPIView.as_view(), name="product-list"),
]
