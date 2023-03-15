import urllib.parse

import requests


def search_book(search):
    query = urllib.parse.quote(search)
    url = f"https://openlibrary.org/search.json?q={query}"
    response = requests.get(url).json()
    result = []
    for item in response["docs"]:
        result.append(
            (
                item["key"].split("/")[-1],
                f"{item['title']} by {', '.join(item.get('author_name') or [])}",
            )
        )
    return result


def get_openlibrary_editions(work_id):
    result = requests.get(
        f"https://openlibrary.org/works/{work_id}/editions.json"
    ).json()
    # we don't paginate, fuckit
    known_languages = ("/languages/eng", "/languages/ger", "/languages/lat")
    return [
        (
            r["key"].split("/")[-1],
            f"{r.get('publish_date' or ['', ''])[0], r.get('languages', [''])[0].split('/')[-1]}, {r.get('number_of_pages', r.get('pagination'))} pages",
        )
        for r in result["entries"]
        if not r.get("languages")
        or any(lang in known_languages for lang in r["languages"])
        and r.get("covers")
        and r["covers"][0] != -1
    ]


def get_openlibrary_book(isbn=None, olid=None):
    if isbn:
        search = f"ISBN:{isbn}"
    elif olid:
        search = f"OLID:{olid}"
    return list(
        requests.get(
            f"https://openlibrary.org/api/books?bibkeys={search}&format=json&jscmd=data"
        )
        .json()
        .values()
    )[0]
