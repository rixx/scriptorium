from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate

from scriptorium.api.schemas import (
    BookDetailOut,
    BookListOut,
    BookPatchIn,
    MessageOut,
    QuoteIn,
    QuoteOut,
    ReadDetailOut,
    ReadIn,
    ReviewSubmitIn,
)
from scriptorium.main.models import Author, Book, BookStatus, Quote, Series, Tag
from scriptorium.main.utils import slugify

router = Router(tags=["books"])

# Nullable but blank=False fields that legitimately stay empty (drafts have
# no review text or feed dates yet, ``social`` is optional); full_clean would
# reject them even though the API cannot set them to anything invalid.
BOOK_CLEAN_EXCLUDE = ("text", "feed_date", "review_updated", "social")


def _book_queryset():
    return Book.all_objects.select_related("primary_author", "series").prefetch_related(
        "additional_authors", "tags", "reads"
    )


def _get_book(author_slug, title_slug):
    return get_object_or_404(
        _book_queryset(), primary_author__name_slug=author_slug, title_slug=title_slug
    )


def _resolve_tags(specs):
    """Turn 'category:name' strings into Tag rows, creating missing ones.
    The post-colon part is slugified (like author and series names), so
    'genre:Science Fiction' and 'genre:science-fiction' are the same tag."""
    tags = []
    for spec in specs:
        category, _, name = spec.partition(":")
        slug = slugify(name)
        if not slug or category not in Tag.TagCategory.values:
            raise HttpError(
                400,
                f"Invalid tag '{spec}': expected 'category:name' with a "
                f"category out of {', '.join(Tag.TagCategory.values)}.",
            )
        tags.append(
            Tag.objects.get_or_create(
                category=category, name_slug=slug, defaults={"name": name.strip()}
            )[0]
        )
    return tags


def _apply_book_patch(book, data, *, keep_values=False):
    """Apply a partial update dict (from ``model_dump(exclude_unset=True)``)
    to a book. With ``keep_values``, empty fields keep the book's current
    values (the review wizard's semantics for queued books); otherwise an
    explicit null clears the field (PATCH semantics)."""
    if keep_values:
        data = {key: value for key, value in data.items() if value not in (None, "")}
    if "series" in data:
        name = data.pop("series")
        book.series = Series.objects.get_or_create_by_name(name)[0] if name else None
    has_tags = "tags" in data
    tags = data.pop("tags", None)
    for field, value in data.items():
        setattr(book, field, value)
    if has_tags:
        # Like the other fields, an explicit null clears the tag set.
        book.tags.set(_resolve_tags(tags) if tags else [])


def _add_quote(book, payload: QuoteIn):
    quote = Quote(
        source_book=book,
        text=payload.text,
        language=payload.language,
        order=payload.order,
    )
    if payload.source_author:
        author = Author.objects.filter(name_slug=payload.source_author).first()
        if author is None:
            raise HttpError(400, f"Unknown author '{payload.source_author}'.")
        quote.source_author = author
    quote.full_clean()
    quote.save()
    return quote


@router.get("/", response=list[BookListOut], summary="List and search books")
@paginate
def list_books(
    request, q: str | None = None, status: str | None = None, year: int | None = None
):
    """Published (reviewed) books by default; pass ``status`` to look at the
    to-read or to-review shelves instead. ``q`` searches titles and author
    names, ``year`` filters by the year a read was finished."""
    books = _book_queryset().filter(status=status or BookStatus.REVIEWED)
    if q:
        books = books.filter(
            Q(title__icontains=q)
            | Q(primary_author__name__icontains=q)
            | Q(additional_authors__name__icontains=q)
        )
    if year:
        books = books.filter(reads__finished_on__year=year)
    return books.distinct().order_by("primary_author__name_slug", "title_slug")


@router.get(
    "/{author_slug}/{title_slug}/", response=BookDetailOut, summary="Book detail"
)
def book_detail(request, author_slug: str, title_slug: str):
    return _get_book(author_slug, title_slug)


@router.patch(
    "/{author_slug}/{title_slug}/",
    response=BookDetailOut,
    summary="Update book metadata and review fields",
)
@transaction.atomic
def update_book(request, author_slug: str, title_slug: str, payload: BookPatchIn):
    """Partial update: only fields present in the payload change, an explicit
    null clears a field (including the tag set). Editing the text of a
    published review stamps ``review_updated`` (taking the book out of the
    reread queue); the slug identity (title, author) and reads are managed
    elsewhere."""
    book = _get_book(author_slug, title_slug)
    _apply_book_patch(book, payload.model_dump(exclude_unset=True))
    book.full_clean(exclude=BOOK_CLEAN_EXCLUDE)
    book.save()
    return _get_book(author_slug, title_slug)


@router.post(
    "/{author_slug}/{title_slug}/review/",
    response={200: BookDetailOut, 409: MessageOut},
    summary="Publish a review",
)
@transaction.atomic
def submit_review(request, author_slug: str, title_slug: str, payload: ReviewSubmitIn):
    """The composite publish endpoint: in one atomic request, update the
    book's metadata, set the review fields, publish the book, log the read
    dates (additively), and attach quotes. Refuses to overwrite an already
    published review unless ``overwrite`` is set -- incremental edits belong
    in the PATCH endpoint instead."""
    book = _get_book(author_slug, title_slug)
    if book.status == BookStatus.REVIEWED and not payload.overwrite:
        return 409, {
            "detail": f"“{book.title}” already has a published review — pass "
            "overwrite=true to replace it, or PATCH the book to edit it."
        }
    if payload.metadata:
        # Like the review wizard: empty metadata fields keep the values the
        # queued book already carries.
        _apply_book_patch(
            book, payload.metadata.model_dump(exclude_unset=True), keep_values=True
        )
    book.text = payload.text
    if payload.tldr is not None:
        book.tldr = payload.tldr
    if payload.rating is not None:
        book.rating = payload.rating
    book.status = BookStatus.REVIEWED
    book.full_clean(exclude=BOOK_CLEAN_EXCLUDE)
    book.save()  # Stamps feed_date and review_updated.
    # Republishing with unchanged text is still a deliberate "the review is
    # current" action, which Book.save() alone wouldn't register.
    book.mark_review_current()
    # A queued book may already have Read rows; only add missing dates.
    book.sync_reads(payload.dates_read, did_not_finish=payload.did_not_finish)
    for quote in payload.quotes:
        _add_quote(book, quote)
    return 200, _get_book(author_slug, title_slug)


@router.post(
    "/{author_slug}/{title_slug}/reads/",
    response={200: ReadDetailOut, 201: ReadDetailOut},
    summary="Log a read",
)
def add_read(request, author_slug: str, title_slug: str, payload: ReadIn):
    """Additive: a read that already exists on the given date is returned
    unchanged (200) instead of duplicated. A new latest read on a published
    book bumps its feed date, like every other read-logging path."""
    book = _get_book(author_slug, title_slug)
    read = book.reads.filter(finished_on=payload.date).first()
    if read is not None:
        return 200, read
    book.sync_reads(
        [payload.date],
        started_on=payload.started_on,
        format=payload.format,
        source=payload.source,
        notes=payload.notes,
        did_not_finish=payload.did_not_finish,
    )
    return 201, book.reads.get(finished_on=payload.date)


@router.get(
    "/{author_slug}/{title_slug}/quotes/",
    response=list[QuoteOut],
    summary="List a book's quotes",
)
def book_quotes(request, author_slug: str, title_slug: str):
    return _get_book(author_slug, title_slug).quotes.all()


@router.post(
    "/{author_slug}/{title_slug}/quotes/",
    response={201: QuoteOut},
    summary="Add a quote to a book",
)
def add_quote(request, author_slug: str, title_slug: str, payload: QuoteIn):
    return 201, _add_quote(_get_book(author_slug, title_slug), payload)
