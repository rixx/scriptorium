import datetime as dt
import json

import pytest

from scriptorium.main.models import BookRelation
from scriptorium.main.views import GraphView, QueueView, healthz
from tests.factories import (
    AuthorFactory,
    PageFactory,
    PoemFactory,
    QuoteFactory,
    TagFactory,
    ToReadFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


# --- Index & feed -----------------------------------------------------------


def test_index_view_shows_recent_books(client, populated_library):
    response = client.get("/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Welcome to log(book)" in body
    assert populated_library["book_two"].title in body


def test_healthz_view_returns_ok(rf):
    response = healthz(rf.get("/healthz/"))

    assert response.status_code == 200
    assert json.loads(response.content.decode()) == {"status": "ok"}


def test_feed_view_returns_atom_feed(client, reviewed_book):
    response = client.get("/feed.atom")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/atom+xml")
    assert reviewed_book.title in response.content.decode()


def test_feed_view_excludes_drafts(client):
    published = make_reviewed_book(title="Published Book")
    draft = make_reviewed_book(title="Draft Book")
    draft.review.is_draft = True
    draft.review.save()

    response = client.get("/feed.atom")

    body = response.content.decode()
    assert published.title in body
    assert draft.title not in body


# --- Year / by-* views ------------------------------------------------------


def test_year_view_defaults_to_current_year(client):
    today = dt.datetime.now(tz=dt.UTC).date()
    recent = make_reviewed_book(
        title="Recent Read", latest_date=today, dates_read=today.isoformat()
    )
    older = make_reviewed_book(
        title="Old Read", latest_date=dt.date(2000, 1, 1), dates_read="2000-01-01"
    )

    response = client.get("/reviews/")

    assert response.status_code == 200
    body = response.content.decode()
    assert recent.title in body
    assert older.title not in body


def test_year_view_specific_year(client):
    book_2023 = make_reviewed_book(
        title="Book from 2023", latest_date=dt.date(2023, 5, 1), dates_read="2023-05-01"
    )
    book_2024 = make_reviewed_book(
        title="Book from 2024", latest_date=dt.date(2024, 5, 1), dates_read="2024-05-01"
    )

    response = client.get("/reviews/2023/")

    assert response.status_code == 200
    body = response.content.decode()
    assert book_2023.title in body
    assert book_2024.title not in body


def test_review_by_author_view(client, populated_library):
    response = client.get("/reviews/by-author/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["author"].name in body
    assert populated_library["other_author"].name in body


def test_review_by_title_view(client, populated_library):
    response = client.get("/reviews/by-title/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body


def test_review_by_series_view_shows_series_with_multiple_books(
    client, populated_library
):
    response = client.get("/reviews/by-series/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "A Series" in body
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body
    # Solo volume is not in a series with multiple books.
    assert populated_library["book_three"].title not in body


# --- Review / Author detail -------------------------------------------------


def test_review_view_shows_book_and_review_text(client, reviewed_book):
    response = client.get(f"/{reviewed_book.slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert reviewed_book.title in body
    assert reviewed_book.review.text in body


def test_review_cover_view_without_cover_returns_404(client, reviewed_book):
    response = client.get(f"/{reviewed_book.slug}/cover.jpg")

    assert response.status_code == 404


def test_author_view_shows_author_books(client, populated_library):
    response = client.get(f"/{populated_library['author'].name_slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["author"].name in body
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body


# --- Catalogue --------------------------------------------------------------


def test_catalogue_view_lists_all_books(client, populated_library):
    response = client.get("/catalogue/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body
    assert populated_library["book_three"].title in body


def test_catalogue_view_search_filters_by_title(client, populated_library):
    response = client.get("/catalogue/?search_input=Solo")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_three"].title in body
    assert populated_library["book_one"].title not in body


def test_catalogue_view_filters_by_tag(client, populated_library):
    other_tag = TagFactory(category="genre", name="Horror", name_slug="horror")
    populated_library["book_three"].tags.add(other_tag)
    populated_library["book_three"].tags.remove(populated_library["tag"])

    response = client.get(f"/catalogue/?tags={populated_library['tag'].pk}")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body
    assert populated_library["book_three"].title not in body


# --- Tags / lists -----------------------------------------------------------


def test_tag_view_lists_tags_with_books(client, populated_library):
    empty_tag = TagFactory(
        category="themes", name="Unused", name_slug="unused"
    )  # no books

    response = client.get("/lists/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["tag"].name in body
    assert empty_tag.name not in body


def test_list_detail_view_shows_books_for_tag(client, populated_library):
    response = client.get(f"/lists/{populated_library['tag'].name_slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_one"].title in body
    assert populated_library["book_two"].title in body
    assert populated_library["book_three"].title in body


# --- Graph ------------------------------------------------------------------


def test_graph_view_reports_graph_metrics(rf):
    book_a = make_reviewed_book()
    book_b = make_reviewed_book()
    make_reviewed_book()  # isolated, becomes "missing"
    BookRelation.objects.create(source=book_a, destination=book_b, text="pairs nicely")

    view = GraphView()
    view.request = rf.get("/graph/")
    view.kwargs = {}
    context = view.get_context_data()

    assert context["node_count"] == 2
    assert context["edge_count"] == 1
    assert context["missing_nodes"] == 1
    assert context["is_connected"] is True


def test_graph_data_returns_nodes_and_links(client):
    book_a = make_reviewed_book()
    book_b = make_reviewed_book()
    BookRelation.objects.create(source=book_a, destination=book_b, text="related")

    response = client.get("/graph.json")

    assert response.status_code == 200
    payload = json.loads(response.content.decode())
    assert {n["id"] for n in payload["nodes"]} == {book_a.slug, book_b.slug}
    assert len(payload["links"]) == 1


# --- Queue ------------------------------------------------------------------


def test_queue_view_shows_shelves_and_totals(rf):
    today = dt.datetime.now(tz=dt.UTC).date()
    last_year = today.replace(year=today.year - 1)
    ToReadFactory(shelf="fiction", pages=200)
    ToReadFactory(shelf="fiction", pages=300)
    ToReadFactory(shelf="non-fiction", pages=100)
    make_reviewed_book(
        title="Read Last Year",
        pages=250,
        latest_date=last_year,
        dates_read=last_year.isoformat(),
    )

    view = QueueView()
    view.request = rf.get("/queue/")
    view.kwargs = {}
    context = view.get_context_data()

    assert context["total_books"] == 3
    assert context["total_pages"] == 600
    assert context["past_year_books"] == 1
    assert context["past_year_pages"] == 250
    shelves = {shelf["name"]: shelf for shelf in context["shelves"]}
    assert set(shelves.keys()) == {"fiction", "non-fiction"}
    assert shelves["fiction"]["page_count"] == 500
    assert shelves["non-fiction"]["page_count"] == 100


# --- Quote ------------------------------------------------------------------


def test_quote_view_renders_quote_text(client, reviewed_book):
    quote = QuoteFactory(source_book=reviewed_book, text="A memorable passage.")

    response = client.get(f"/q/{quote.pk}/")

    assert response.status_code == 200
    assert "A memorable passage." in response.content.decode()


# --- Pages ------------------------------------------------------------------


def test_page_view_renders_page(client):
    page = PageFactory(title="Colophon", slug="colophon", text="Made with care.")

    response = client.get(f"/p/{page.slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Colophon" in body
    assert "Made with care." in body


# --- Poems ------------------------------------------------------------------


def test_poem_list_view(client, author):
    poem = PoemFactory(author=author, title="Lied", slug="lied")

    response = client.get("/poems/")

    assert response.status_code == 200
    assert poem.title in response.content.decode()


def test_poem_author_list_view(client):
    author = AuthorFactory(name_slug="sappho", name="Sappho")
    poem = PoemFactory(author=author, title="Fragment", slug="fragment-31")
    unrelated_author = AuthorFactory()
    PoemFactory(author=unrelated_author, title="Elsewhere", slug="elsewhere")

    response = client.get(f"/{author.name_slug}/poems/")

    assert response.status_code == 200
    body = response.content.decode()
    assert poem.title in body
    assert "Elsewhere" not in body


def test_poem_book_list_view(client):
    book = make_reviewed_book(
        primary_author=AuthorFactory(name_slug="rilke", name="Rilke"),
        title_slug="neue-gedichte",
    )
    poem = PoemFactory(book=book, title="Der Panther", slug="der-panther")

    response = client.get(f"/{book.slug}/poems/")

    assert response.status_code == 200
    assert poem.title in response.content.decode()


def test_poem_view_by_author(client):
    author = AuthorFactory(name_slug="hafiz", name="Hafiz")
    poem = PoemFactory(
        author=author, title="Ghazal", slug="ghazal-one", text="A line of verse."
    )

    response = client.get(f"/{author.name_slug}/poems/{poem.slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert poem.title in body
    assert "A line of verse." in body
