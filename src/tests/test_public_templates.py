import datetime as dt

import pytest
from bs4 import BeautifulSoup
from django.conf import settings
from django.test import Client

from tests.factories import (
    AuthorFactory,
    PoemFactory,
    QuoteFactory,
    ReadFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


def _soup(response):
    return BeautifulSoup(response.content.decode(), "html.parser")


def test_header_nav_links_have_trailing_slashes_and_no_separators(client):
    response = client.get("/")

    nav = _soup(response).find("nav", id="nav-links")
    assert [a["href"] for a in nav.find_all("a")] == [
        "/reviews/",
        "/queue/",
        "/catalogue/",
        "/stats/",
        "/poems/",
    ]
    assert nav.find_all("span") == []


def test_header_marks_admin_links_for_logged_in_user(admin_logged_in_client):
    logged_in = _soup(admin_logged_in_client.get("/")).find(id="sidenav-right")
    anonymous = _soup(Client().get("/")).find(id="sidenav-right")

    assert logged_in["class"] == ["sidenav", "admin-links"]
    assert anonymous["class"] == ["sidenav"]


def test_internal_links_on_public_pages_do_not_redirect(client):
    book = make_reviewed_book(
        title="Linked",
        title_slug="linked",
        latest_date=dt.date(2024, 5, 3),
        spine_color="#123456",
    )
    pages = ["/", "/reviews/2024/", f"/{book.slug}/", "/catalogue/"]

    hrefs = set()
    for page in pages:
        for a in _soup(client.get(page)).find_all("a", href=True):
            if a["href"].startswith("/") and not a["href"].startswith("//"):
                hrefs.add(a["href"].split("#")[0])

    assert {"/reviews/2024/", "/stats/", "/graph/", "/lists/"} <= hrefs
    lenient = Client(raise_request_exception=False)
    statuses = {href: lenient.get(href).status_code for href in sorted(hrefs)}
    assert {href: s for href, s in statuses.items() if s in {301, 302}} == {}


def test_quote_by_author_only_links_to_author_page(client):
    author = AuthorFactory(name="Anna Akhmatova", name_slug="anna-akhmatova")
    quote = QuoteFactory(source_author=author)

    response = client.get(f"/q/{quote.pk}/")

    link = _soup(response).find(id="quote-attribution").find("a")
    assert link["href"] == "/anna-akhmatova/"
    assert client.get(link["href"]).status_code == 200


def test_review_page_uses_og_property_for_description(client):
    book = make_reviewed_book(tldr="Gripping.")

    response = client.get(f"/{book.slug}/")

    meta = _soup(response).find("meta", property="og:description")
    assert meta["content"] == "Review: Gripping."
    assert _soup(response).find("meta", attrs={"name": "og:description"}) is None


@pytest.mark.parametrize(
    ("ui_color", "expected_attrs"), [(None, {"class"}), ("#a1b2c3", {"class", "style"})]
)
def test_book_card_attributes_are_well_formed(client, ui_color, expected_attrs):
    make_reviewed_book(ui_color=ui_color)

    response = client.get("/")

    card = _soup(response).find("div", class_="book-card")
    assert set(card.attrs) == expected_attrs
    if ui_color:
        assert card["style"] == "border-color: #a1b2c3"


def test_year_view_emits_one_anchor_per_month(client):
    for day in (dt.date(2024, 6, 20), dt.date(2024, 6, 2), dt.date(2024, 5, 9)):
        make_reviewed_book(latest_date=day)

    response = client.get("/reviews/2024/")

    anchors = [p["id"] for p in _soup(response).find_all("p", id=True)]
    assert anchors == ["2024-06", "2024-05"]


def test_review_plot_markdown_is_not_nested_in_paragraph(client):
    book = make_reviewed_book(plot="First part.\n\nSecond part.")

    response = client.get(f"/{book.slug}/")

    paragraphs = _soup(response).find("details").find_all("p")
    plot = [p for p in paragraphs if p.get_text() in {"First part.", "Second part."}]
    assert [p.parent.name for p in plot] == ["div", "div"]


def test_author_text_markdown_is_not_nested_in_paragraph(client):
    author = AuthorFactory(text="About the author.")
    make_reviewed_book(primary_author=author)

    response = client.get(f"/{author.name_slug}/")

    paragraph = _soup(response).find("p", string="About the author.")
    assert paragraph.parent.name == "div"


def test_poem_context_markdown_is_not_nested_in_paragraph(client):
    poem = PoemFactory(author=AuthorFactory(), context="Written at sea.")

    response = client.get(poem.get_absolute_url())

    paragraph = _soup(response).find("p", string="Written at sea.")
    assert paragraph.parent.name == "div"
    assert paragraph.parent["class"] == ["context"]


def test_poem_without_context_renders_no_context_block(client):
    poem = PoemFactory(author=AuthorFactory(), context="")

    response = client.get(poem.get_absolute_url())

    assert _soup(response).find(class_="context") is None


def test_index_intro_prose_is_in_paragraphs(client):
    response = client.get("/")

    soup = _soup(response)
    starts = ["This is where I", "The data gets synced", "Thanks for the content"]
    parents = [
        soup.find(
            string=lambda s, start=start: s and s.strip().startswith(start)
        ).parent.name
        for start in starts
    ]
    assert parents == ["p", "p", "p"]


def test_border_image_list_offers_every_border(client):
    response = client.get("/img/border/all/")

    options = _soup(response).find("select", id="border-image").find_all("option")
    assert [int(o["value"]) for o in options] == list(range(1, settings.MAX_BORDER + 1))


def test_unknown_url_renders_site_404_page(client):
    response = client.get("/no-such-author/no-such-book/")

    assert response.status_code == 404
    soup = _soup(response)
    assert [a["href"] for a in soup.find("nav", id="nav-links").find_all("a")] == [
        "/reviews/",
        "/queue/",
        "/catalogue/",
        "/stats/",
        "/poems/",
    ]
    assert [a["href"] for a in soup.find("main").find_all("a")] == [
        "/catalogue/",
        "/reviews/",
    ]


def test_shelf_spines_have_accessible_names(client):
    book = make_reviewed_book(title="Spined", spine_color="#334455")

    response = client.get("/")

    spines = _soup(response).find_all("a", class_="spine-wrapper")
    assert [s["aria-label"] for s in spines] == ["Spined"]
    assert spines[0]["href"] == f"/{book.slug}/"


def test_public_pages_have_alt_text_on_every_image(client):
    book = make_reviewed_book(
        title="Pictured", isbn13="9780000000000", spine_color="#334455"
    )
    ReadFactory(book=book, finished_on=dt.date(2023, 1, 1))

    missing = {}
    for page in ("/", f"/{book.slug}/"):
        imgs = _soup(client.get(page)).find_all("img")
        missing[page] = [img["src"] for img in imgs if not img.has_attr("alt")]

    assert missing == {"/": [], f"/{book.slug}/": []}
    links = _soup(client.get(f"/{book.slug}/")).find(class_="external-link")
    alts = [img["alt"].strip() for img in links.find_all("img")]
    assert len(alts) == 3
    assert all(alts)
