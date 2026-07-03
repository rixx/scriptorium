import datetime as dt

import pytest

from scriptorium.main.models import Book, BookStatus
from tests.factories import (
    AuthorFactory,
    BookFactory,
    ReadFactory,
    SeriesFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


def make_stale_reread(latest_date, review_updated, **book_kwargs):
    """A published book whose latest read is newer than its review text --
    Book.save() stamps review_updated with today, so tests backdate it via a
    queryset update, like the feed_date tests do."""
    book = make_reviewed_book(latest_date=latest_date, **book_kwargs)
    Book.all_objects.filter(pk=book.pk).update(review_updated=review_updated)
    return book


def test_queue_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    BookFactory(title="Waiting", status=BookStatus.TO_REVIEW)

    response = client.get("/api/queue/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_queue_lists_unreviewed_and_stale_rereads_oldest_first(api_client):
    author = AuthorFactory(name="Susanna Clarke", name_slug="susanna-clarke")
    unreviewed = BookFactory(
        title="Piranesi",
        title_slug="piranesi",
        primary_author=author,
        series=SeriesFactory(name="Standalone"),
        series_position="1",
        status=BookStatus.TO_REVIEW,
    )
    ReadFactory(
        book=unreviewed, finished_on=dt.date(2024, 5, 1), notes="Loved the halls."
    )
    reread = make_stale_reread(
        title="Old Favourite",
        title_slug="old-favourite",
        latest_date=dt.date(2024, 2, 2),
        review_updated=dt.date(2020, 1, 1),
    )
    # Fresh review (review_updated is today, newer than any read): not queued.
    make_reviewed_book(title="Fresh", latest_date=dt.date(2024, 6, 1))
    # Not read yet: not in the review queue either.
    BookFactory(title="On the pile", status=BookStatus.TO_READ)

    response = api_client.get("/api/queue/")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": reread.pk,
            "slug": reread.slug,
            "title": "Old Favourite",
            "author": reread.primary_author.name,
            "series": None,
            "series_position": None,
            "status": "reviewed",
            "date": "2024-02-02",
            "why": "reread",
            "reads": [{"date": "2024-02-02", "notes": None}],
        },
        {
            "id": unreviewed.pk,
            "slug": "susanna-clarke/piranesi",
            "title": "Piranesi",
            "author": "Susanna Clarke",
            "series": "Standalone",
            "series_position": "1",
            "status": "to_review",
            "date": "2024-05-01",
            "why": "unreviewed",
            "reads": [{"date": "2024-05-01", "notes": "Loved the halls."}],
        },
    ]


def test_queue_puts_books_without_reads_first(api_client):
    read_book = BookFactory(title="Read but unlogged?", status=BookStatus.TO_REVIEW)
    ReadFactory(book=read_book, finished_on=dt.date(2024, 5, 1))
    BookFactory(title="No read recorded", status=BookStatus.TO_REVIEW)

    response = api_client.get("/api/queue/")

    items = response.json()
    assert [item["title"] for item in items] == [
        "No read recorded",
        "Read but unlogged?",
    ]
    assert items[0]["date"] is None
    assert items[0]["reads"] == []


def test_queue_next_returns_oldest_item(api_client):
    BookFactory(title="Newer", status=BookStatus.TO_REVIEW).reads.create(
        finished_on=dt.date(2024, 5, 1)
    )
    oldest = make_stale_reread(
        title="Oldest",
        latest_date=dt.date(2023, 3, 3),
        review_updated=dt.date(2022, 1, 1),
    )

    response = api_client.get("/api/queue/next/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == oldest.pk
    assert data["title"] == "Oldest"
    assert data["why"] == "reread"
    assert data["date"] == "2023-03-03"


def test_queue_next_returns_404_when_queue_is_empty(api_client):
    make_reviewed_book(title="Fresh", latest_date=dt.date(2024, 6, 1))

    response = api_client.get("/api/queue/next/")

    assert response.status_code == 404
    assert response.json() == {"detail": "The review queue is empty."}
