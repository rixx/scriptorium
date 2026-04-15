import datetime as dt
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

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


def _make_image_bytes(color=(200, 100, 50)):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _attach_cover(book, filename="cover.jpg"):
    book.cover.save(
        filename, SimpleUploadedFile(filename, _make_image_bytes(), "image/jpeg")
    )
    return book


@pytest.fixture
def _media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def _gender_tags():
    TagFactory(category="author", name="gender:female", name_slug="gender:female")
    TagFactory(category="author", name="gender:male", name_slug="gender:male")


@pytest.fixture
def stats_library(_gender_tags):
    """Twelve reviewed books on a page-count × publication-year diagonal, so
    that every bucket used by ``get_charts`` has at least one review and no
    ``round(None, ...)`` call can crash."""
    # (pages, publication_year) pairs — one per (page_bucket, pub_year_bucket) slot.
    combos = [
        (25, 1850),
        (75, 1910),
        (125, 1935),
        (175, 1960),
        (225, 1980),
        (275, 1987),
        (325, 1992),
        (375, 1997),
        (450, 2002),
        (600, 2007),
        (875, 2012),
        (1500, 2017),
    ]
    books = []
    for idx, (pages, year) in enumerate(combos):
        read_date = dt.date(2024, 1, 1) + dt.timedelta(days=idx)
        books.append(
            make_reviewed_book(
                title=f"Stats book {idx}",
                title_slug=f"stats-book-{idx}",
                pages=pages,
                publication_year=year,
                rating=4,
                latest_date=read_date,
                dates_read=read_date.isoformat(),
            )
        )
    return books


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


def test_poem_view_by_book(client):
    book = make_reviewed_book(
        primary_author=AuthorFactory(name_slug="eliot", name="T. S. Eliot"),
        title_slug="four-quartets",
    )
    poem = PoemFactory(
        book=book,
        title="Burnt Norton",
        slug="burnt-norton",
        text="Time present and time past.",
    )

    response = client.get(f"/{book.slug}/poems/{poem.slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert poem.title in body
    assert "Time present and time past." in body


def test_poem_view_by_url_slug_fallback(client):
    """A Poem with neither book nor author resolves via its url_slug."""
    poem = PoemFactory(
        title="Anonymous Fragment",
        slug="fragment",
        url_slug="anonymous",
        text="A mystery verse.",
    )

    response = client.get(f"/poems/{poem.url_slug}/{poem.slug}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert poem.title in body
    assert "A mystery verse." in body


# --- Border images ---------------------------------------------------------


def test_border_image_returns_svg_for_requested_number(client):
    response = client.get("/img/border/?border=1&color=123456")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    body = response.content.decode()
    assert "#123456" in body
    assert "<svg" in body


def test_border_image_random_when_no_number_given(client, settings):
    response = client.get("/img/border/")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    body = response.content.decode()
    assert "<svg" in body
    # Default color is used when none given.
    assert "#990000" in body


@pytest.mark.parametrize("border_param", ["not-a-number", "99999"])
def test_border_image_invalid_number_falls_back_to_random(client, border_param):
    response = client.get(f"/img/border/?border={border_param}")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.content.decode()


def test_border_image_list_view(client, settings):
    response = client.get("/img/border/all/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Border Images" in body
    # The template renders one <option> per available border via range(1, max_border).
    option_count = body.count('<option value="')
    assert option_count >= settings.MAX_BORDER - 1


# --- Stats ------------------------------------------------------------------


def test_stats_view_renders_reading_stats(client, stats_library):
    response = client.get("/stats/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Reading stats" in body
    # The stats grid renders an SVG per year-month bucket.
    assert "<svg" in body
    # The stats table row for total book count.
    assert "Total books" in body
    # get_charts() renders all three labelled charts.
    assert "Rating and books over time" in body
    assert "Rating and books per page count" in body
    assert "Ratings and books per publication year" in body


def test_year_in_books_view_renders_year_stats(client, stats_library):
    # stats_library reads all 12 books across 2024 (latest_date = 2024-01-01..12).
    # Previous year (2023) also needs at least one review for get_year_stats'
    # extra_years recursion.
    make_reviewed_book(
        title="Read in 2023",
        title_slug="read-in-2023",
        pages=250,
        publication_year=2010,
        rating=4,
        latest_date=dt.date(2023, 6, 1),
        dates_read="2023-06-01",
    )

    response = client.get("/reviews/2024/stats/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "2024 in books" in body
    # First/last book slots pick from stats_library's 12 2024 reads.
    assert stats_library[0].title in body
    assert stats_library[-1].title in body


# --- Cover / thumbnail ------------------------------------------------------


@pytest.mark.usefixtures("_media_tmp")
def test_review_cover_view_returns_file_response(client, reviewed_book):
    _attach_cover(reviewed_book)

    response = client.get(f"/{reviewed_book.slug}/cover.jpg")

    assert response.status_code == 200
    assert response.streaming is True
    assert b"".join(response.streaming_content) == reviewed_book.cover.read()


def test_review_cover_thumbnail_view_without_cover_returns_404(client, reviewed_book):
    response = client.get(f"/{reviewed_book.slug}/thumbnail.jpg")

    assert response.status_code == 404


@pytest.mark.usefixtures("_media_tmp")
def test_review_cover_thumbnail_view_serves_existing_thumbnail(client, reviewed_book):
    _attach_cover(reviewed_book)
    # First request generates the thumbnail row…
    client.get(f"/{reviewed_book.slug}/thumbnail.jpg")
    assert reviewed_book.thumbnails.count() == 1

    # …a second request must serve it without creating another row.
    response = client.get(f"/{reviewed_book.slug}/thumbnail.jpg")

    assert response.status_code == 200
    assert reviewed_book.thumbnails.count() == 1


@pytest.mark.usefixtures("_media_tmp")
def test_review_cover_thumbnail_view_generates_and_returns_thumbnail(
    client, reviewed_book
):
    _attach_cover(reviewed_book)
    assert reviewed_book.cover_thumbnail is None

    response = client.get(f"/{reviewed_book.slug}/thumbnail.jpg")

    assert response.status_code == 200
    reviewed_book.refresh_from_db()
    del reviewed_book.cover_thumbnail  # invalidate cached_property
    assert reviewed_book.cover_thumbnail is not None
    # The served bytes are a valid JPEG produced by the thumbnail generator.
    body = b"".join(response.streaming_content)
    assert body.startswith(b"\xff\xd8")  # JPEG magic bytes
    assert Image.open(io.BytesIO(body)).format == "JPEG"


# --- Catalogue invalid form -------------------------------------------------


def test_catalogue_view_invalid_form_returns_no_books(client, populated_library):
    # `order_by` has a fixed choice list; an unknown value makes the form invalid,
    # which must fall back to an empty queryset rather than leaking all books.
    happy_response = client.get("/catalogue/")
    happy_body = happy_response.content.decode()
    assert populated_library["book_one"].title in happy_body  # sanity

    response = client.get("/catalogue/?order_by=not-a-real-field")

    assert response.status_code == 200
    body = response.content.decode()
    assert populated_library["book_one"].title not in body
    assert populated_library["book_two"].title not in body
    assert populated_library["book_three"].title not in body
