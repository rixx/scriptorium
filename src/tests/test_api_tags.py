import pytest

from tests.factories import TagFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


def test_tags_list_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    TagFactory(name="Hidden")

    response = client.get("/api/tags/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_tags_list_returns_tags_with_book_counts(api_client):
    genre = TagFactory(
        category="genre", name="Science Fiction", name_slug="science-fiction"
    )
    TagFactory(category="format", name="Novella", name_slug="novella")
    book_one = make_reviewed_book(title="One")
    book_two = make_reviewed_book(title="Two")
    book_one.tags.add(genre)
    book_two.tags.add(genre)

    response = api_client.get("/api/tags/")

    assert response.status_code == 200
    assert response.json() == [
        {
            "category": "format",
            "name": "Novella",
            "slug": "novella",
            "text": None,
            "book_count": 0,
        },
        {
            "category": "genre",
            "name": "Science Fiction",
            "slug": "science-fiction",
            "text": None,
            "book_count": 2,
        },
    ]
