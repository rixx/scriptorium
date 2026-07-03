import datetime as dt

import pytest
from django.utils.timezone import now

from scriptorium.api.routes.koreader import (
    _extract_isbns,
    _parse_version,
    _series_position,
)
from scriptorium.main.models import Author, Book, BookStatus, Read, Series
from tests.factories import AuthorFactory, BookFactory, ReadFactory, make_reviewed_book

pytestmark = pytest.mark.django_db

MD5 = "8a1a4d0d64d09761b0eb0e3d97e4e848"

HIGHLIGHT = {
    "text": "Light is the left hand of darkness...",
    "note": None,
    "chapter": "Chapter 16",
    "datetime": "2026-06-28 21:14:03",
    "pageno": 233,
    "color": "yellow",
    "drawer": "lighten",
}


def _book_payload(**overrides):
    payload = {
        "md5": MD5,
        "title": "The Left Hand of Darkness",
        "authors": ["Ursula K. Le Guin"],
        "identifiers": ["ISBN:9780441478125", "uuid:not-an-isbn"],
        "series": "Hainish Cycle",
        "series_index": 6,
        "pages": 304,
        "finished_on": "2026-07-01",
        "started_on": "2026-06-12",
        "total_time_seconds": 25440,
        "highlights": [HIGHLIGHT],
    }
    payload.update(overrides)
    return payload


def _sync(api_client, *books, plugin_version="1.0.0"):
    return api_client.post(
        "/api/koreader/sync/",
        {
            "plugin_version": plugin_version,
            "device": {"id": "inkpalm-test", "model": "InkPalm 5"},
            "books": list(books),
        },
        content_type="application/json",
    )


# --- Helper units ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "parsed"),
    [("1.0.0", (1, 0, 0)), ("2.13.1", (2, 13, 1)), ("not-a-version", (0,))],
)
def test_koreader_parse_version(version, parsed):
    assert _parse_version(version) == parsed


@pytest.mark.parametrize(
    ("identifiers", "isbns"),
    [
        (["ISBN:9780441478125"], ["9780441478125"]),
        (["urn:isbn:978-0-441-47812-5"], ["9780441478125"]),
        (["9780441478125"], ["9780441478125"]),
        (["isbn:0-9752298-0-X"], ["097522980X"]),
        # calibre/uuid identifiers and non-ISBN strings are ignored.
        (["calibre:1234", "uuid:aaaa-bbbb", "123456789Z"], []),
        ([], []),
    ],
)
def test_koreader_extract_isbns(identifiers, isbns):
    assert _extract_isbns(identifiers) == isbns


@pytest.mark.parametrize(
    ("series_index", "position"),
    [(6, "6"), (6.0, "6"), (1.5, "1.5"), ("II", "II"), (None, None), ("", None)],
)
def test_koreader_series_position(series_index, position):
    assert _series_position(series_index) == position


# --- Auth and version gate ------------------------------------------------------


def test_koreader_sync_requires_token(client, api_token):
    response = client.post(
        "/api/koreader/sync/",
        {"plugin_version": "1.0.0", "books": [_book_payload()]},
        content_type="application/json",
    )

    assert response.status_code == 401
    assert Book.all_objects.count() == 0


@pytest.mark.parametrize("plugin_version", ["0.9.0", "not-a-version"])
def test_koreader_sync_rejects_outdated_plugin(api_client, plugin_version):
    response = _sync(api_client, _book_payload(), plugin_version=plugin_version)

    assert response.status_code == 426
    assert list(response.json()) == ["detail"]
    assert Book.all_objects.count() == 0


def test_koreader_sync_requires_at_least_one_book(api_client):
    response = api_client.post(
        "/api/koreader/sync/",
        {"plugin_version": "1.0.0", "books": []},
        content_type="application/json",
    )

    assert response.status_code == 422


# --- Matching chain -------------------------------------------------------------


def test_koreader_sync_auto_creates_book_in_review_queue(api_client):
    response = _sync(api_client, _book_payload())

    assert response.status_code == 200
    book = Book.all_objects.get()
    read = book.reads.get()
    assert response.json() == {
        "results": [
            {
                "md5": MD5,
                "action": "created_book",
                "book": "ursula-k-le-guin/the-left-hand-of-darkness",
                "read_id": read.pk,
                "highlights_stored": 1,
                "warnings": ["ISBN not in library; matched by title/author"],
                "detail": None,
            }
        ]
    }
    assert book.title == "The Left Hand of Darkness"
    assert book.status == BookStatus.TO_REVIEW
    assert book.source == "koreader"
    assert book.pages == 304
    assert book.isbn13 == "9780441478125"
    assert book.isbn10 is None
    assert book.series.name == "Hainish Cycle"
    assert book.series_position == "6"
    assert book.primary_author.name == "Ursula K. Le Guin"
    assert read.finished_on == dt.date(2026, 7, 1)
    assert read.started_on == dt.date(2026, 6, 12)
    assert read.total_time_seconds == 25440
    assert read.format == "ebook"
    assert read.source == "koreader"
    assert read.koreader_md5 == MD5
    assert read.highlights == [HIGHLIGHT]
    assert read.notes is None
    assert read.did_not_finish is False
    assert list(Book.all_objects.needs_review()) == [book]


def test_koreader_sync_matches_known_md5_before_anything_else(api_client):
    """A known device file wins even when title and ISBN point elsewhere:
    the book was matched (or renamed) once, later pushes must stick."""
    book = BookFactory(title="Fixed Up Title", status=BookStatus.TO_REVIEW)
    ReadFactory(book=book, finished_on=dt.date(2020, 1, 1), koreader_md5=MD5)
    decoy = BookFactory(title="The Left Hand of Darkness", isbn13="9780441478125")

    response = _sync(api_client, _book_payload())

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["action"] == "matched"
    assert result["book"] == book.slug
    assert Book.all_objects.count() == 2
    assert book.reads.count() == 2
    assert decoy.reads.count() == 0


@pytest.mark.parametrize(
    "identifier", ["ISBN:9780441478125", "urn:isbn:978-0-441-47812-5", "9780441478125"]
)
def test_koreader_sync_matches_by_isbn13(api_client, identifier):
    book = BookFactory(
        title="A Completely Different Title",
        status=BookStatus.TO_READ,
        isbn13="9780441478125",
    )

    response = _sync(api_client, _book_payload(identifiers=[identifier]))

    result = response.json()["results"][0]
    assert result["action"] == "matched"
    assert result["book"] == book.slug
    assert Book.all_objects.count() == 1
    read = book.reads.get()
    assert read.koreader_md5 == MD5


def test_koreader_sync_matches_by_isbn10(api_client):
    book = BookFactory(title="Different Title", isbn10="097522980X")

    response = _sync(api_client, _book_payload(identifiers=["isbn:0-9752298-0-x"]))

    assert response.json()["results"][0]["book"] == book.slug
    assert Book.all_objects.count() == 1


def test_koreader_sync_matches_by_slug_without_mutating_the_book(api_client):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    book = BookFactory(
        title="The Left Hand of Darkness",
        title_slug="the-left-hand-of-darkness",
        primary_author=author,
        status=BookStatus.TO_READ,
        pages=286,
    )

    response = _sync(api_client, _book_payload(identifiers=[]))

    result = response.json()["results"][0]
    assert result["action"] == "matched"
    assert result["book"] == book.slug
    assert result["warnings"] == ["no ISBN found; matched by title/author"]
    assert Book.all_objects.count() == 1
    book.refresh_from_db()
    # queue_for_review's status bump is the only allowed mutation.
    assert book.status == BookStatus.TO_REVIEW
    assert book.pages == 286
    assert book.source is None
    assert book.isbn13 is None


def test_koreader_sync_without_authors_files_under_unknown(api_client):
    response = _sync(api_client, _book_payload(authors=[], identifiers=[]))

    result = response.json()["results"][0]
    assert result["action"] == "created_book"
    assert result["warnings"] == [
        "no ISBN found; matched by title/author",
        "no author in metadata; filed under 'Unknown'",
    ]
    assert Book.all_objects.get().primary_author.name == "Unknown"


# --- Read upsert ----------------------------------------------------------------


def test_koreader_sync_repush_updates_read_in_place(api_client):
    """Highlights get reviewed after finishing: a re-push with the same
    (md5, finished_on) replaces the blob and stats instead of duplicating."""
    first = _sync(api_client, _book_payload())
    new_highlights = [HIGHLIGHT, {**HIGHLIGHT, "text": "Second pass.", "note": "!"}]

    response = _sync(
        api_client,
        _book_payload(
            highlights=new_highlights,
            total_time_seconds=30000,
            summary_note="Loved it.",
        ),
    )

    result = response.json()["results"][0]
    assert result["action"] == "updated_read"
    assert result["read_id"] == first.json()["results"][0]["read_id"]
    assert result["highlights_stored"] == 2
    assert Book.all_objects.count() == 1
    read = Read.objects.get()
    assert read.highlights == new_highlights
    assert read.total_time_seconds == 30000
    assert read.notes == "Loved it."


def test_koreader_sync_repush_without_note_keeps_existing_notes(api_client):
    _sync(api_client, _book_payload(summary_note="Loved it."))

    _sync(api_client, _book_payload(summary_note=None))

    assert Read.objects.get().notes == "Loved it."


def test_koreader_sync_adopts_manually_logged_read(api_client):
    """A read logged manually before the device pushed gets the device data
    attached instead of a same-day duplicate; manual notes win."""
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    book = BookFactory(
        title="The Left Hand of Darkness",
        title_slug="the-left-hand-of-darkness",
        primary_author=author,
        status=BookStatus.TO_REVIEW,
    )
    read = ReadFactory(
        book=book, finished_on=dt.date(2026, 7, 1), source="manual", notes="On paper?"
    )

    response = _sync(api_client, _book_payload(summary_note="Device note."))

    result = response.json()["results"][0]
    assert result["action"] == "updated_read"
    assert result["read_id"] == read.pk
    assert book.reads.count() == 1
    read.refresh_from_db()
    assert read.koreader_md5 == MD5
    assert read.highlights == [HIGHLIGHT]
    assert read.total_time_seconds == 25440
    assert read.started_on == dt.date(2026, 6, 12)
    assert read.format == "ebook"
    assert read.notes == "On paper?"
    assert read.source == "manual"


def test_koreader_sync_reread_creates_second_read_and_requeues(api_client):
    """A reread gets a new summary.modified date on the device, so the server
    sees a new (md5, finished_on): a second Read that bumps the feed date and
    puts the published book back in the review queue."""
    book = make_reviewed_book(
        title="The Left Hand of Darkness",
        title_slug="the-left-hand-of-darkness",
        primary_author=AuthorFactory(
            name="Ursula K. Le Guin", name_slug="ursula-k-le-guin"
        ),
        reads=[],
    )
    ReadFactory(book=book, finished_on=dt.date(2020, 1, 1), koreader_md5=MD5)
    Book.all_objects.filter(pk=book.pk).update(
        feed_date=dt.date(2020, 1, 1), review_updated=dt.date(2020, 1, 2)
    )

    response = _sync(api_client, _book_payload(finished_on="2026-07-01"))

    result = response.json()["results"][0]
    assert result["action"] == "matched"
    assert sorted(read.finished_on for read in book.reads.all()) == [
        dt.date(2020, 1, 1),
        dt.date(2026, 7, 1),
    ]
    book.refresh_from_db()
    assert book.feed_date == now().date()
    assert list(Book.all_objects.needs_review()) == [book]


def test_koreader_sync_abandoned_book_creates_dnf_read(api_client):
    response = _sync(api_client, _book_payload(status="abandoned", highlights=[]))

    assert response.json()["results"][0]["highlights_stored"] == 0
    read = Read.objects.get()
    assert read.did_not_finish is True
    assert read.highlights is None


def test_koreader_sync_rating_and_note_never_touch_book_rating(api_client):
    response = _sync(
        api_client, _book_payload(rating=5, summary_note="Best Hainish novel.")
    )

    assert response.status_code == 200
    read = Read.objects.get()
    assert read.notes == "Best Hainish novel.\n\nKOReader rating: 5/5"
    assert read.book.rating is None


# --- Batching -------------------------------------------------------------------


def test_koreader_sync_batch_is_all_or_nothing(api_client):
    """One unprocessable book (its title slugifies to nothing) fails the
    whole batch with a 422: the good book that preceded it is rolled back,
    and every failing book is reported."""
    bad_md5 = "b" * 32

    response = _sync(
        api_client,
        _book_payload(),
        _book_payload(md5=bad_md5, title="!!!", identifiers=[]),
        _book_payload(md5="c" * 32, title="???", identifiers=[]),
    )

    assert response.status_code == 422
    first_error, second_error = response.json()["results"]
    assert first_error["md5"] == bad_md5
    assert first_error["action"] == "error"
    assert first_error["detail"]
    assert first_error["read_id"] is None
    assert second_error["md5"] == "c" * 32
    assert second_error["action"] == "error"
    assert not Book.all_objects.exists()
    assert not Read.objects.exists()


def test_koreader_sync_batch_updates_and_creates_in_one_push(api_client):
    _sync(api_client, _book_payload())

    response = _sync(
        api_client,
        _book_payload(),
        _book_payload(
            md5="c" * 32,
            title="The Dispossessed",
            identifiers=[],
            series=None,
            series_index=None,
        ),
    )

    actions = [result["action"] for result in response.json()["results"]]
    assert actions == ["updated_read", "created_book"]
    assert Book.all_objects.count() == 2
    assert Series.objects.count() == 1
    assert Author.objects.count() == 1


# --- Highlights downstream ------------------------------------------------------


def test_koreader_highlights_show_up_in_queue_and_read_detail(api_client):
    """The review queue and the reads API carry the highlight blob to the
    CLI and AI-drafting consumers."""
    _sync(api_client, _book_payload())
    read = Read.objects.get()

    queue = api_client.get("/api/queue/").json()
    patched = api_client.patch(
        f"/api/reads/{read.pk}/", {}, content_type="application/json"
    ).json()

    assert queue[0]["reads"] == [
        {
            "id": read.pk,
            "date": "2026-07-01",
            "notes": None,
            "highlights": [HIGHLIGHT],
        }
    ]
    assert patched["highlights"] == [HIGHLIGHT]
