import json
import re
import urllib.parse
from functools import cache

import requests
from django.conf import settings


# add profiling decorator
def time_taken(func):
    def wrapper(*args, **kwargs):
        if not settings.DEBUG:
            return func(*args, **kwargs)

        import time

        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"Time taken for {func.__name__}: {end - start:.2f}s")
        return result

    return wrapper


@time_taken
@cache
def search_book(search):
    query = urllib.parse.quote(search)
    url = f"https://openlibrary.org/search.json?q={query}"
    # timeout is 5 seconds
    try:
        response = requests.get(url, timeout=5).json()
    except Exception:
        return []
    result = []
    for item in response["docs"]:
        result.append(
            (
                item["key"].split("/")[-1],
                f"{item['title']} by {', '.join(item.get('author_name') or [])}",
            )
        )
    return result


@time_taken
@cache
def get_openlibrary_editions(work_id):
    data = requests.get(
        f"https://openlibrary.org/works/{work_id}/editions.json", timeout=5
    ).json()
    result = []
    # we don't paginate, fuckit
    known_languages = ("/languages/eng", "/languages/ger", "/languages/lat")
    for edition in data["entries"]:
        language = edition["languages"][0]["key"] if edition.get("languages") else ""
        if language and language not in known_languages:
            continue
        language = language.split("/")[-1] if language else language
        pages = edition.get("number_of_pages", edition.get("pagination")) or 0
        result.append(
            (
                edition["key"].split("/")[-1],
                f"{edition['title']}: {edition.get('publish_date' or '')}, {language}, {pages} pages",
                {"lang": language, "pages": pages},
            )
        )
    result = sorted(result, key=lambda x: (x[2]["lang"] or "zzz", -int(x[2]["pages"])))
    return [(r[0], r[1]) for r in result]


@time_taken
@cache
def get_openlibrary_book(isbn=None, olid=None):
    if isbn:
        search = f"ISBN:{isbn}"
    elif olid:
        search = f"OLID:{olid}"
    return list(
        requests.get(
            f"https://openlibrary.org/api/books?bibkeys={search}&format=json&jscmd=data",
            timeout=5,
        )
        .json()
        .values()
    )[0]


@time_taken
@cache
def get_goodreads_book(goodreads_id):
    response = requests.get(
        f"https://www.goodreads.com/book/show/{goodreads_id}-placeholder",
        timeout=5,
    )

    if not response.ok:
        return {}
    # parse with beautifulsoup
    from bs4 import BeautifulSoup

    html = BeautifulSoup(response.text, "html.parser")
    # there is data in <script type="application/ld+json">
    try:
        json_data = json.loads(
            html.select_one("script[type='application/ld+json']").text
        )
    except Exception:
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
        raise Exception(f"Failed to get goodreads data for {book.title}")
    print(f"Got goodreads data for {book.title}")
    if not book.cover and goodreads_data.get("cover_source"):
        book.cover_source = goodreads_data["cover_source"]
        print(f"Setting cover for {book.title}")
    if goodreads_data.get("publication_year") and (
        not book.publication_year
        or book.publication_year > goodreads_data["publication_year"]
    ):
        book.publication_year = goodreads_data["publication_year"]
        print(f"Setting publication year for {book.title}")
    if goodreads_data.get("pages") and (
        not book.pages or book.pages < goodreads_data["pages"]
    ):
        book.pages = goodreads_data["pages"]
        print(f"Setting pages for {book.title}")
    if len(goodreads_data.get("isbn")) == 13 and not book.isbn:
        book.isbn = goodreads_data["isbn"]
        print(f"Setting isbn for {book.title}")
    if len(goodreads_data.get("isbn")) == 10 and not book.isbn10:
        book.isbn10 = goodreads_data["isbn"]
        print(f"Setting isbn10 for {book.title}")
    book.save()
