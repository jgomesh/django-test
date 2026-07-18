from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("produto/<slug:slug>/", views.product_detail, name="product_detail"),
    path("produto/<slug:slug>/comprar/", views.comprar, name="comprar"),
    path("entrar/", LoginView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
]
