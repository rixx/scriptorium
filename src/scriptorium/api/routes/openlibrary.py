from ninja import Router
from ninja.errors import HttpError

from scriptorium.api.schemas import (
    OpenLibraryBookOut,
    OpenLibraryEditionOut,
    OpenLibraryWorkOut,
)
from scriptorium.main import metadata

router = Router(tags=["openlibrary"])


def _proxy(func, *args, **kwargs):
    """Call a metadata helper, translating upstream failures (timeouts,
    network errors, non-JSON responses) into a 502 instead of letting the
    requests exception bubble up as a 500 of our own."""
    try:
        return func(*args, **kwargs)
    except metadata.MetadataError as exc:
        raise HttpError(502, str(exc)) from exc


@router.get(
    "/search/", response=list[OpenLibraryWorkOut], summary="Search OpenLibrary works"
)
def search_works(request, q: str):
    return _proxy(metadata.search_openlibrary, q)


@router.get(
    "/works/{work_id}/editions/",
    response=list[OpenLibraryEditionOut],
    summary="List a work's editions",
)
def work_editions(request, work_id: str):
    """Editions filtered to languages I read (en/de/la), sorted the way the
    review wizard shows them."""
    return _proxy(metadata.get_openlibrary_editions_data, work_id)


@router.get(
    "/books/{olid}/",
    response=OpenLibraryBookOut,
    summary="Edition metadata for book creation",
)
def book_metadata(request, olid: str):
    """A single edition, normalized to the field names the queue-add and
    book PATCH/review endpoints expect."""
    book = _proxy(metadata.get_openlibrary_book_data, olid)
    if book is None:
        raise HttpError(404, f"OpenLibrary has no book for id '{olid}'.")
    return book
