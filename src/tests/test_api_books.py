import datetime as dt

import pytest
from django.test import Client
from django.utils.timezone import now

from scriptorium.main.models import Book, BookStatus, Tag
from tests.factories import (
    AuthorFactory,
    BookFactory,
    QuoteFactory,
    ReadFactory,
    SeriesFactory,
    TagFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


# --- Auth ---------------------------------------------------------------------


def test_api_rejects_request_without_token(client, settings):
    settings.API_KEY = "test-api-key"
    make_reviewed_book(title="Secret")

    response = client.get("/api/books/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_api_rejects_request_with_wrong_token(settings):
    settings.API_KEY = "test-api-key"
    make_reviewed_book(title="Secret")

    client = Client(headers={"Authorization": "Bearer wrong-key"})
    response = client.get("/api/books/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_api_accepts_request_with_configured_token(api_client):
    response = api_client.get("/api/books/")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


# --- Book list ------------------------------------------------------------------


def test_books_list_returns_published_books_with_metadata(api_client):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    book = make_reviewed_book(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=author,
        series=SeriesFactory(name="Hainish Cycle"),
        series_position="5",
        rating=5,
        tldr="Competing utopias.",
        pages=341,
        latest_date=dt.date(2024, 3, 14),
    )
    book.tags.add(TagFactory(category="genre", name="Science Fiction"))
    BookFactory(title="Not yet read", status=BookStatus.TO_READ)

    response = api_client.get("/api/books/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"] == [
        {
            "id": book.pk,
            "title": "The Dispossessed",
            "slug": "ursula-k-le-guin/the-dispossessed",
            "authors": ["Ursula K. Le Guin"],
            "series": "Hainish Cycle",
            "series_position": "5",
            "rating": 5,
            "tldr": "Competing utopias.",
            "status": "reviewed",
            "latest_read": "2024-03-14",
            "pages": 341,
            "tags": ["genre:Science Fiction"],
        }
    ]


def test_books_list_search_matches_title(api_client):
    make_reviewed_book(title="The Dispossessed")
    make_reviewed_book(title="Piranesi")

    response = api_client.get("/api/books/", {"q": "piranesi"})

    assert [item["title"] for item in response.json()["items"]] == ["Piranesi"]


def test_books_list_search_matches_primary_author(api_client):
    author = AuthorFactory(name="Susanna Clarke", name_slug="susanna-clarke")
    make_reviewed_book(title="Piranesi", primary_author=author)
    make_reviewed_book(title="The Dispossessed")

    response = api_client.get("/api/books/", {"q": "clarke"})

    assert [item["title"] for item in response.json()["items"]] == ["Piranesi"]


def test_books_list_search_matches_additional_author(api_client):
    book = make_reviewed_book(title="Good Omens")
    book.additional_authors.add(
        AuthorFactory(name="Terry Pratchett", name_slug="terry-pratchett")
    )
    make_reviewed_book(title="Piranesi")

    response = api_client.get("/api/books/", {"q": "pratchett"})

    assert [item["title"] for item in response.json()["items"]] == ["Good Omens"]


def test_books_list_status_filter_shows_unpublished_books(api_client):
    make_reviewed_book(title="Published")
    BookFactory(title="On the pile", status=BookStatus.TO_READ)

    response = api_client.get("/api/books/", {"status": "to_read"})

    items = response.json()["items"]
    assert [item["title"] for item in items] == ["On the pile"]
    assert items[0]["status"] == "to_read"
    assert items[0]["series"] is None
    assert items[0]["latest_read"] is None


def test_books_list_year_filter_matches_read_year(api_client):
    make_reviewed_book(title="Old Read", latest_date=dt.date(2023, 5, 1))
    # Read twice in the filter year: must show up exactly once.
    make_reviewed_book(
        title="Reread",
        reads=[dt.date(2023, 8, 1), dt.date(2023, 12, 24), dt.date(2024, 2, 2)],
    )
    make_reviewed_book(title="New Read", latest_date=dt.date(2024, 6, 1))

    response = api_client.get("/api/books/", {"year": 2023})

    titles = sorted(item["title"] for item in response.json()["items"])
    assert titles == ["Old Read", "Reread"]


def test_books_list_paginates_with_limit_and_offset(api_client):
    author = AuthorFactory(name="Writer", name_slug="writer")
    for index in range(3):
        make_reviewed_book(
            title=f"Book {index}", title_slug=f"book-{index}", primary_author=author
        )

    response = api_client.get("/api/books/", {"limit": 2, "offset": 2})

    data = response.json()
    assert data["count"] == 3
    assert [item["title"] for item in data["items"]] == ["Book 2"]


# --- Book detail ---------------------------------------------------------------


def test_books_detail_returns_full_review_data(api_client):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    book = make_reviewed_book(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=author,
        series=SeriesFactory(name="Hainish Cycle"),
        series_position="5",
        rating=5,
        tldr="Competing utopias.",
        text="A brilliant exploration of competing utopias.",
        pages=341,
        isbn13="9780061054884",
        openlibrary_id="OL59802W",
        reads=[],
    )
    ReadFactory(
        book=book,
        finished_on=dt.date(2024, 3, 14),
        format="paper",
        source="library",
        notes="Holiday read.",
    )
    QuoteFactory(source_book=book, text="To be whole is to be part.")
    QuoteFactory(source_book=book, text="True journey is return.")

    response = api_client.get("/api/books/ursula-k-le-guin/the-dispossessed/")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == book.pk
    assert data["url"] == "http://testserver/ursula-k-le-guin/the-dispossessed/"
    assert data["text"] == "A brilliant exploration of competing utopias."
    assert data["reads"] == [
        {
            "date": "2024-03-14",
            "format": "paper",
            "source": "library",
            "notes": "Holiday read.",
        }
    ]
    assert data["quotes_count"] == 2
    assert data["isbn"] == "9780061054884"
    assert data["openlibrary_id"] == "OL59802W"
    assert data["tags"] == []


def test_books_detail_includes_unpublished_books(api_client):
    author = AuthorFactory(name="Susanna Clarke", name_slug="susanna-clarke")
    BookFactory(
        title="Piranesi",
        title_slug="piranesi",
        primary_author=author,
        status=BookStatus.TO_REVIEW,
    )

    response = api_client.get("/api/books/susanna-clarke/piranesi/")

    data = response.json()
    assert data["title"] == "Piranesi"
    assert data["status"] == "to_review"
    assert data["text"] is None
    assert data["reads"] == []
    assert data["quotes_count"] == 0
    assert data["isbn"] is None


def test_books_detail_unknown_slug_returns_404(api_client):
    make_reviewed_book(title="The Dispossessed")

    response = api_client.get("/api/books/nobody/nothing/")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


# --- Book patch ------------------------------------------------------------------


def _detail_url(book):
    return f"/api/books/{book.slug}/"


def test_books_patch_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    book = make_reviewed_book(title="Secret", pages=200)

    response = client.patch(
        _detail_url(book), {"pages": 1}, content_type="application/json"
    )

    assert response.status_code == 401
    book.refresh_from_db()
    assert book.pages == 200


def test_books_patch_unknown_book_returns_404(api_client):
    response = api_client.patch(
        "/api/books/nobody/nothing/", {"pages": 1}, content_type="application/json"
    )

    assert response.status_code == 404


def test_books_patch_updates_metadata(api_client):
    book = BookFactory(status=BookStatus.TO_REVIEW, pages=None)

    response = api_client.patch(
        _detail_url(book),
        {
            "pages": 341,
            "publication_year": 1974,
            "isbn13": "9780061054884",
            "openlibrary_id": "OL59802W",
            "series": "Hainish Cycle",
            "series_position": "5",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["pages"] == 341
    assert data["series"] == "Hainish Cycle"
    assert data["series_position"] == "5"
    book.refresh_from_db()
    assert book.pages == 341
    assert book.publication_year == 1974
    assert book.isbn13 == "9780061054884"
    assert book.openlibrary_id == "OL59802W"
    assert book.series.name_slug == "hainish-cycle"


def test_books_patch_text_on_published_review_stamps_review_updated(api_client):
    book = make_reviewed_book(text="Old text.")
    Book.all_objects.filter(pk=book.pk).update(
        review_updated=dt.date(2020, 1, 1), feed_date=dt.date(2020, 1, 2)
    )

    response = api_client.patch(
        _detail_url(book), {"text": "New text."}, content_type="application/json"
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.text == "New text."
    # A fresh review leaves the reread queue but does not re-enter the feed.
    assert book.review_updated == now().date()
    assert book.feed_date == dt.date(2020, 1, 2)


def test_books_patch_without_text_change_keeps_review_updated(api_client):
    book = make_reviewed_book()
    Book.all_objects.filter(pk=book.pk).update(review_updated=dt.date(2020, 1, 1))

    response = api_client.patch(
        _detail_url(book), {"tldr": "Newer."}, content_type="application/json"
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.tldr == "Newer."
    assert book.review_updated == dt.date(2020, 1, 1)


def test_books_patch_null_clears_fields(api_client):
    book = make_reviewed_book(
        series=SeriesFactory(name="Hainish Cycle"), series_position="5", rating=5
    )

    response = api_client.patch(
        _detail_url(book),
        {"series": None, "series_position": None, "rating": None},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["series"] is None
    assert data["rating"] is None
    book.refresh_from_db()
    assert book.series is None
    assert book.series_position is None
    assert book.rating is None


def test_books_patch_replaces_tags(api_client):
    book = make_reviewed_book()
    book.tags.add(TagFactory(category="genre", name_slug="old"))
    existing = TagFactory(category="themes", name="future", name_slug="future")

    response = api_client.patch(
        _detail_url(book),
        {"tags": ["themes:future", "genre:new-tag"]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert sorted(response.json()["tags"]) == ["genre:new-tag", "themes:future"]
    new_tag = Tag.objects.get(category="genre", name_slug="new-tag")
    assert set(book.tags.all()) == {existing, new_tag}
    assert Tag.objects.count() == 3  # old and future were reused, new-tag created


def test_books_patch_ignores_identity_and_status_fields(api_client):
    book = make_reviewed_book(title="Fixed Title")

    response = api_client.patch(
        _detail_url(book),
        {"title": "Sneaky", "title_slug": "sneaky", "status": "to_read", "pages": 100},
        content_type="application/json",
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.title == "Fixed Title"
    assert book.title_slug != "sneaky"
    assert book.status == BookStatus.REVIEWED
    assert book.pages == 100


def test_books_patch_invalid_tag_spec_returns_400(api_client):
    book = make_reviewed_book(pages=200)

    response = api_client.patch(
        _detail_url(book),
        {"tags": ["nocolon"], "pages": 1},
        content_type="application/json",
    )

    assert response.status_code == 400
    book.refresh_from_db()
    assert book.pages == 200
    assert book.tags.count() == 0


def test_books_patch_rating_out_of_range_returns_422(api_client):
    book = make_reviewed_book(rating=4)

    response = api_client.patch(
        _detail_url(book), {"rating": 9}, content_type="application/json"
    )

    assert response.status_code == 422
    book.refresh_from_db()
    assert book.rating == 4
