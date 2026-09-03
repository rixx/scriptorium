import pytest
from django.test import Client

from scriptorium.main.models import Quote
from tests.factories import QuoteFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


@pytest.fixture
def strict_client():
    """Django's test client skips CSRF checks unless told otherwise."""
    return Client(enforce_csrf_checks=True)


def test_login_post_without_csrf_token_is_rejected(strict_client, user):
    response = strict_client.post(
        "/b/login/", {"username": user.username, "password": "password"}
    )

    assert response.status_code == 403
    assert "_auth_user_id" not in strict_client.session


def test_logout_without_csrf_token_keeps_session(strict_client, user):
    strict_client.force_login(user)

    response = strict_client.post("/b/logout")

    assert response.status_code == 403
    assert "_auth_user_id" in strict_client.session


def test_quote_delete_without_csrf_token_keeps_quote(strict_client, user):
    strict_client.force_login(user)
    quote = QuoteFactory(source_book=make_reviewed_book(), text="Stays.")

    response = strict_client.post(f"/b/quotes/{quote.pk}/delete")

    assert response.status_code == 403
    assert Quote.objects.filter(pk=quote.pk).exists()


def test_quote_delete_rejects_get(admin_logged_in_client):
    quote = QuoteFactory(source_book=make_reviewed_book(), text="Stays.")

    response = admin_logged_in_client.get(f"/b/quotes/{quote.pk}/delete")

    assert response.status_code == 405
    assert Quote.objects.filter(pk=quote.pk).exists()


def test_form_post_with_csrf_token_is_accepted(strict_client, user):
    page = strict_client.get("/b/login/")
    token = page.cookies["csrftoken"].value

    response = strict_client.post(
        "/b/login/",
        {
            "username": user.username,
            "password": "password",
            "csrfmiddlewaretoken": token,
        },
    )

    assert response.status_code == 302
    assert "_auth_user_id" in strict_client.session


def test_api_bearer_post_bypasses_csrf(api_token):
    """API clients hold no session cookie, so CSRF does not apply to them."""
    client = Client(
        enforce_csrf_checks=True, headers={"Authorization": f"Bearer {api_token.token}"}
    )
    book = make_reviewed_book(title="Quotable")

    response = client.post(
        f"/api/books/{book.slug}/quotes/",
        data={"text": "Fresh.", "language": "en"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Quote.objects.filter(source_book=book, text="Fresh.").exists()
