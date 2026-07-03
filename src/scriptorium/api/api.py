from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import NinjaAPI

from scriptorium.api.auth import ApiKeyAuth
from scriptorium.api.routes.authors import router as authors_router
from scriptorium.api.routes.books import router as books_router
from scriptorium.api.routes.queue import router as queue_router
from scriptorium.api.routes.quotes import router as quotes_router
from scriptorium.api.routes.reads import router as reads_router
from scriptorium.api.routes.series import router as series_router
from scriptorium.api.routes.tags import router as tags_router

api = NinjaAPI(title="Scriptorium API", auth=ApiKeyAuth())
api.add_router("/books", books_router)
api.add_router("/queue", queue_router)
api.add_router("/reads", reads_router)
api.add_router("/quotes", quotes_router)
api.add_router("/authors", authors_router)
api.add_router("/tags", tags_router)
api.add_router("/series", series_router)


@api.exception_handler(DjangoValidationError)
def handle_django_validation_error(request, exc):
    """Model-level validation failures become structured 400s. Raised inside
    an atomic view, the exception has already rolled the transaction back by
    the time this handler builds the response."""
    detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
    return api.create_response(request, {"detail": detail}, status=400)
