import pytest

pytestmark = pytest.mark.django_db


def test_api_docs_page_renders(client):
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "Scriptorium API" in response.content.decode()


def test_openapi_schema_lists_all_routes(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Scriptorium API"
    assert set(schema["paths"]) == {
        "/api/books/",
        "/api/books/{author_slug}/{title_slug}/",
        "/api/books/{author_slug}/{title_slug}/review/",
        "/api/books/{author_slug}/{title_slug}/reads/",
        "/api/books/{author_slug}/{title_slug}/quotes/",
        "/api/queue/",
        "/api/queue/next/",
        "/api/reads/{read_id}/",
        "/api/quotes/{quote_id}/",
        "/api/authors/",
        "/api/authors/{author_slug}/",
        "/api/tags/",
        "/api/series/",
        "/api/openlibrary/search/",
        "/api/openlibrary/works/{work_id}/editions/",
        "/api/openlibrary/books/{olid}/",
    }
