from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Same as TokenObtainPairView, but rate-limited per IP (scope "login").

    Login is where brute-force credential guessing happens, so it needs a
    tighter limit than the general "anon" rate applied to the rest of the
    public API.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
