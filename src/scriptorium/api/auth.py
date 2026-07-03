import hmac

from django.conf import settings
from ninja.security import HttpBearer


class ApiKeyAuth(HttpBearer):
    """Single-user bearer auth: the token is the static API key from
    settings (``SCRIPTORIUM_API_KEY`` in the environment)."""

    def authenticate(self, request, token):
        if hmac.compare_digest(token, settings.API_KEY):
            return token
        return None
