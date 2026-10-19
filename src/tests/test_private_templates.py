import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from django.conf import settings
from django.test import Client

from scriptorium.main.models import BookStatus
from tests.factories import ApiTokenFactory, BookFactory

pytestmark = pytest.mark.django_db

ADMIN_NAV = [
    "/b/toreview/",
    "/b/new/",
    "/b/pages/",
    "/b/poems/",
    "/b/tokens/",
    "/b/tohuwabohu/",
    "/b/",
]
TEMPLATES = Path(settings.BASE_DIR) / "scriptorium" / "main" / "templates"


def _soup(response):
    return BeautifulSoup(response.content.decode(), "html.parser")


def _admin_nav(response):
    nav = _soup(response).find("nav", class_="admin-nav")
    return nav and [a["href"] for a in nav.find_all("a")]


@pytest.mark.parametrize(
    "url", ["/b/", "/b/toreview/", "/b/tokens/", "/b/pages/", "/b/poems/"]
)
def test_private_pages_show_admin_nav_instead_of_queue_banner(
    admin_logged_in_client, url
):
    BookFactory(status=BookStatus.TO_REVIEW)

    response = admin_logged_in_client.get(url)

    assert _admin_nav(response) == ADMIN_NAV
    assert _soup(response).find(class_="alert") is None


def test_public_pages_show_queue_banner_but_no_admin_nav(admin_logged_in_client):
    BookFactory(status=BookStatus.TO_REVIEW)

    response = admin_logged_in_client.get("/")

    assert _admin_nav(response) is None
    assert _soup(response).find(class_="alert").find("a")["href"] == "/queue/"


def test_login_page_uses_admin_styling_without_admin_nav():
    response = Client().get("/b/login/")

    soup = _soup(response)
    assert _admin_nav(response) is None
    assert soup.find("h2") is not None
    assert [b["type"] for b in soup.find("main").find_all("button")] == ["submit"]
    stylesheets = [link["href"] for link in soup.find_all("link", rel="stylesheet")]
    assert any(href.endswith("bstyle.css") for href in stylesheets)


def test_destructive_queue_and_token_forms_ask_for_confirmation(
    admin_logged_in_client, user
):
    queued = BookFactory(status=BookStatus.TO_REVIEW)
    token = ApiTokenFactory(user=user)

    queue = _soup(admin_logged_in_client.get("/b/toreview/"))
    tokens = _soup(admin_logged_in_client.get("/b/tokens/"))

    confirmed = {
        form["action"]: form.has_attr("data-confirm")
        for soup in (queue, tokens)
        for form in soup.find("main").find_all("form", class_="inline")
    }
    assert confirmed == {
        f"/b/toreview/{queued.pk}/delete/": True,
        f"/b/tokens/{token.pk}/delete/": True,
    }


def test_templates_have_no_bare_submit_inputs_or_unslashed_private_urls():
    offenders = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        source = path.read_text()
        problems = re.findall(r'<input type="submit"', source)
        problems += [
            url
            for url in re.findall(r'(?:href|action)="(/b/[^"{]*)"', source)
            if not url.endswith("/")
        ]
        problems += re.findall(r"(?:href|action)=[^\"'\s>]+", source)
        if problems:
            offenders[str(path.relative_to(TEMPLATES))] = problems

    assert offenders == {}
