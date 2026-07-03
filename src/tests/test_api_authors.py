import pytest

from scriptorium.main.models import BookStatus
from tests.factories import AuthorFactory, BookFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


def test_authors_list_requires_token(client, settings):
    settings.API_KEY = "test-api-key"
    AuthorFactory(name="Hidden")

    response = client.get("/api/authors/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_authors_list_returns_authors_sorted_by_slug(api_client):
    zeta = AuthorFactory(name="Zeta", name_slug="zeta")
    alpha = AuthorFactory(name="Alpha", name_slug="alpha")

    response = api_client.get("/api/authors/")

    assert response.status_code == 200
    assert response.json() == {
        "count": 2,
        "items": [
            {"id": alpha.pk, "name": "Alpha", "slug": "alpha"},
            {"id": zeta.pk, "name": "Zeta", "slug": "zeta"},
        ],
    }


def test_authors_list_search_filters_by_name(api_client):
    AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    AuthorFactory(name="Susanna Clarke", name_slug="susanna-clarke")

    response = api_client.get("/api/authors/", {"q": "guin"})

    assert [item["name"] for item in response.json()["items"]] == ["Ursula K. Le Guin"]


def test_authors_detail_includes_published_books(api_client):
    author = AuthorFactory(
        name="Ursula K. Le Guin", name_slug="ursula-k-le-guin", text="SF grandmaster."
    )
    make_reviewed_book(
        title="The Dispossessed", title_slug="the-dispossessed", primary_author=author
    )
    coauthored = make_reviewed_book(title="Anthology", title_slug="anthology")
    coauthored.additional_authors.add(author)
    # Unpublished books stay out of the public author page and API alike.
    BookFactory(title="Draft", primary_author=author, status=BookStatus.TO_REVIEW)

    response = api_client.get("/api/authors/ursula-k-le-guin/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Ursula K. Le Guin"
    assert data["slug"] == "ursula-k-le-guin"
    assert data["text"] == "SF grandmaster."
    assert [book["title"] for book in data["books"]] == [
        "Anthology",
        "The Dispossessed",
    ]


def test_authors_detail_unknown_slug_returns_404(api_client):
    response = api_client.get("/api/authors/nobody/")

    assert response.status_code == 404


def test_authors_patch_renames_but_keeps_slug(api_client):
    author = AuthorFactory(name="Ursula Le Guin", name_slug="ursula-k-le-guin")

    response = api_client.patch(
        "/api/authors/ursula-k-le-guin/",
        {"name": "Ursula K. Le Guin", "text": "Corrected."},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Ursula K. Le Guin"
    assert data["slug"] == "ursula-k-le-guin"
    author.refresh_from_db()
    assert author.name == "Ursula K. Le Guin"
    assert author.name_slug == "ursula-k-le-guin"
    assert author.text == "Corrected."


def test_authors_patch_rejects_null_name(api_client):
    author = AuthorFactory(name="Keep Me")

    response = api_client.patch(
        f"/api/authors/{author.name_slug}/",
        {"name": None},
        content_type="application/json",
    )

    assert response.status_code == 422
    author.refresh_from_db()
    assert author.name == "Keep Me"


def test_authors_patch_unknown_slug_returns_404(api_client):
    response = api_client.patch(
        "/api/authors/nobody/", {"name": "New"}, content_type="application/json"
    )

    assert response.status_code == 404
