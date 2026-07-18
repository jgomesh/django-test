"""URL configuration for the config project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from main.views import status

urlpatterns = [
    path("admin/", admin.site.urls),
    # REST API (v1)
    path("api/v1/status/", status, name="status"),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("orders.urls")),
    path("api/v1/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Public storefront (templates) -- kept last so it owns the root path.
    path("", include("storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
