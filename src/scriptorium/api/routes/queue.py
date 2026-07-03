from django.db.models import Max
from ninja import Router

from scriptorium.api.schemas import MessageOut, QueueAddIn, QueueItemOut
from scriptorium.main.models import Book, BookStatus, Series

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


@router.post(
    "/",
    response={201: QueueItemOut, 409: MessageOut},
    summary="Add a book to the review queue",
)
def add_to_queue(request, payload: QueueAddIn):
    """Queue a finished book for a later review, creating the author, series,
    and book as needed (all deduplicated by slug) and logging the read. Like
    the web form, an already published book stays published and its new read
    queues it as a reread instead."""
    series = (
        Series.objects.get_or_create_by_name(payload.series)[0]
        if payload.series
        else None
    )
    book, _ = Book.all_objects.queue_for_review(
        title=payload.title,
        author_name=payload.author_name,
        date=payload.date_read,
        series=series,
        series_position=payload.series_position,
        notes=payload.notes,
        shelf=payload.shelf,
    )
    if book.status == BookStatus.REVIEWED and not payload.date_read:
        return 409, {
            "detail": f"“{book.title}” already has a published review — include "
            "date_read to queue it as a reread."
        }
    book = (
        Book.all_objects.select_related("primary_author", "series")
        .prefetch_related("additional_authors", "reads")
        .annotate(date=Max("reads__finished_on"))
        .get(pk=book.pk)
    )
    return 201, book
