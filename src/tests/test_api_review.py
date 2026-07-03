import datetime as dt

import pytest
from django.utils.timezone import now

from scriptorium.main.models import Book, BookStatus, Quote, Tag
from tests.factories import (
    AuthorFactory,
    BookFactory,
    ReadFactory,
    SeriesFactory,
    TagFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


def _payload(**overrides):
    payload = {
        "text": "A thoughtful review.",
        "tldr": "Read it.",
        "rating": 4,
        "dates_read": ["2024-05-02"],
    }
    payload.update(overrides)
    return payload


def _queued_book(**kwargs):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    return BookFactory(
        title="The Word for World Is Forest",
        title_slug="the-word-for-world-is-forest",
        primary_author=author,
        status=BookStatus.TO_REVIEW,
        **kwargs,
    )


def _url(book):
    return f"/api/books/{book.slug}/review/"


def test_review_submit_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    book = _queued_book()

    response = client.post(_url(book), _payload(), content_type="application/json")

    assert response.status_code == 401
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW


def test_review_submit_unknown_book_returns_404(api_client):
    response = api_client.post(
        "/api/books/nobody/nothing/review/", _payload(), content_type="application/json"
    )

    assert response.status_code == 404


def test_review_submit_publishes_queued_book_with_metadata_and_quotes(api_client):
    book = _queued_book(pages=None)
    ReadFactory(book=book, finished_on=dt.date(2024, 2, 1), notes="Queued read.")

    response = api_client.post(
        _url(book),
        _payload(
            dates_read=["2024-02-01", "2024-05-02"],
            metadata={
                "pages": 189,
                "publication_year": 1972,
                "series": "Hainish Cycle",
                "series_position": "5",
                "isbn13": "9780765324641",
                "openlibrary_id": "OL7101487W",
                "tags": ["genre:science-fiction"],
            },
            quotes=[
                {"text": "The forest quote.", "language": "en", "order": 1},
                {"text": "Das Waldzitat.", "language": "de", "order": 2},
            ],
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reviewed"
    assert (
        data["url"]
        == "http://testserver/ursula-k-le-guin/the-word-for-world-is-forest/"
    )
    assert data["text"] == "A thoughtful review."
    assert data["tldr"] == "Read it."
    assert data["rating"] == 4
    assert data["pages"] == 189
    assert data["series"] == "Hainish Cycle"
    assert data["tags"] == ["genre:science-fiction"]
    assert data["quotes_count"] == 2
    assert [read["date"] for read in data["reads"]] == ["2024-05-02", "2024-02-01"]
    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert book.feed_date == now().date()
    assert book.review_updated == now().date()
    assert book.isbn13 == "9780765324641"
    assert book.series.name_slug == "hainish-cycle"
    # The queued read was kept (with its notes), only the new date was added.
    assert book.reads.get(finished_on=dt.date(2024, 2, 1)).notes == "Queued read."
    assert book.reads.count() == 2
    assert [(quote.text, quote.language) for quote in book.quotes.all()] == [
        ("The forest quote.", "en"),
        ("Das Waldzitat.", "de"),
    ]


def test_review_submit_minimal_payload_keeps_existing_fields(api_client):
    book = _queued_book(tldr="Kept.", rating=3)

    response = api_client.post(
        _url(book),
        {"text": "Just the text.", "dates_read": ["2024-05-02"]},
        content_type="application/json",
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert book.text == "Just the text."
    assert book.tldr == "Kept."
    assert book.rating == 3


def test_review_submit_metadata_blanks_keep_queued_values(api_client):
    series = SeriesFactory(name="Hainish Cycle", name_slug="hainish-cycle")
    book = _queued_book(series=series, series_position="5")

    response = api_client.post(
        _url(book),
        _payload(metadata={"series": None, "pages": 300}),
        content_type="application/json",
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.series == series
    assert book.series_position == "5"
    assert book.pages == 300


def test_review_submit_refuses_published_review_without_overwrite(api_client):
    book = make_reviewed_book(title="Published", text="Original review.")

    response = api_client.post(
        _url(book),
        _payload(text="Sneaky overwrite.", quotes=[{"text": "New quote."}]),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert list(response.json()) == ["detail"]
    book.refresh_from_db()
    assert book.text == "Original review."
    assert Quote.objects.count() == 0


def test_review_submit_overwrite_replaces_published_review(api_client):
    book = make_reviewed_book(
        title="Published", text="Original review.", latest_date=dt.date(2024, 6, 15)
    )
    Book.all_objects.filter(pk=book.pk).update(
        review_updated=dt.date(2020, 1, 1), feed_date=dt.date(2020, 1, 2)
    )

    response = api_client.post(
        _url(book),
        _payload(text="Fresh take.", dates_read=["2024-06-15"], overwrite=True),
        content_type="application/json",
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert book.text == "Fresh take."
    assert book.review_updated == now().date()
    # No new read was logged, so the review does not re-enter the feed.
    assert book.feed_date == dt.date(2020, 1, 2)
    assert book.reads.count() == 1


def test_review_submit_overwrite_with_identical_text_clears_reread_queue(api_client):
    """Republishing an unchanged review is a deliberate "the review still
    stands" action: Book.save() alone wouldn't stamp review_updated (the text
    didn't change), but the book must still leave the reread queue."""
    book = make_reviewed_book(text="Same text.", latest_date=dt.date(2024, 6, 15))
    Book.all_objects.filter(pk=book.pk).update(review_updated=dt.date(2020, 1, 1))
    assert Book.all_objects.needs_review().filter(pk=book.pk).exists()

    response = api_client.post(
        _url(book),
        _payload(text="Same text.", dates_read=["2024-06-15"], overwrite=True),
        content_type="application/json",
    )

    assert response.status_code == 200
    book.refresh_from_db()
    assert book.text == "Same text."
    assert book.review_updated == now().date()
    assert not Book.all_objects.needs_review().filter(pk=book.pk).exists()


def test_review_submit_invalid_metadata_returns_400_and_rolls_back(api_client):
    book = _queued_book()

    response = api_client.post(
        _url(book),
        _payload(metadata={"isbn13": "9" * 31}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "isbn13" in response.json()["detail"]
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW
    assert book.isbn13 is None
    assert book.reads.count() == 0


def test_review_submit_did_not_finish_flags_new_reads(api_client):
    book = _queued_book()

    response = api_client.post(
        _url(book), _payload(did_not_finish=True), content_type="application/json"
    )

    assert response.status_code == 200
    read = book.reads.get()
    assert read.finished_on == dt.date(2024, 5, 2)
    assert read.did_not_finish is True


def test_review_submit_reuses_existing_tags(api_client):
    tag = TagFactory(category="genre", name_slug="science-fiction")
    book = _queued_book()

    response = api_client.post(
        _url(book),
        _payload(metadata={"tags": ["genre:science-fiction"]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert list(book.tags.all()) == [tag]
    assert Tag.objects.count() == 1


def test_review_submit_failing_quote_rolls_back_everything(api_client):
    book = _queued_book()

    response = api_client.post(
        _url(book),
        _payload(
            metadata={"tags": ["genre:science-fiction"]},
            quotes=[{"text": "Fine quote."}, {"text": ""}],
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "text" in response.json()["detail"]
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW
    assert book.text is None
    assert book.reads.count() == 0
    assert book.tags.count() == 0
    assert Quote.objects.count() == 0
    assert Tag.objects.count() == 0


@pytest.mark.parametrize("spec", ["nocolon", "bogus:slug", "genre:"])
def test_review_submit_invalid_tag_returns_400(api_client, spec):
    book = _queued_book()

    response = api_client.post(
        _url(book), _payload(metadata={"tags": [spec]}), content_type="application/json"
    )

    assert response.status_code == 400
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW
    assert book.text is None
    assert Tag.objects.count() == 0


@pytest.mark.parametrize(
    ("field", "value"), [("text", ""), ("rating", 6), ("dates_read", [])]
)
def test_review_submit_validation_errors(api_client, field, value):
    book = _queued_book()

    response = api_client.post(
        _url(book), _payload(**{field: value}), content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field
    book.refresh_from_db()
    assert book.status == BookStatus.TO_REVIEW
