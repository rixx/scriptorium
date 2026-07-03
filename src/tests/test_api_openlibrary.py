import pytest
import requests

from scriptorium.main import metadata
from tests.test_metadata import FakeResponse, _install_fake_get

pytestmark = pytest.mark.django_db

# The metadata helpers are wrapped in functools.cache, so every test uses a
# unique query / work id / olid to avoid cross-test cache hits (same
# convention as tests/test_metadata.py).


def test_openlibrary_search_requires_token(client, settings):
    settings.API_KEY = "test-api-key"

    response = client.get("/api/openlibrary/search/", {"q": "anything"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_openlibrary_search_returns_works(api_client, monkeypatch):
    _install_fake_get(
        monkeypatch,
        [
            (
                "search.json",
                FakeResponse(
                    json_data={
                        "docs": [
                            {
                                "key": "/works/OL1W",
                                "title": "A Wizard of Earthsea",
                                "author_name": ["Ursula K. Le Guin"],
                                "first_publish_year": 1968,
                                "cover_i": 12345,
                            },
                            {
                                "key": "/works/OL2W",
                                "title": "Obscure Work",
                                # No authors, year, or cover known.
                            },
                        ]
                    }
                ),
            )
        ],
    )

    response = api_client.get("/api/openlibrary/search/", {"q": "api-earthsea-happy"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "OL1W",
            "title": "A Wizard of Earthsea",
            "authors": ["Ursula K. Le Guin"],
            "year": 1968,
            "cover_url": "https://covers.openlibrary.org/b/id/12345-M.jpg",
        },
        {
            "id": "OL2W",
            "title": "Obscure Work",
            "authors": [],
            "year": None,
            "cover_url": None,
        },
    ]


def test_openlibrary_search_maps_upstream_error_to_502(api_client, monkeypatch):
    _install_fake_get(monkeypatch, [("search.json", requests.ConnectionError("boom"))])

    response = api_client.get("/api/openlibrary/search/", {"q": "api-search-error"})

    assert response.status_code == 502
    assert response.json()["detail"].startswith("OpenLibrary request failed")


def test_openlibrary_editions_returns_sorted_filtered_editions(api_client, monkeypatch):
    _install_fake_get(
        monkeypatch,
        [
            (
                "/editions.json",
                FakeResponse(
                    json_data={
                        "entries": [
                            {
                                "key": "/books/OL20M",
                                "title": "German edition",
                                "publish_date": "2016",
                                "languages": [{"key": "/languages/ger"}],
                                "number_of_pages": 250,
                            },
                            {
                                "key": "/books/OL21M",
                                "title": "English edition",
                                "publish_date": "2020",
                                "languages": [{"key": "/languages/eng"}],
                                "number_of_pages": 500,
                            },
                            {
                                "key": "/books/OL22M",
                                "title": "French edition",
                                "languages": [{"key": "/languages/fre"}],
                                "number_of_pages": 300,
                            },
                        ]
                    }
                ),
            )
        ],
    )

    response = api_client.get("/api/openlibrary/works/OLAPIEDITIONS1W/editions/")

    # French is filtered out, English sorts before German.
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "OL21M",
            "title": "English edition",
            "publish_date": "2020",
            "language": "eng",
            "pages": 500,
            "cover_url": "https://covers.openlibrary.org/b/olid/OL21M-M.jpg",
        },
        {
            "id": "OL20M",
            "title": "German edition",
            "publish_date": "2016",
            "language": "ger",
            "pages": 250,
            "cover_url": "https://covers.openlibrary.org/b/olid/OL20M-M.jpg",
        },
    ]


def test_openlibrary_editions_maps_upstream_error_to_502(api_client, monkeypatch):
    _install_fake_get(monkeypatch, [("/editions.json", requests.Timeout("too slow"))])

    response = api_client.get("/api/openlibrary/works/OLAPIEDITIONS2W/editions/")

    assert response.status_code == 502
    assert response.json()["detail"].startswith("OpenLibrary request failed")


def test_openlibrary_book_returns_normalized_metadata(api_client, monkeypatch):
    _install_fake_get(
        monkeypatch,
        [
            (
                "api/books",
                FakeResponse(
                    json_data={
                        "OLID:OLAPIBOOK1M": {
                            "title": "The Dispossessed",
                            "identifiers": {
                                "openlibrary": ["OLAPIBOOK1M"],
                                "isbn_13": ["9780061054884"],
                                "isbn_10": ["0061054887"],
                                "goodreads": ["13651"],
                            },
                            "authors": [
                                {"name": "Ursula K. Le Guin"},
                                {"name": "Someone Else"},
                            ],
                            "number_of_pages": 341,
                            "publish_date": "May 1974",
                            "cover": {"large": "https://covers.example.com/l.jpg"},
                        }
                    }
                ),
            )
        ],
    )

    response = api_client.get("/api/openlibrary/books/OLAPIBOOK1M/")

    assert response.status_code == 200
    assert response.json() == {
        "title": "The Dispossessed",
        "author_name": "Ursula K. Le Guin & Someone Else",
        "openlibrary_id": "OLAPIBOOK1M",
        "isbn13": "9780061054884",
        "isbn10": "0061054887",
        "goodreads_id": "13651",
        "pages": 341,
        "publication_year": 1974,
        "cover_source": "https://covers.example.com/l.jpg",
    }


def test_openlibrary_book_unknown_id_returns_404(api_client, monkeypatch):
    # OpenLibrary answers with an empty object for ids it doesn't know.
    _install_fake_get(monkeypatch, [("api/books", FakeResponse(json_data={}))])

    response = api_client.get("/api/openlibrary/books/OLAPIBOOKMISSINGM/")

    assert response.status_code == 404
    assert "OLAPIBOOKMISSINGM" in response.json()["detail"]


def test_openlibrary_book_maps_upstream_error_to_502(api_client, monkeypatch):
    _install_fake_get(
        monkeypatch, [("api/books", FakeResponse(raise_on_json=ValueError("not json")))]
    )

    response = api_client.get("/api/openlibrary/books/OLAPIBOOKERRM/")

    assert response.status_code == 502
    assert response.json()["detail"].startswith("OpenLibrary request failed")


def test_openlibrary_book_data_is_cached_between_requests(api_client, monkeypatch):
    """The proxy leans on the metadata layer's functools.cache: repeated
    lookups of the same id hit OpenLibrary once."""
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return FakeResponse(
            json_data={
                "OLID:OLAPICACHED1M": {
                    "title": "Cached Book",
                    "identifiers": {"openlibrary": ["OLAPICACHED1M"]},
                    "authors": [{"name": "Someone"}],
                    "publish_date": "2001",
                }
            }
        )

    monkeypatch.setattr(metadata.requests, "get", fake_get)

    first = api_client.get("/api/openlibrary/books/OLAPICACHED1M/")
    second = api_client.get("/api/openlibrary/books/OLAPICACHED1M/")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1
