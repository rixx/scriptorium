import logging

import pytest
import requests
from django.test import override_settings

from scriptorium.main import metadata
from scriptorium.main.metadata import (
    get_goodreads_book,
    get_openlibrary_book,
    get_openlibrary_editions,
    merge_goodreads,
    search_book,
    time_taken,
)
from tests.factories import BookFactory


class FakeResponse:
    """Duck-typed stand-in for requests.Response.

    Tests inject a pre-built body so we never hit the network. `json_data`
    is returned from .json(); set `raise_on_json` to make .json() raise
    instead (the ValueError path in search_book)."""

    def __init__(self, *, json_data=None, text="", ok=True, raise_on_json=None):
        self._json = json_data
        self.text = text
        self.ok = ok
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json is not None:
            raise self._raise_on_json
        return self._json


def _install_fake_get(monkeypatch, responses):
    """Replace metadata.requests.get with a URL-substring router.

    `responses` is a list of (needle, outcome) tuples. The first needle
    found in the URL wins; an Exception outcome is raised instead of
    returned, so tests can simulate network errors."""

    def fake_get(url, *args, **kwargs):
        for needle, outcome in responses:
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(metadata.requests, "get", fake_get)


# ---------- time_taken ----------


def test_time_taken_passes_through_when_debug_off():
    calls = []

    @time_taken
    def doubler(x):
        calls.append(x)
        return x * 2

    result = doubler(5)

    assert result == 10
    assert calls == [5]


def test_time_taken_logs_duration_when_debug_on(caplog):
    @time_taken
    def incrementor(x):
        return x + 1

    with (
        override_settings(DEBUG=True),
        caplog.at_level(logging.DEBUG, logger="scriptorium.main.metadata"),
    ):
        result = incrementor(41)

    assert result == 42
    debug_messages = [r.getMessage() for r in caplog.records if r.levelname == "DEBUG"]
    assert any("Time taken for incrementor" in m for m in debug_messages)


# ---------- search_book ----------

# Each search_book test uses a unique query because search_book is wrapped in
# functools.cache and we cannot clear the cache from outside time_taken.


def test_search_book_returns_title_and_author_tuples(monkeypatch):
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
                            },
                            {
                                "key": "/works/OL2W",
                                "title": "Solaris",
                                "author_name": None,
                            },
                        ]
                    }
                ),
            )
        ],
    )

    result = search_book("earthsea-unique-happy")

    assert result == [
        ("OL1W", "A Wizard of Earthsea by Ursula K. Le Guin"),
        ("OL2W", "Solaris by "),
    ]


def test_search_book_returns_empty_list_on_request_exception(monkeypatch):
    _install_fake_get(monkeypatch, [("search.json", requests.ConnectionError("boom"))])

    assert search_book("search-unique-req-error") == []


def test_search_book_returns_empty_list_when_response_is_not_json(monkeypatch):
    _install_fake_get(
        monkeypatch,
        [("search.json", FakeResponse(raise_on_json=ValueError("bad json")))],
    )

    assert search_book("search-unique-json-error") == []


# ---------- get_openlibrary_editions ----------


def test_get_openlibrary_editions_filters_languages_sorts_and_falls_back_to_pagination(
    monkeypatch,
):
    _install_fake_get(
        monkeypatch,
        [
            (
                "/editions.json",
                FakeResponse(
                    json_data={
                        "entries": [
                            {
                                "key": "/books/OL10M",
                                "title": "English long",
                                "publish_date": "2020",
                                "languages": [{"key": "/languages/eng"}],
                                "number_of_pages": 500,
                            },
                            {
                                "key": "/books/OL11M",
                                "title": "English short",
                                "publish_date": "2019",
                                "languages": [{"key": "/languages/eng"}],
                                # No number_of_pages → fall back to pagination.
                                "pagination": 200,
                            },
                            {
                                "key": "/books/OL12M",
                                "title": "French filtered out",
                                "publish_date": "2018",
                                "languages": [{"key": "/languages/fre"}],
                                "number_of_pages": 300,
                            },
                            {
                                "key": "/books/OL13M",
                                "title": "Unknown lang",
                                "publish_date": "2017",
                                # No languages → empty language string, not filtered.
                                "number_of_pages": 100,
                            },
                            {
                                "key": "/books/OL14M",
                                "title": "German",
                                "publish_date": "2016",
                                "languages": [{"key": "/languages/ger"}],
                                "number_of_pages": 250,
                            },
                        ]
                    }
                ),
            )
        ],
    )

    result = get_openlibrary_editions("WORK_UNIQUE_EDITIONS_MIX")

    # French is filtered out; the remaining editions sort by (lang or "zzz",
    # -pages), so eng before ger, unknown-language ("zzz" placeholder) last.
    assert result == [
        ("OL10M", "English long: 2020, eng, 500 pages"),
        ("OL11M", "English short: 2019, eng, 200 pages"),
        ("OL14M", "German: 2016, ger, 250 pages"),
        ("OL13M", "Unknown lang: 2017, , 100 pages"),
    ]


# ---------- get_openlibrary_book ----------


def test_get_openlibrary_book_queries_by_isbn(monkeypatch):
    captured = []

    def fake_get(url, *args, **kwargs):
        captured.append(url)
        return FakeResponse(json_data={"ISBN:9780000000001": {"title": "Isbn Book"}})

    monkeypatch.setattr(metadata.requests, "get", fake_get)

    result = get_openlibrary_book(isbn="9780000000001")

    assert result == {"title": "Isbn Book"}
    assert "bibkeys=ISBN:9780000000001" in captured[0]


def test_get_openlibrary_book_without_identifiers_raises(monkeypatch):
    """Called with neither isbn nor olid, the function falls through both
    branches without defining `search` and raises NameError. Documents
    current behaviour so the branch is exercised."""

    def boom(*args, **kwargs):
        raise AssertionError("requests.get must not be reached")

    monkeypatch.setattr(metadata.requests, "get", boom)

    with pytest.raises(NameError):
        get_openlibrary_book()


def test_get_openlibrary_book_queries_by_olid(monkeypatch):
    captured = []

    def fake_get(url, *args, **kwargs):
        captured.append(url)
        return FakeResponse(json_data={"OLID:OL42M": {"title": "Olid Book"}})

    monkeypatch.setattr(metadata.requests, "get", fake_get)

    result = get_openlibrary_book(olid="OL42M")

    assert result == {"title": "Olid Book"}
    assert "bibkeys=OLID:OL42M" in captured[0]


# ---------- get_goodreads_book ----------


GOODREADS_HAPPY_HTML = """
<html>
<body>
<script type="application/ld+json">
{"name": "Sample Book", "image": "https://example.com/cover.jpg",
 "numberOfPages": 300, "isbn": "9780000000002"}
</script>
<div class="FeaturedDetails">First published May 14, 2020 by Tor</div>
</body>
</html>
"""


GOODREADS_FALLBACK_HTML = """
<html>
<body>
<script type="application/ld+json">
{"name": "Fallback Book", "image": "https://example.com/x.jpg",
 "numberOfPages": 150, "isbn": "0000000001"}
</script>
<div class="FeaturedDetails">No release date information available.</div>
<dl><dt>ISBN</dt><dd>0000000001</dd></dl>
<dl><dt>First published</dt><dd>unknown release</dd></dl>
<dl><dt>Also published</dt><dd>reissued 1999</dd></dl>
</body>
</html>
"""


def test_get_goodreads_book_parses_ld_json_and_featured_year(monkeypatch):
    _install_fake_get(
        monkeypatch, [("goodreads.com", FakeResponse(text=GOODREADS_HAPPY_HTML))]
    )

    result = get_goodreads_book("gr-unique-happy")

    assert result == {
        "title": "Sample Book",
        "cover_source": "https://example.com/cover.jpg",
        "pages": 300,
        "isbn": "9780000000002",
        "publication_year": 2020,
    }


def test_get_goodreads_book_returns_empty_when_response_not_ok(monkeypatch):
    _install_fake_get(monkeypatch, [("goodreads.com", FakeResponse(ok=False))])

    assert get_goodreads_book("gr-unique-not-ok") == {}


def test_get_goodreads_book_returns_empty_when_ld_json_missing(monkeypatch):
    _install_fake_get(
        monkeypatch,
        [
            (
                "goodreads.com",
                FakeResponse(text="<html><body>no ld json here</body></html>"),
            )
        ],
    )

    assert get_goodreads_book("gr-unique-no-script") == {}


def test_get_goodreads_book_falls_back_to_dl_publication_year(monkeypatch):
    _install_fake_get(
        monkeypatch, [("goodreads.com", FakeResponse(text=GOODREADS_FALLBACK_HTML))]
    )

    result = get_goodreads_book("gr-unique-fallback")

    # Featured block has no year, so we sweep the dl list. "ISBN" has no
    # "published" in its term (skipped). "First published / unknown release"
    # matches the term but has no 4-digit year (no assignment). The final
    # "Also published / reissued 1999" matches both and wins.
    assert result["title"] == "Fallback Book"
    assert result["publication_year"] == 1999


# ---------- merge_goodreads ----------


@pytest.mark.django_db
def test_merge_goodreads_returns_early_when_book_has_no_goodreads_id(monkeypatch):
    def should_not_be_called(gid):
        raise AssertionError("get_goodreads_book must not run when id is missing")

    monkeypatch.setattr(metadata, "get_goodreads_book", should_not_be_called)
    book = BookFactory(goodreads_id=None)

    assert merge_goodreads(book) is None


@pytest.mark.django_db
def test_merge_goodreads_raises_when_fetch_returns_empty(monkeypatch):
    monkeypatch.setattr(metadata, "get_goodreads_book", lambda gid: {})
    book = BookFactory(goodreads_id="gr-raises-1", title="Orphaned")

    with pytest.raises(RuntimeError, match="Failed to get goodreads data"):
        merge_goodreads(book)


@pytest.mark.django_db
def test_merge_goodreads_fills_missing_fields_from_full_payload(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "get_goodreads_book",
        lambda gid: {
            "cover_source": "https://example.com/cover.jpg",
            "publication_year": 2005,
            "pages": 400,
            "isbn": "9780000000003",
        },
    )
    book = BookFactory(
        goodreads_id="gr-full-1",
        pages=None,
        publication_year=None,
        isbn13=None,
        isbn10=None,
    )

    merge_goodreads(book)
    book.refresh_from_db()

    assert book.cover_source == "https://example.com/cover.jpg"
    assert book.publication_year == 2005
    assert book.pages == 400


@pytest.mark.django_db
def test_merge_goodreads_preserves_existing_better_fields_and_sets_isbn10(monkeypatch):
    """Exercise the 'skip' branches: book already has a cover, an older
    publication year, more pages, and an isbn13 — only the missing isbn10
    field should change."""
    monkeypatch.setattr(
        metadata,
        "get_goodreads_book",
        lambda gid: {
            # No cover_source → skip cover branch.
            "publication_year": 2005,
            "pages": 300,
            "isbn": "0000000001",
        },
    )
    book = BookFactory(
        goodreads_id="gr-skip-1",
        pages=500,
        publication_year=1990,
        isbn13="9780000000099",
        isbn10=None,
    )

    merge_goodreads(book)
    book.refresh_from_db()

    assert book.publication_year == 1990
    assert book.pages == 500
    assert book.isbn13 == "9780000000099"
    assert book.isbn10 == "0000000001"
    assert book.cover_source is None
