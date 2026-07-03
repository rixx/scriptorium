import datetime as dt

import pytest
from django.utils.timezone import now

from scriptorium.main.models import Author, Book, BookStatus, Series
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


def test_queue_requires_token(client, api_token):
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


# --- Add to queue -------------------------------------------------------------


def _queue_payload(**overrides):
    payload = {
        "title": "The Tombs of Atuan",
        "author_name": "Ursula K. Le Guin",
        "series": "Earthsea",
        "series_position": "2",
        "date_read": "2024-05-01",
        "notes": "Read at the beach.",
    }
    payload.update(overrides)
    return payload


def test_queue_add_requires_token(client, api_token):

    response = client.post(
        "/api/queue/", _queue_payload(), content_type="application/json"
    )

    assert response.status_code == 401
    assert Book.all_objects.count() == 0


def test_queue_add_creates_author_series_book_and_read(api_client):
    response = api_client.post(
        "/api/queue/", _queue_payload(), content_type="application/json"
    )

    assert response.status_code == 201
    book = Book.all_objects.get()
    assert response.json() == {
        "id": book.pk,
        "slug": "ursula-k-le-guin/the-tombs-of-atuan",
        "title": "The Tombs of Atuan",
        "author": "Ursula K. Le Guin",
        "series": "Earthsea",
        "series_position": "2",
        "status": "to_review",
        "date": "2024-05-01",
        "why": "unreviewed",
        "reads": [{"date": "2024-05-01", "notes": "Read at the beach."}],
        "queued": True,
    }
    assert book.status == BookStatus.TO_REVIEW
    assert book.series.name_slug == "earthsea"
    read = book.reads.get()
    assert read.finished_on == dt.date(2024, 5, 1)
    assert read.source == "manual"
    assert read.notes == "Read at the beach."


def test_queue_add_without_read_date_creates_unread_queue_item(api_client):
    response = api_client.post(
        "/api/queue/",
        {"title": "Piranesi", "author_name": "Susanna Clarke"},
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["date"] is None
    assert data["reads"] == []
    assert data["series"] is None
    book = Book.all_objects.get()
    assert book.status == BookStatus.TO_REVIEW
    assert book.reads.count() == 0


def test_queue_add_reuses_author_and_series_by_slug(api_client):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    series = SeriesFactory(name="Earthsea", name_slug="earthsea")

    response = api_client.post(
        "/api/queue/",
        _queue_payload(author_name="ursula k. le guin", series="EARTHSEA"),
        content_type="application/json",
    )

    assert response.status_code == 201
    book = Book.all_objects.get()
    assert book.primary_author == author
    assert book.series == series
    assert Author.objects.count() == 1
    assert Series.objects.count() == 1


def test_queue_add_promotes_queued_to_read_book(api_client):
    book = BookFactory(
        title="The Tombs of Atuan",
        title_slug="the-tombs-of-atuan",
        primary_author=AuthorFactory(
            name="Ursula K. Le Guin", name_slug="ursula-k-le-guin"
        ),
        status=BookStatus.TO_READ,
    )

    response = api_client.post(
        "/api/queue/", _queue_payload(), content_type="application/json"
    )

    assert response.status_code == 201
    assert Book.all_objects.count() == 1
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW
    assert [read.finished_on for read in book.reads.all()] == [dt.date(2024, 5, 1)]


def test_queue_add_duplicate_date_updates_notes_and_returns_200(api_client):
    """Re-submitting an already logged date must not silently discard the
    submitted notes: the existing read is updated instead of duplicated, and
    the response says 200 (nothing new was created)."""
    api_client.post(
        "/api/queue/",
        _queue_payload(notes="First impression."),
        content_type="application/json",
    )

    response = api_client.post(
        "/api/queue/",
        _queue_payload(notes="Corrected note."),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["queued"] is True
    book = Book.all_objects.get()
    read = book.reads.get()
    assert read.finished_on == dt.date(2024, 5, 1)
    assert read.notes == "Corrected note."
    assert read.source == "manual"


def test_queue_add_reviewed_book_with_date_queues_reread(api_client):
    book = make_reviewed_book(
        title="Reread Me", title_slug="reread-me", latest_date=dt.date(2020, 1, 1)
    )
    # Backdate the review so the new read is genuinely newer than it.
    Book.all_objects.filter(pk=book.pk).update(review_updated=dt.date(2020, 1, 2))

    response = api_client.post(
        "/api/queue/",
        _queue_payload(title="Reread Me", author_name=book.primary_author.name),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["why"] == "reread"
    assert data["status"] == "reviewed"
    assert data["queued"] is True
    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert sorted(read.finished_on for read in book.reads.all()) == [
        dt.date(2020, 1, 1),
        dt.date(2024, 5, 1),
    ]


def test_queue_add_reviewed_book_without_date_is_refused_without_side_effects(
    api_client,
):
    book = make_reviewed_book(title="Reread Me", title_slug="reread-me")

    response = api_client.post(
        "/api/queue/",
        {
            "title": "Reread Me",
            "author_name": book.primary_author.name,
            "series": "Brand New Series",
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    assert list(response.json()) == ["detail"]
    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert book.reads.count() == 1
    # The refusal happens before anything is created.
    assert Series.objects.count() == 0
    assert Author.objects.count() == 1


def test_queue_add_backfilled_old_read_reports_queued_false(api_client):
    """Logging a read that predates the review keeps the book out of the
    queue; the response's ``queued`` field is honest about that."""
    book = make_reviewed_book(
        title="Backfill", title_slug="backfill", latest_date=dt.date(2024, 6, 15)
    )

    response = api_client.post(
        "/api/queue/",
        _queue_payload(
            title="Backfill",
            author_name=book.primary_author.name,
            date_read="2020-01-01",
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["queued"] is False
    assert data["status"] == "reviewed"
    assert book.reads.count() == 2
    assert not Book.all_objects.needs_review().filter(pk=book.pk).exists()


def test_queue_add_stores_shelf_on_new_books(api_client):
    response = api_client.post(
        "/api/queue/",
        _queue_payload(shelf="beach reads"),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Book.all_objects.get().shelf == "beach reads"


def test_queue_add_requires_title(api_client):
    response = api_client.post(
        "/api/queue/", {"author_name": "Nobody"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "payload", "title"]
    assert Book.all_objects.count() == 0


# --- Dismiss ------------------------------------------------------------------


def test_queue_dismiss_clears_reread_from_queue(api_client):
    book = make_stale_reread(
        title="Old Favourite",
        latest_date=dt.date(2024, 2, 2),
        review_updated=dt.date(2020, 1, 1),
    )
    assert [item["id"] for item in api_client.get("/api/queue/").json()] == [book.pk]

    response = api_client.post(f"/api/queue/{book.pk}/dismiss/")

    assert response.status_code == 204
    book.refresh_from_db()
    assert book.review_updated == now().date()
    assert api_client.get("/api/queue/").json() == []


def test_queue_dismiss_rejects_unreviewed_books(api_client):
    book = BookFactory(title="Needs a review", status=BookStatus.TO_REVIEW)
    ReadFactory(book=book, finished_on=dt.date(2024, 5, 1))

    response = api_client.post(f"/api/queue/{book.pk}/dismiss/")

    assert response.status_code == 404
    assert [item["id"] for item in api_client.get("/api/queue/").json()] == [book.pk]


def test_queue_dismiss_requires_token(client, api_token):
    book = make_stale_reread(
        title="Old Favourite",
        latest_date=dt.date(2024, 2, 2),
        review_updated=dt.date(2020, 1, 1),
    )

    response = client.post(f"/api/queue/{book.pk}/dismiss/")

    assert response.status_code == 401
    book.refresh_from_db()
    assert book.review_updated == dt.date(2020, 1, 1)


# --- Query counts ---------------------------------------------------------------


@pytest.mark.parametrize("item_count", [1, 3])
def test_queue_list_query_count_is_constant(
    api_client, django_assert_num_queries, item_count
):
    for index in range(item_count):
        book = BookFactory(title=f"Queued {index}", status=BookStatus.TO_REVIEW)
        book.additional_authors.add(AuthorFactory())
        ReadFactory(book=book, finished_on=dt.date(2024, 5, 1 + index))

    # Warm the auth throttle so only the token lookup itself is counted.
    api_client.get("/api/books/")

    with django_assert_num_queries(4):
        response = api_client.get("/api/queue/")

    items = response.json()
    assert len(items) == item_count
    assert all(" & " in item["author"] for item in items)
    assert all(len(item["reads"]) == 1 for item in items)
