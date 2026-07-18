from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

User = get_user_model()


class LoginThrottleTests(APITestCase):
    """Login uses its own "login" throttle scope (5/min, see settings.py),
    tighter than the general "anon" rate -- this is what actually protects
    against password brute-forcing."""

    def setUp(self):
        cache.clear()
        User.objects.create_user("tokuser", password="secret123")

    def tearDown(self):
        cache.clear()

    def test_login_still_works_under_the_rate_limit(self):
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "tokuser", "password": "secret123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)

    def test_login_is_blocked_after_exceeding_the_rate_limit(self):
        payload = {"username": "tokuser", "password": "wrong-password"}

        for _ in range(5):
            resp = self.client.post(
                reverse("token_obtain_pair"), payload, format="json"
            )
            self.assertEqual(resp.status_code, 401)

        resp = self.client.post(reverse("token_obtain_pair"), payload, format="json")
        self.assertEqual(resp.status_code, 429)
