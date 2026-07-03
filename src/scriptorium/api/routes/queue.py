from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from ninja import Router

from scriptorium.api.schemas import MessageOut, QueueAddIn, QueueAddOut, QueueItemOut
from scriptorium.main.models import Book, BookStatus, Series
from scriptorium.main.utils import slugify

router = Router(tags=["queue"])


def _queue():
    """The review queue (oldest first): unreviewed reads plus published books
    whose latest read is newer than their review."""
    return Book.all_objects.needs_review()


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
    response={200: QueueAddOut, 201: QueueAddOut, 409: MessageOut},
    summary="Add a book to the review queue",
)
@transaction.atomic
def add_to_queue(request, payload: QueueAddIn):
    """Queue a finished book for a later review, creating the author, series,
    and book as needed (all deduplicated by slug) and logging the read. Like
    the web form, an already published book stays published and its new read
    queues it as a reread instead. Re-submitting an already logged date
    updates that read's notes instead of adding a row and returns 200;
    ``queued`` reports whether the book actually ended up in the queue."""
    existing = Book.all_objects.filter(
        primary_author__name_slug=slugify(payload.author_name),
        title_slug=slugify(payload.title),
    ).first()
    if existing and existing.status == BookStatus.REVIEWED and not payload.date_read:
        # Refuse before creating the author, series, or anything else.
        return 409, {
            "detail": f"“{existing.title}” already has a published review — include "
            "date_read to queue it as a reread."
        }
    duplicate_read = (
        existing.reads.filter(finished_on=payload.date_read).first()
        if existing and payload.date_read
        else None
    )
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
    if duplicate_read:
        # sync_reads skipped the already-logged date; keep the submitted
        # notes instead of silently discarding them.
        duplicate_read.notes = payload.notes or None
        duplicate_read.source = "manual"
        duplicate_read.save(update_fields=["notes", "source"])
    book = (
        Book.all_objects.select_related("primary_author", "series")
        .prefetch_related("additional_authors", "reads")
        .annotate(date=Max("reads__finished_on"))
        .get(pk=book.pk)
    )
    book.queued = Book.all_objects.needs_review().filter(pk=book.pk).exists()
    return (200 if duplicate_read else 201), book


@router.post(
    "/{book_id}/dismiss/",
    response={204: None},
    summary="Dismiss a reread from the queue",
)
def dismiss_reread(request, book_id: int):
    """The explicit "review still stands" action: stamp the published review
    as current so the book's newer reads leave the reread queue. Unreviewed
    books can't be dismissed (404) -- they need a review, or deletion."""
    book = get_object_or_404(
        Book.all_objects.filter(status=BookStatus.REVIEWED), pk=book_id
    )
    book.mark_review_current()
    return 204, None
