import datetime as dt

import pytest
from django.utils.timezone import now

from scriptorium.main.models import Book, BookStatus
from tests.factories import BookFactory, ReadFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


def _reads_url(book):
    return f"/api/books/{book.slug}/reads/"


def test_reads_create_requires_token(client, api_token):
    book = BookFactory(status=BookStatus.TO_REVIEW)

    response = client.post(
        _reads_url(book), {"date": "2024-05-01"}, content_type="application/json"
    )

    assert response.status_code == 401
    assert book.reads.count() == 0


def test_reads_create_unknown_book_returns_404(api_client):
    response = api_client.post(
        "/api/books/nobody/nothing/reads/",
        {"date": "2024-05-01"},
        content_type="application/json",
    )

    assert response.status_code == 404


def test_reads_create_logs_read_with_metadata(api_client):
    book = BookFactory(status=BookStatus.TO_REVIEW)

    response = api_client.post(
        _reads_url(book),
        {
            "date": "2024-05-01",
            "started_on": "2024-04-20",
            "format": "audio",
            "source": "koreader",
            "notes": "Slow start.",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    read = book.reads.get()
    assert response.json() == {
        "id": read.pk,
        "book": book.slug,
        "date": "2024-05-01",
        "started_on": "2024-04-20",
        "format": "audio",
        "source": "koreader",
        "notes": "Slow start.",
        "did_not_finish": False,
        "highlights": None,
    }
    assert read.finished_on == dt.date(2024, 5, 1)
    assert read.started_on == dt.date(2024, 4, 20)
    assert read.format == "audio"
    assert read.source == "koreader"
    assert read.did_not_finish is False


def test_reads_create_deduplicates_by_date(api_client):
    book = BookFactory(status=BookStatus.TO_REVIEW)
    existing = ReadFactory(
        book=book, finished_on=dt.date(2024, 5, 1), notes="Original."
    )

    response = api_client.post(
        _reads_url(book),
        {"date": "2024-05-01", "notes": "Duplicate."},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["id"] == existing.pk
    read = book.reads.get()
    assert read.notes == "Original."


def test_reads_create_new_latest_read_bumps_feed_date(api_client):
    book = make_reviewed_book(latest_date=dt.date(2023, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2023, 1, 1))

    response = api_client.post(
        _reads_url(book), {"date": "2024-05-01"}, content_type="application/json"
    )

    assert response.status_code == 201
    book.refresh_from_db()
    assert book.feed_date == now().date()


def test_reads_create_backfilled_read_keeps_feed_date(api_client):
    book = make_reviewed_book(latest_date=dt.date(2023, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2023, 1, 1))

    response = api_client.post(
        _reads_url(book), {"date": "2020-05-01"}, content_type="application/json"
    )

    assert response.status_code == 201
    book.refresh_from_db()
    assert book.feed_date == dt.date(2023, 1, 1)
    assert book.reads.count() == 2


def test_reads_create_rejects_unknown_format(api_client):
    book = BookFactory(status=BookStatus.TO_REVIEW)

    response = api_client.post(
        _reads_url(book),
        {"date": "2024-05-01", "format": "vinyl"},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert book.reads.count() == 0


def test_reads_patch_updates_fields_without_bumping_feed(api_client):
    book = make_reviewed_book(latest_date=dt.date(2023, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2023, 1, 1))
    read = book.reads.get()

    response = api_client.patch(
        f"/api/reads/{read.pk}/",
        {
            "date": "2024-05-01",
            "format": "paper",
            "notes": "Corrected.",
            "did_not_finish": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    read.refresh_from_db()
    assert read.finished_on == dt.date(2024, 5, 1)
    assert read.format == "paper"
    assert read.notes == "Corrected."
    assert read.did_not_finish is True
    book.refresh_from_db()
    # Corrections are not rereads: the book does not re-enter the feed.
    assert book.feed_date == dt.date(2023, 1, 1)


def test_reads_patch_backfills_start_date_and_reading_time(api_client):
    """The KOReader-statistics backfill path: started_on and
    total_time_seconds land on an existing read and are echoed back."""
    read = ReadFactory(book=BookFactory(status=BookStatus.TO_REVIEW))

    response = api_client.patch(
        f"/api/reads/{read.pk}/",
        {"started_on": "2024-06-01", "total_time_seconds": 12345},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["started_on"] == "2024-06-01"
    assert data["total_time_seconds"] == 12345
    read.refresh_from_db()
    assert read.started_on == dt.date(2024, 6, 1)
    assert read.total_time_seconds == 12345


def test_reads_patch_can_update_notes_only(api_client):
    read = ReadFactory(book=BookFactory(status=BookStatus.TO_REVIEW), notes=None)

    response = api_client.patch(
        f"/api/reads/{read.pk}/",
        {"notes": "Late note."},
        content_type="application/json",
    )

    assert response.status_code == 200
    read.refresh_from_db()
    assert read.notes == "Late note."
    assert read.finished_on == dt.date(2024, 6, 15)


def test_reads_patch_overlong_source_returns_400(api_client):
    read = ReadFactory(source="library")

    response = api_client.patch(
        f"/api/reads/{read.pk}/", {"source": "x" * 301}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "source" in response.json()["detail"]
    read.refresh_from_db()
    assert read.source == "library"


def test_reads_patch_unknown_read_returns_404(api_client):
    response = api_client.patch(
        "/api/reads/999/", {"notes": "x"}, content_type="application/json"
    )

    assert response.status_code == 404


def test_reads_delete_removes_read_and_keeps_feed_date(api_client):
    book = make_reviewed_book(reads=[dt.date(2023, 1, 1), dt.date(2024, 2, 2)])
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2024, 2, 2))
    read = book.reads.get(finished_on=dt.date(2024, 2, 2))

    response = api_client.delete(f"/api/reads/{read.pk}/")

    assert response.status_code == 204
    assert [r.finished_on for r in book.reads.all()] == [dt.date(2023, 1, 1)]
    book.refresh_from_db()
    assert book.feed_date == dt.date(2024, 2, 2)


def test_reads_delete_unknown_read_returns_404(api_client):
    response = api_client.delete("/api/reads/999/")

    assert response.status_code == 404
