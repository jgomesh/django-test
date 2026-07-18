from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model, kept identical to Django's default for now.

    Starting with a custom ``AUTH_USER_MODEL`` (even empty) is the
    Django-recommended default: swapping it later requires a full migration
    reset, so it's cheapest to do this on day one.
    """
