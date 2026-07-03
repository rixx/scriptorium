import json
import logging
import re
import time
import urllib.parse
from functools import cache

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MetadataError(Exception):
    """An upstream metadata service (OpenLibrary) failed: network error,
    timeout, or a response that wasn't JSON."""


def _fetch_json(url):
    try:
        return requests.get(url, timeout=5).json()
    except (requests.RequestException, ValueError) as exc:
        raise MetadataError(f"OpenLibrary request failed: {exc}") from exc


# add profiling decorator
def time_taken(func):
    def wrapper(*args, **kwargs):
        if not settings.DEBUG:
            return func(*args, **kwargs)

        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.debug("Time taken for %s: %.2fs", func.__name__, end - start)
        return result

    return wrapper


@time_taken
@cache
def search_openlibrary(search):
    """Search OpenLibrary works, returning structured dicts. Raises
    MetadataError on upstream failure -- the API proxy maps that to a 502,
    while the wizard-facing search_book swallows it."""
    query = urllib.parse.quote(search)
    data = _fetch_json(f"https://openlibrary.org/search.json?q={query}")
    return [
        {
            "id": doc["key"].split("/")[-1],
            "title": doc["title"],
            "authors": doc.get("author_name") or [],
            "year": doc.get("first_publish_year"),
            "cover_url": (
                f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                if doc.get("cover_i")
                else None
            ),
        }
        for doc in data.get("docs") or []
    ]


@time_taken
@cache
def search_book(search):
    """Works as (id, label) choice tuples for the review wizard. Upstream
    failures raise MetadataError (the wizard catches it and offers manual
    entry) instead of permanently memoizing an empty result."""
    return [
        (work["id"], f"{work['title']} by {', '.join(work['authors'])}")
        for work in search_openlibrary(search)
    ]


def _page_count(value):
    """Coerce an OpenLibrary page count to an int: 'number_of_pages' is a
    number, but the 'pagination' fallback is free text like 'xii, 340 p.' --
    extract the first integer, or fall back to 0."""
    match = re.search(r"\d+", str(value)) if value else None
    return int(match.group()) if match else 0


@time_taken
@cache
def get_openlibrary_editions_data(work_id):
    """A work's editions as structured dicts, filtered to languages I read
    and sorted like the wizard shows them. Raises MetadataError upstream
    failure."""
    data = _fetch_json(f"https://openlibrary.org/works/{work_id}/editions.json")
    result = []
    # we don't paginate, fuckit
    known_languages = ("/languages/eng", "/languages/ger", "/languages/lat")
    for edition in data.get("entries") or []:
        language = edition["languages"][0]["key"] if edition.get("languages") else ""
        if language and language not in known_languages:
            continue
        language = language.split("/")[-1] if language else language
        edition_id = edition["key"].split("/")[-1]
        result.append(
            {
                "id": edition_id,
                "title": edition["title"],
                "publish_date": edition.get("publish_date", ""),
                "language": language,
                "pages": _page_count(
                    edition.get("number_of_pages", edition.get("pagination"))
                ),
                "cover_url": f"https://covers.openlibrary.org/b/olid/{edition_id}-M.jpg",
            }
        )
    return sorted(result, key=lambda e: (e["language"] or "zzz", -e["pages"]))


@time_taken
@cache
def get_openlibrary_editions(work_id):
    """Editions as (id, label) choice tuples for the review wizard."""
    return [
        (
            edition["id"],
            f"{edition['title']}: {edition['publish_date']}, "
            f"{edition['language']}, {edition['pages']} pages",
        )
        for edition in get_openlibrary_editions_data(work_id)
    ]


@time_taken
@cache
def get_openlibrary_book(isbn=None, olid=None):
    if isbn:
        search = f"ISBN:{isbn}"
    elif olid:
        search = f"OLID:{olid}"
    return next(
        iter(
            _fetch_json(
                f"https://openlibrary.org/api/books?bibkeys={search}&format=json&jscmd=data"
            ).values()
        )
    )


@time_taken
@cache
def get_openlibrary_book_data(olid):
    """A single edition, normalized to the field names our book endpoints
    (PATCH /api/books/, queue add, review metadata) expect. Returns None when
    OpenLibrary has no record for the id; raises MetadataError on upstream
    failure."""
    try:
        data = get_openlibrary_book(olid=olid)
    except StopIteration:
        # OpenLibrary returns an empty object for unknown ids.
        return None
    identifiers = data.get("identifiers") or {}

    def first_identifier(key):
        values = identifiers.get(key) or []
        return values[0] if values else None

    year = re.search(r"\d{4}", str(data.get("publish_date") or ""))
    return {
        "title": data.get("title"),
        "author_name": " & ".join(
            author["name"] for author in data.get("authors") or []
        ),
        "openlibrary_id": first_identifier("openlibrary") or olid,
        "isbn13": first_identifier("isbn_13"),
        "isbn10": first_identifier("isbn_10"),
        "goodreads_id": first_identifier("goodreads"),
        "pages": data.get("number_of_pages"),
        "publication_year": int(year.group(0)) if year else None,
        "cover_source": (data.get("cover") or {}).get("large"),
    }


@time_taken
@cache
def get_goodreads_book(goodreads_id):
    response = requests.get(
        f"https://www.goodreads.com/book/show/{goodreads_id}-placeholder", timeout=5
    )

    if not response.ok:
        return {}
    # parse with beautifulsoup
    from bs4 import BeautifulSoup  # noqa: PLC0415

    html = BeautifulSoup(response.text, "html.parser")
    # there is data in <script type="application/ld+json">
    try:
        json_data = json.loads(
            html.select_one("script[type='application/ld+json']").text
        )
    except (AttributeError, KeyError, ValueError):
        return {}
    result = {
        "title": json_data["name"],
        "cover_source": json_data.get("image"),
        "pages": json_data.get("numberOfPages"),
        "isbn": json_data.get("isbn"),
    }
    details = html.select_one(".FeaturedDetails").text
    # Year is in the format "First published <optional: month> <year>"
    year = re.search(r"First published.*(\d{4})", details)
    if year:
        result["publication_year"] = int(year.group(1))
    if not result.get("publication_year"):
        for dl in html.select("dl"):
            term = dl.select_one("dt").text
            content = dl.select_one("dd").text
            if "published" in term:
                # find the year with a regex
                year = re.search(r"\d{4}", content)
                if year:
                    result["publication_year"] = int(year.group(0))
    return result


def merge_goodreads(book):
    if not book.goodreads_id:
        return
    goodreads_data = get_goodreads_book(book.goodreads_id)
    if not goodreads_data:
        raise RuntimeError(f"Failed to get goodreads data for {book.title}")
    logger.info("Got goodreads data for %s", book.title)
    if not book.cover and goodreads_data.get("cover_source"):
        book.cover_source = goodreads_data["cover_source"]
        logger.info("Setting cover for %s", book.title)
    if goodreads_data.get("publication_year") and (
        not book.publication_year
        or book.publication_year > goodreads_data["publication_year"]
    ):
        book.publication_year = goodreads_data["publication_year"]
        logger.info("Setting publication year for %s", book.title)
    if goodreads_data.get("pages") and (
        not book.pages or book.pages < goodreads_data["pages"]
    ):
        book.pages = goodreads_data["pages"]
        logger.info("Setting pages for %s", book.title)
    if len(goodreads_data.get("isbn")) == 13 and not book.isbn:
        book.isbn = goodreads_data["isbn"]
        logger.info("Setting isbn for %s", book.title)
    if len(goodreads_data.get("isbn")) == 10 and not book.isbn10:
        book.isbn10 = goodreads_data["isbn"]
        logger.info("Setting isbn10 for %s", book.title)
    book.save()
