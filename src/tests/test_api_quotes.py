import pytest

from scriptorium.main.models import Quote
from tests.factories import AuthorFactory, QuoteFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


def _quotes_url(book):
    return f"/api/books/{book.slug}/quotes/"


def test_quotes_list_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    quote = QuoteFactory(source_book=make_reviewed_book(title="Secret"), text="Hidden.")

    response = client.get(_quotes_url(quote.source_book))

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_quotes_list_returns_book_quotes_in_order(api_client):
    book = make_reviewed_book(title="Quotable")
    second = QuoteFactory(source_book=book, text="Second.", order=2)
    first = QuoteFactory(source_book=book, text="First.", order=1)
    QuoteFactory(source_book=make_reviewed_book(title="Other"), text="Elsewhere.")

    response = api_client.get(_quotes_url(book))

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": first.pk,
            "text": "First.",
            "language": "en",
            "order": 1,
            "book": book.slug,
            "author": None,
        },
        {
            "id": second.pk,
            "text": "Second.",
            "language": "en",
            "order": 2,
            "book": book.slug,
            "author": None,
        },
    ]


def test_quotes_list_unknown_book_returns_404(api_client):
    response = api_client.get("/api/books/nobody/nothing/quotes/")

    assert response.status_code == 404


def test_quotes_create_links_quote_to_book(api_client):
    book = make_reviewed_book(title="Quotable")

    response = api_client.post(
        _quotes_url(book),
        {"text": "To be whole is to be part.", "language": "en", "order": 3},
        content_type="application/json",
    )

    assert response.status_code == 201
    quote = Quote.objects.get()
    assert response.json()["id"] == quote.pk
    assert quote.source_book == book
    assert quote.text == "To be whole is to be part."
    assert quote.order == 3


def test_quotes_create_with_source_author_slug(api_client):
    book = make_reviewed_book(title="Anthology")
    author = AuthorFactory(name="Mary Oliver", name_slug="mary-oliver")

    response = api_client.post(
        _quotes_url(book),
        {"text": "Attention is devotion.", "source_author": "mary-oliver"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["author"] == "mary-oliver"
    assert Quote.objects.get().source_author == author


def test_quotes_create_unknown_author_returns_400(api_client):
    book = make_reviewed_book(title="Anthology")

    response = api_client.post(
        _quotes_url(book),
        {"text": "Lost.", "source_author": "nobody"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert Quote.objects.count() == 0


def test_quotes_create_empty_text_returns_400(api_client):
    book = make_reviewed_book(title="Quotable")

    response = api_client.post(
        _quotes_url(book), {"text": ""}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "text" in response.json()["detail"]
    assert Quote.objects.count() == 0


def test_quotes_patch_updates_fields(api_client):
    quote = QuoteFactory(
        source_book=make_reviewed_book(title="Quotable"), text="Old.", order=1
    )

    response = api_client.patch(
        f"/api/quotes/{quote.pk}/",
        {"text": "New.", "language": "de", "order": 7},
        content_type="application/json",
    )

    assert response.status_code == 200
    quote.refresh_from_db()
    assert quote.text == "New."
    assert quote.language == "de"
    assert quote.order == 7


def test_quotes_patch_moves_quote_to_other_author(api_client):
    quote = QuoteFactory(source_author=AuthorFactory(), text="Devotion.")
    target = AuthorFactory(name="Mary Oliver", name_slug="mary-oliver")

    response = api_client.patch(
        f"/api/quotes/{quote.pk}/",
        {"source_author": "mary-oliver"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": quote.pk,
        "text": "Devotion.",
        "language": "en",
        "order": None,
        "book": None,
        "author": "mary-oliver",
    }
    quote.refresh_from_db()
    assert quote.source_author == target


def test_quotes_patch_clears_source_author_with_null(api_client):
    book = make_reviewed_book(title="Quotable")
    quote = QuoteFactory(source_book=book, source_author=AuthorFactory(), text="Q.")

    response = api_client.patch(
        f"/api/quotes/{quote.pk}/",
        {"source_author": None},
        content_type="application/json",
    )

    assert response.status_code == 200
    quote.refresh_from_db()
    assert quote.source_author is None
    assert quote.source_book == book


def test_quotes_patch_unknown_author_returns_400(api_client):
    quote = QuoteFactory(source_book=make_reviewed_book(), text="Q.")

    response = api_client.patch(
        f"/api/quotes/{quote.pk}/",
        {"source_author": "nobody"},
        content_type="application/json",
    )

    assert response.status_code == 400
    quote.refresh_from_db()
    assert quote.source_author is None


def test_quotes_patch_unknown_quote_returns_404(api_client):
    response = api_client.patch(
        "/api/quotes/999/", {"text": "x"}, content_type="application/json"
    )

    assert response.status_code == 404


def test_quotes_delete_removes_quote(api_client):
    book = make_reviewed_book(title="Quotable")
    quote = QuoteFactory(source_book=book, text="Doomed.")
    keeper = QuoteFactory(source_book=book, text="Keeper.")

    response = api_client.delete(f"/api/quotes/{quote.pk}/")

    assert response.status_code == 204
    assert list(Quote.objects.all()) == [keeper]


def test_quotes_delete_unknown_quote_returns_404(api_client):
    response = api_client.delete("/api/quotes/999/")

    assert response.status_code == 404
