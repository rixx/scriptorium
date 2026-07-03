from ninja import Router

from scriptorium.api.schemas import MessageOut, QueueItemOut
from scriptorium.main.models import Book

router = Router(tags=["queue"])


def _queue():
    """The review queue (oldest first): unreviewed reads plus published books
    whose latest read is newer than their review."""
    return Book.all_objects.needs_review().prefetch_related("reads")


@router.get("/", response=list[QueueItemOut], summary="List the review queue")
def review_queue(request):
    return _queue()


@router.get(
    "/next/",
    response={200: QueueItemOut, 404: MessageOut},
    summary="Next book to review",
)
def next_in_queue(request):
    book = _queue().first()
    if book is None:
        return 404, {"detail": "The review queue is empty."}
    return 200, book
