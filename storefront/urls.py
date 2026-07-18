from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("produto/<slug:slug>/", views.product_detail, name="product_detail"),
    path("produto/<slug:slug>/comprar/", views.comprar, name="comprar"),
    path(
        "produto/<slug:slug>/adicionar-ao-carrinho/",
        views.adicionar_ao_carrinho,
        name="adicionar_ao_carrinho",
    ),
    path("carrinho/", views.carrinho, name="carrinho"),
    path(
        "carrinho/item/<int:product_id>/atualizar/",
        views.atualizar_item_carrinho,
        name="atualizar_item_carrinho",
    ),
    path(
        "carrinho/item/<int:product_id>/remover/",
        views.remover_do_carrinho,
        name="remover_do_carrinho",
    ),
    path("carrinho/finalizar/", views.finalizar_compra, name="finalizar_compra"),
    path("entrar/", LoginView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
]
