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
    data = requests.get(f"https://openlibrary.org/works/{work_id}/editions.json").json()
    result = []
    # we don't paginate, fuckit
    known_languages = ("/languages/eng", "/languages/ger", "/languages/lat")
    for edition in data["entries"]:
        language = edition["languages"][0]["key"] if edition.get("languages") else ""
        if language and language not in known_languages:
            continue
        language = language.split("/")[-1] if language else language
        result.append((
            edition["key"].split("/")[-1],
            f"{edition['title']}: {edition.get('publish_date' or '')}, {language}, {edition.get('number_of_pages', edition.get('pagination'))} pages",
            ))
    return result


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
