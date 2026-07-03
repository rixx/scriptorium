from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import paginate

from scriptorium.api.schemas import BookDetailOut, BookListOut
from scriptorium.main.models import Book, BookStatus

router = Router(tags=["books"])


def _book_queryset():
    return Book.all_objects.select_related("primary_author", "series").prefetch_related(
        "additional_authors", "tags", "reads"
    )


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
    return get_object_or_404(
        _book_queryset(), primary_author__name_slug=author_slug, title_slug=title_slug
    )
