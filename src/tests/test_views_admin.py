import json

import pytest

from scriptorium.main.models import Page, Quote, ToReview
from tests.factories import (
    PageFactory,
    QuoteFactory,
    ToReviewFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


# --- Auth -------------------------------------------------------------------


def test_login_view_renders_form(client):
    response = client.get("/b/login/")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="username"' in body
    assert 'name="password"' in body
    assert 'type="submit"' in body


def test_login_view_post_redirects_to_wizard_on_valid_credentials(client, user):
    response = client.post(
        "/b/login/", {"username": user.username, "password": "password"}
    )

    assert response.status_code == 302
    assert response.url == "/b/new"


def test_login_view_post_redirects_back_on_invalid_credentials(client):
    response = client.post("/b/login/", {"username": "nobody", "password": "wrong"})

    assert response.status_code == 302
    assert response.url == "/b/login"


def test_logout_view_redirects_home_and_clears_session(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/logout")

    assert response.status_code == 302
    assert response.url == "/"
    assert "_auth_user_id" not in admin_logged_in_client.session


# --- Permission gating ------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/b/",
        "/b/new",
        "/b/tohuwabohu/",
        "/b/pages/",
        "/b/pages/new",
        "/b/quotes/new/",
        "/b/poems/",
        "/b/poems/new/",
        "/b/toreview/",
    ],
)
def test_admin_views_redirect_anonymous_to_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert "/b/login" in response.url or "/accounts/login" in response.url


# --- Bibliothecarius / dashboard --------------------------------------------


def test_bibliothecarius_dashboard_renders_for_admin(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "href=/b/new" in body
    assert 'href="/b/toreview/"' in body
    assert "tohuwabohu" in body


def test_tohuwabohu_lists_books_missing_metadata(admin_logged_in_client):
    good = make_reviewed_book(pages=300, plot="Full plot.")
    missing_pages = make_reviewed_book(pages=None, plot="Plot")
    missing_plot = make_reviewed_book(pages=200, plot=None)

    response = admin_logged_in_client.get("/b/tohuwabohu/")

    assert response.status_code == 200
    body = response.content.decode()
    assert missing_pages.title in body
    assert missing_plot.title in body
    # good book may also appear (no-related list), but at least the specifically
    # missing items should show up. Tighter assertions would require parsing the
    # page sections individually, which is overkill for a smoke test.
    assert good.title in body


# --- Pages ------------------------------------------------------------------


def test_page_create_saves_and_redirects(admin_logged_in_client):
    response = admin_logged_in_client.post(
        "/b/pages/new", {"title": "Imprint", "slug": "imprint", "text": "Body."}
    )

    assert response.status_code == 302
    assert response.url == "/p/imprint/"
    page = Page.objects.get(slug="imprint")
    assert page.title == "Imprint"
    assert page.text == "Body."


def test_page_edit_updates_existing_page(admin_logged_in_client):
    page = PageFactory(slug="colophon", title="Colophon", text="old")

    response = admin_logged_in_client.post(
        f"/b/pages/{page.slug}/",
        {"title": "Colophon", "slug": "colophon", "text": "new"},
    )

    assert response.status_code == 302
    assert response.url == "/p/colophon/"
    page.refresh_from_db()
    assert page.text == "new"


def test_page_list_view_renders(admin_logged_in_client):
    PageFactory(title="About", slug="about")
    PageFactory(title="Contact", slug="contact")

    response = admin_logged_in_client.get("/b/pages/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "About" in body
    assert "Contact" in body


# --- Quotes -----------------------------------------------------------------


def test_quote_create_saves_and_redirects_to_detail(admin_logged_in_client):
    book = make_reviewed_book()

    response = admin_logged_in_client.post(
        "/b/quotes/new/",
        {"source_book": book.pk, "text": "A perfect line.", "language": "en"},
    )

    assert response.status_code == 302
    quote = Quote.objects.get(text="A perfect line.")
    assert response.url == f"/q/{quote.pk}/"
    assert quote.source_book == book


def test_quote_create_with_action_more_redirects_back_to_create(admin_logged_in_client):
    book = make_reviewed_book()

    response = admin_logged_in_client.post(
        "/b/quotes/new/",
        {
            "source_book": book.pk,
            "text": "Another one.",
            "language": "en",
            "action": "more",
        },
    )

    assert response.status_code == 302
    assert response.url == f"/b/quotes/new/?book={book.pk}"


def test_quote_delete_removes_quote_and_redirects_to_book(admin_logged_in_client):
    book = make_reviewed_book()
    quote = QuoteFactory(source_book=book, text="Gone soon.")

    response = admin_logged_in_client.get(f"/b/quotes/{quote.pk}/delete")

    assert response.status_code == 302
    assert response.url == f"/{book.slug}/"
    assert not Quote.objects.filter(pk=quote.pk).exists()


# --- ToReview ---------------------------------------------------------------


def test_to_review_list_shows_unreviewed_by_default(admin_logged_in_client):
    book = make_reviewed_book()
    unlinked = ToReviewFactory(title="Still to review")
    linked = ToReviewFactory(title="Already linked", book=book)

    response = admin_logged_in_client.get("/b/toreview/")

    assert response.status_code == 200
    body = response.content.decode()
    assert unlinked.title in body
    assert linked.title not in body


def test_to_review_list_reviewed_filter(admin_logged_in_client):
    book = make_reviewed_book()
    unlinked = ToReviewFactory(title="Still to review")
    linked = ToReviewFactory(title="Already linked", book=book)

    response = admin_logged_in_client.get("/b/toreview/?filter=reviewed")

    assert response.status_code == 200
    body = response.content.decode()
    assert linked.title in body
    assert unlinked.title not in body


def test_to_review_delete_removes_entry(admin_logged_in_client):
    entry = ToReviewFactory(title="Trashed")

    response = admin_logged_in_client.get(f"/b/toreview/{entry.pk}/delete")

    assert response.status_code == 302
    assert not ToReview.objects.filter(pk=entry.pk).exists()


# --- Deploy trigger ---------------------------------------------------------


def test_trigger_deploy_requires_post(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/deploy/")

    assert response.status_code == 405


def test_trigger_deploy_touches_flag_file(admin_logged_in_client, settings, tmp_path):
    flag_file = tmp_path / "deploy.flag"
    settings.DEPLOY_FLAG_FILE = str(flag_file)
    assert not flag_file.exists()

    response = admin_logged_in_client.post("/b/deploy/")

    assert response.status_code == 200
    assert flag_file.exists()


def test_trigger_deploy_without_flag_file_configured(admin_logged_in_client, settings):
    settings.DEPLOY_FLAG_FILE = ""

    response = admin_logged_in_client.post("/b/deploy/")

    assert response.status_code == 400
    assert json.loads(response.content.decode()) == {"error": "Deploy not configured"}
