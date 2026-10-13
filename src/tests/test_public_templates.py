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


