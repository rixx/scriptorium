import datetime as dt

from django.utils.timezone import now
from ninja.security import HttpBearer

from scriptorium.main.models import ApiToken

#: last_used is informational ("is this token still in use?"), so it only
#: needs hour resolution -- skipping fresher stamps avoids a database write
#: on every request.
LAST_USED_THROTTLE = dt.timedelta(hours=1)


class ApiTokenAuth(HttpBearer):
    """Bearer auth against database-backed ``ApiToken`` rows, which are
    created and revoked in the private UI at ``/b/tokens/``."""

    def authenticate(self, request, token):
        if not token:
            # Never match an empty bearer token, and skip the query.
            return None
        api_token = ApiToken.objects.filter(token=token).first()
        if api_token is None:
            return None
        timestamp = now()
        if (
            api_token.last_used is None
            or timestamp - api_token.last_used > LAST_USED_THROTTLE
        ):
            api_token.last_used = timestamp
            api_token.save(update_fields=["last_used"])
        return api_token
