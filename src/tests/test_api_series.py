import pytest

from tests.factories import SeriesFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


def test_series_list_requires_token(client, api_token):
    SeriesFactory(name="Hidden")

    response = client.get("/api/series/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_series_list_returns_series_with_book_counts(api_client):
    hainish = SeriesFactory(name="Hainish Cycle", name_slug="hainish-cycle")
    earthsea = SeriesFactory(name="Earthsea", name_slug="earthsea")
    make_reviewed_book(title="One", series=hainish)
    make_reviewed_book(title="Two", series=hainish)

    response = api_client.get("/api/series/")

    assert response.status_code == 200
    assert response.json() == {
        "count": 2,
        "items": [
            {
                "id": earthsea.pk,
                "name": "Earthsea",
                "slug": "earthsea",
                "book_count": 0,
            },
            {
                "id": hainish.pk,
                "name": "Hainish Cycle",
                "slug": "hainish-cycle",
                "book_count": 2,
            },
        ],
    }


def test_series_list_search_filters_by_name(api_client):
    SeriesFactory(name="Hainish Cycle", name_slug="hainish-cycle")
    SeriesFactory(name="Earthsea", name_slug="earthsea")

    response = api_client.get("/api/series/", {"q": "hain"})

    assert [item["name"] for item in response.json()["items"]] == ["Hainish Cycle"]
