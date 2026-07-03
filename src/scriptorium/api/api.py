from ninja import NinjaAPI

from scriptorium.api.auth import ApiKeyAuth
from scriptorium.api.routes.books import router as books_router
from scriptorium.api.routes.queue import router as queue_router

api = NinjaAPI(title="Scriptorium API", auth=ApiKeyAuth())
api.add_router("/books", books_router)
api.add_router("/queue", queue_router)
