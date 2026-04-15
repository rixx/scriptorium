import datetime as dt
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from django.test import RequestFactory
from markupsafe import Markup

from scriptorium.main.jinja2 import (
    render_authors,
    render_date,
    replace_url,
    strip_markdown,
    unmark_element,
)


def test_unmark_element_concatenates_text_and_tail():
    root = ET.Element("p")
    root.text = "hello "
    child = ET.SubElement(root, "b")
    child.text = "bold"
    child.tail = " world"

    assert unmark_element(root) == "hello bold world"


def test_unmark_element_handles_missing_text_and_tail():
    """Elements without .text or .tail must be skipped, not crash."""
    root = ET.Element("p")
    child = ET.SubElement(root, "b")
    child.text = "only"
    # root.text, child.tail, root.tail are all None

    assert unmark_element(root) == "only"


def test_strip_markdown_removes_formatting():
    assert strip_markdown("**bold** and _italic_").strip() == "bold and italic"


def test_render_date_accepts_date_object():
    result = render_date(dt.date(2024, 6, 15))

    assert result == Markup('<a href="/reviews/2024">2024</a>-06-15')


def test_render_date_accepts_string():
    """Strings skip the strftime branch and are used verbatim."""
    result = render_date("2023-01-02")

    assert result == Markup('<a href="/reviews/2023">2023</a>-01-02')


def test_render_date_without_link_returns_plain_string():
    assert render_date("2023-01-02", link=False) == "2023-01-02"


def test_render_date_returns_none_for_empty_value():
    assert render_date("") is None


def test_render_authors_single_author():
    author = SimpleNamespace(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")

    result = render_authors([author])

    assert result == Markup('<a href="/ursula-k-le-guin/">Ursula K. Le Guin</a>')


def test_render_authors_multiple_authors_joins_with_ampersand():
    authors = [
        SimpleNamespace(name="A", name_slug="a"),
        SimpleNamespace(name="B", name_slug="b"),
        SimpleNamespace(name="C", name_slug="c"),
    ]

    result = render_authors(authors)

    assert result == Markup(
        '<a href="/a/">A</a>, <a href="/b/">B</a> & <a href="/c/">C</a>'
    )


def test_replace_url_adds_or_updates_key():
    request = RequestFactory().get("/?page=2&sort=title")

    assert replace_url(request, "page", 5) == "page=5&sort=title"


def test_replace_url_removes_key_when_value_is_empty():
    request = RequestFactory().get("/?page=2&sort=title")

    assert replace_url(request, "page", "") == "sort=title"
