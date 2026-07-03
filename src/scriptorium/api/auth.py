import hmac

from django.conf import settings
from ninja.security import HttpBearer


class ApiKeyAuth(HttpBearer):
    """Single-user bearer auth: the token is the static API key from
    settings (``SCRIPTORIUM_API_KEY`` in the environment)."""

    def authenticate(self, request, token):
        if not settings.API_KEY:
            # No key configured: the API is disabled, nothing may match --
            # especially not an empty bearer token.
            return None
        # Compare bytes: compare_digest raises on non-ASCII str input.
        if hmac.compare_digest(token.encode(), settings.API_KEY.encode()):
            return token
        return None
