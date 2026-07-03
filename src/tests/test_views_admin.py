import datetime as dt
import json

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage

from scriptorium.main import metadata
from scriptorium.main.models import (
    ApiToken,
    Author,
    Book,
    BookStatus,
    Page,
    Poem,
    PoemStatus,
    Quote,
    Read,
    Tag,
)
from scriptorium.main.views.admin import ReviewCreate, show_edition_step
from tests.factories import (
    ApiTokenFactory,
    AuthorFactory,
    BookFactory,
    PageFactory,
    PoemFactory,
    QuoteFactory,
    ReadFactory,
    SeriesFactory,
    TagFactory,
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
        "/b/tokens/",
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


def test_to_review_list_shows_books_waiting_for_review(admin_logged_in_client):
    reviewed = make_reviewed_book(title="Already reviewed")
    queued = BookFactory(title="Still queued", status=BookStatus.TO_READ)
    waiting = BookFactory(title="Waiting for review", status=BookStatus.TO_REVIEW)
    ReadFactory(book=waiting, finished_on=dt.date(2024, 6, 1))

    response = admin_logged_in_client.get("/b/toreview/")

    assert response.status_code == 200
    body = response.content.decode()
    assert waiting.title in body
    assert "2024-06-01" in body
    assert reviewed.title not in body
    assert queued.title not in body


def test_to_review_list_includes_stale_rereads(admin_logged_in_client):
    """A published book reread after its last review edit needs a review
    refresh and shows up in the queue alongside unreviewed books."""
    stale = make_reviewed_book(title="Reread since review")
    Book.all_objects.filter(pk=stale.pk).update(review_updated=dt.date(2020, 1, 1))
    fresh = make_reviewed_book(title="Review still fresh")

    response = admin_logged_in_client.get("/b/toreview/")

    body = response.content.decode()
    assert stale.title in body
    assert fresh.title not in body


def test_to_review_edit_get_renders_initial_values(admin_logged_in_client):
    author = AuthorFactory(name="Some One", name_slug="some-one")
    book = BookFactory(
        title="Queued",
        title_slug="queued",
        primary_author=author,
        series=SeriesFactory(name="A Cycle", name_slug="a-cycle"),
        series_position="2",
        status=BookStatus.TO_REVIEW,
        plot="A scholar is trapped in an endless house.",
    )
    ReadFactory(book=book, finished_on=dt.date(2024, 5, 1), notes="Holiday read.")

    response = admin_logged_in_client.get(f"/b/toreview/{book.pk}/")

    assert response.status_code == 200
    initial = response.context["form"].initial
    assert initial["title"] == "Queued"
    assert initial["author"] == "Some One"
    assert initial["series"] == "A Cycle"
    assert initial["series_position"] == "2"
    assert initial["date"] == dt.date(2024, 5, 1)
    assert initial["notes"] == "Holiday read."
    assert initial["plot"] == "A scholar is trapped in an endless house."


def test_to_review_edit_shows_metadata_and_highlights(admin_logged_in_client):
    """The queue edit page is the review workbench: it shows the book's
    stored metadata and the KOReader highlights (with their data blob for
    the copy button)."""
    book = BookFactory(
        title="Queued",
        title_slug="queued",
        status=BookStatus.TO_REVIEW,
        pages=304,
        publication_year=1969,
        isbn13="9780441478125",
        source="koreader",
    )
    ReadFactory(
        book=book,
        finished_on=dt.date(2024, 5, 1),
        format="ebook",
        total_time_seconds=25440,
        highlights=[
            {
                "text": "Light is the left hand of darkness.",
                "note": "gorgeous",
                "chapter": "Chapter 16",
                "pageno": 233,
            }
        ],
    )

    response = admin_logged_in_client.get(f"/b/toreview/{book.pk}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert book.primary_author.name in body
    assert "304" in body
    assert "1969" in body
    assert "9780441478125" in body
    assert "koreader" in body
    assert "7.1h reading time" in body
    assert "Light is the left hand of darkness." in body
    assert "gorgeous" in body
    assert "Chapter 16" in body
    assert "Copy all" in body
    assert f'id="highlights-data-{book.reads.get().pk}"' in body


def test_to_review_edit_post_updates_existing_book_and_read(admin_logged_in_client):
    author = AuthorFactory(name="Some One", name_slug="some-one")
    book = BookFactory(
        title="Queued",
        title_slug="queued",
        primary_author=author,
        status=BookStatus.TO_REVIEW,
    )
    read = ReadFactory(
        book=book, finished_on=dt.date(2024, 5, 1), notes="Holiday read."
    )

    response = admin_logged_in_client.post(
        f"/b/toreview/{book.pk}/",
        {
            "title": "Queued, Corrected",
            "author": "Some One",
            "date": "2024-05-03",
            "series": "A Cycle",
            "series_position": "2",
            "notes": "Holiday read.",
            "plot": "A scholar is trapped in an endless house.",
        },
    )

    assert response.status_code == 302
    assert response.url == "/b/toreview/"
    book.refresh_from_db()
    assert book.title == "Queued, Corrected"
    assert book.title_slug == "queued-corrected"
    assert book.series.name == "A Cycle"
    assert book.series_position == "2"
    assert book.plot == "A scholar is trapped in an endless house."
    read.refresh_from_db()
    assert read.finished_on == dt.date(2024, 5, 3)
    assert read.notes == "Holiday read."
    assert Book.all_objects.count() == 1
    assert Read.objects.count() == 1


def test_to_review_edit_creates_read_when_none_recorded(admin_logged_in_client):
    """Queue entries can exist without a Read row (e.g. from imports);
    editing one records the read instead of crashing."""
    book = BookFactory(
        title="No Read Yet", title_slug="no-read-yet", status=BookStatus.TO_REVIEW
    )

    response = admin_logged_in_client.post(
        f"/b/toreview/{book.pk}/",
        {
            "title": "No Read Yet",
            "author": book.primary_author.name,
            "date": "2024-05-03",
            "series": "",
            "series_position": "",
            "notes": "",
        },
    )

    assert response.status_code == 302
    read = Read.objects.get(book=book)
    assert read.finished_on == dt.date(2024, 5, 3)
    assert read.source == "manual"
    assert read.notes is None


def test_to_review_edit_rejects_published_books(admin_logged_in_client):
    book = make_reviewed_book(title="Published Already")

    response = admin_logged_in_client.get(f"/b/toreview/{book.pk}/")

    assert response.status_code == 404


def test_to_review_delete_removes_book(admin_logged_in_client):
    book = BookFactory(title="Trashed", status=BookStatus.TO_REVIEW)

    response = admin_logged_in_client.get(f"/b/toreview/{book.pk}/delete")

    assert response.status_code == 302
    assert not Book.all_objects.filter(pk=book.pk).exists()


def test_to_review_delete_rejects_published_books(admin_logged_in_client):
    book = make_reviewed_book(title="Keep me")

    response = admin_logged_in_client.get(f"/b/toreview/{book.pk}/delete")

    assert response.status_code == 404
    assert Book.all_objects.filter(pk=book.pk).exists()


def test_to_review_list_reread_rows_link_to_review_edit_and_dismiss(
    admin_logged_in_client,
):
    """Rereads of published books don't fit the to-review edit/delete views:
    their rows link to the existing review instead and offer a dismiss
    action, while unreviewed rows keep the edit/delete links."""
    stale = make_reviewed_book(title="Reread since review")
    Book.all_objects.filter(pk=stale.pk).update(review_updated=dt.date(2020, 1, 1))
    waiting = BookFactory(title="Waiting for review", status=BookStatus.TO_REVIEW)

    response = admin_logged_in_client.get("/b/toreview/")

    body = response.content.decode()
    assert f'href="/b/{stale.slug}/"' in body
    assert f'action="/b/toreview/{stale.pk}/dismiss"' in body
    assert f'href="/b/toreview/{stale.pk}/"' not in body
    assert f'href="/b/toreview/{stale.pk}/delete"' not in body
    assert f'href="/b/toreview/{waiting.pk}/"' in body
    assert f'href="/b/toreview/{waiting.pk}/delete"' in body
    assert f'action="/b/toreview/{waiting.pk}/dismiss"' not in body


def test_to_review_dismiss_clears_reread_from_queue(admin_logged_in_client):
    stale = make_reviewed_book(title="Reread since review")
    Book.all_objects.filter(pk=stale.pk).update(review_updated=dt.date(2020, 1, 1))
    assert Book.all_objects.needs_review().filter(pk=stale.pk).exists()

    response = admin_logged_in_client.post(f"/b/toreview/{stale.pk}/dismiss")

    assert response.status_code == 302
    assert response.url == "/b/toreview/"
    stale.refresh_from_db()
    assert stale.review_updated == dt.datetime.now(tz=dt.UTC).date()
    assert not Book.all_objects.needs_review().filter(pk=stale.pk).exists()


def test_to_review_dismiss_rejects_unreviewed_books(admin_logged_in_client):
    book = BookFactory(title="Needs a review first", status=BookStatus.TO_REVIEW)
    ReadFactory(book=book, finished_on=dt.date(2024, 6, 1))

    response = admin_logged_in_client.post(f"/b/toreview/{book.pk}/dismiss")

    assert response.status_code == 404
    assert Book.all_objects.needs_review().filter(pk=book.pk).exists()


def test_to_review_dismiss_requires_post(admin_logged_in_client):
    stale = make_reviewed_book(title="Reread since review")
    Book.all_objects.filter(pk=stale.pk).update(review_updated=dt.date(2020, 1, 1))

    response = admin_logged_in_client.get(f"/b/toreview/{stale.pk}/dismiss")

    assert response.status_code == 405
    stale.refresh_from_db()
    assert stale.review_updated == dt.date(2020, 1, 1)


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


# --- Login form invalid branch ---------------------------------------------


def test_login_view_post_with_missing_fields_redirects_back(client):
    """Covers the form.is_valid() == False branch: an empty POST can never
    authenticate and must bounce back to the login page."""
    response = client.post("/b/login/", {})

    assert response.status_code == 302
    assert response.url == "/b/login"


# --- AuthorEdit -------------------------------------------------------------


def test_author_edit_get_object_renders_author_form(admin_logged_in_client):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")

    response = admin_logged_in_client.get("/b/ursula-k-le-guin/")

    assert response.status_code == 200
    assert response.context["form"].instance == author


def test_author_edit_post_updates_author_and_redirects(admin_logged_in_client):
    author = AuthorFactory(name="Old Name", name_slug="old-slug")

    response = admin_logged_in_client.post(
        "/b/old-slug/",
        {"name": "Old Name", "name_slug": "new-slug", "text": "Fresh bio."},
    )

    assert response.status_code == 302
    assert response.url == "/new-slug/"
    author.refresh_from_db()
    assert author.name_slug == "new-slug"
    assert author.text == "Fresh bio."


# --- Review wizard ----------------------------------------------------------


class _FakeWizard:
    """Minimal stand-in for formtools' WizardView, used only to exercise
    show_edition_step in isolation."""

    def __init__(self, select_data):
        self._select_data = select_data

    def get_cleaned_data_for_step(self, step):
        assert step == "select"
        return self._select_data


def test_show_edition_step_hidden_for_manual_entry():
    assert show_edition_step(_FakeWizard({"search_selection": "manual"})) is False


def test_show_edition_step_visible_for_openlibrary_work():
    assert show_edition_step(_FakeWizard({"search_selection": "OL1W"})) is True


def test_show_edition_step_visible_when_no_select_data_yet():
    assert show_edition_step(_FakeWizard(None)) is True


def _wizard_view(rf, steps_data, form_list=None):
    """Build a ReviewCreate instance with request + messages storage set up and
    with get_cleaned_data_for_step / get_form_list replaced by stubs. This lets
    us unit-test the two interesting methods (get_form_kwargs, done) without
    walking the full SessionWizardView storage machinery."""
    request = rf.get("/b/new")
    request.session = {}
    request._messages = FallbackStorage(request)
    view = ReviewCreate()
    view.request = request
    view.get_cleaned_data_for_step = steps_data.get
    if form_list is None:
        form_list = {
            "search": None,
            "select": None,
            "edition": None,
            "book": None,
            "review": None,
        }
    view.get_form_list = lambda: form_list
    return view


def test_review_create_get_form_kwargs_select_calls_search_book(rf, monkeypatch):

    monkeypatch.setattr(metadata, "search_book", lambda s: [("OL1W", f"Hit: {s}")])
    view = _wizard_view(rf, {"search": {"search_input": "Dispossessed"}})

    kwargs = view.get_form_kwargs(step="select")

    assert kwargs == {"works": [("OL1W", "Hit: Dispossessed")]}


def test_review_create_get_form_kwargs_select_falls_back_on_error(rf, monkeypatch):

    def boom(_):
        raise RuntimeError("openlibrary is down")

    monkeypatch.setattr(metadata, "search_book", boom)
    view = _wizard_view(rf, {"search": {"search_input": "anything"}})

    kwargs = view.get_form_kwargs(step="select")

    assert kwargs == {"works": [("manual", "Enter manually")]}


def test_review_create_get_form_kwargs_edition_calls_openlibrary(rf, monkeypatch):

    monkeypatch.setattr(
        metadata, "get_openlibrary_editions", lambda wid: [("OL1M", f"Edition {wid}")]
    )
    view = _wizard_view(rf, {"select": {"search_selection": "OL9W"}})

    kwargs = view.get_form_kwargs(step="edition")

    assert kwargs == {"editions": [("OL1M", "Edition OL9W")]}


def test_review_create_get_form_kwargs_edition_skipped_for_manual_select(rf):
    view = _wizard_view(rf, {"select": {"search_selection": "manual"}})

    kwargs = view.get_form_kwargs(step="edition")

    assert kwargs == {}


def test_review_create_get_form_kwargs_edition_falls_back_on_error(rf, monkeypatch):

    def boom(_):
        raise RuntimeError("editions fetch failed")

    monkeypatch.setattr(metadata, "get_openlibrary_editions", boom)
    view = _wizard_view(rf, {"select": {"search_selection": "OL9W"}})

    kwargs = view.get_form_kwargs(step="edition")

    assert kwargs == {"editions": []}


def test_review_create_get_form_kwargs_book_calls_openlibrary(rf, monkeypatch):

    monkeypatch.setattr(
        metadata, "get_openlibrary_book", lambda olid=None: {"title": "T", "olid": olid}
    )
    view = _wizard_view(rf, {"edition": {"edition_selection": "OL1M"}})

    kwargs = view.get_form_kwargs(step="book")

    assert kwargs == {"openlibrary": {"title": "T", "olid": "OL1M"}}


def test_review_create_get_form_kwargs_book_falls_back_on_error(rf, monkeypatch):

    def boom(olid=None):
        raise RuntimeError("book fetch failed")

    monkeypatch.setattr(metadata, "get_openlibrary_book", boom)
    view = _wizard_view(rf, {"edition": {"edition_selection": "OL1M"}})

    kwargs = view.get_form_kwargs(step="book")

    assert kwargs == {"openlibrary": {}}


def test_review_create_get_form_kwargs_book_skips_openlibrary_in_manual_flow(rf):
    view = _wizard_view(
        rf, {}, form_list={"search": None, "select": None, "book": None, "review": None}
    )

    kwargs = view.get_form_kwargs(step="book")

    assert kwargs == {}


def test_review_create_get_form_kwargs_review_step_returns_empty(rf):
    view = _wizard_view(rf, {"select": {"search_selection": "OL1W"}})

    kwargs = view.get_form_kwargs(step="review")

    assert kwargs == {}


def test_review_create_get_form_kwargs_unknown_step_returns_empty(rf):
    """When the wizard asks for kwargs with no step (or an unrecognised one),
    every branch is skipped and we return an empty dict. Covers the 190->192
    fall-through."""
    view = _wizard_view(rf, {})

    assert view.get_form_kwargs() == {}
    assert view.get_form_kwargs(step="unknown") == {}


def test_review_create_done_creates_author_book_review_and_tags(rf):
    view = _wizard_view(
        rf,
        {
            "search": None,
            "select": None,
            "edition": None,
            "book": {
                "title": "The Dispossessed",
                "title_slug": "the-dispossessed",
                "author_name": "Ursula K. Le Guin",
                "source": "",
                "pages": 341,
                "cover_source": None,
                "goodreads_id": None,
                "isbn10": None,
                "isbn13": None,
                "publication_year": 1974,
                "series": None,
                "series_position": "",
                "tags": [],
                "new_tags": ["genre:scifi"],
                "plot": "",
            },
            "review": {
                "dates_read": [dt.date(2024, 2, 10), dt.date(2024, 3, 14)],
                "rating": 5,
                "text": "A brilliant book.",
                "tldr": "Go read it.",
                "did_not_finish": False,
            },
        },
    )

    response = view.done(form_list=[])

    assert response.status_code == 302
    author = Author.objects.get(name="Ursula K. Le Guin")
    assert author.name_slug == "ursula-k-le-guin"
    book = Book.objects.get(title="The Dispossessed")
    assert book.primary_author == author
    assert book.pages == 341
    assert book.status == BookStatus.REVIEWED
    assert response.url == f"/{book.slug}/"
    assert list(book.tags.values_list("name_slug", flat=True)) == ["scifi"]
    assert list(book.tags.values_list("category", flat=True)) == ["genre"]
    assert book.rating == 5
    assert book.text == "A brilliant book."
    assert book.tldr == "Go read it."
    assert book.latest_date == dt.date(2024, 3, 14)
    assert [read.finished_on for read in book.reads.order_by("finished_on")] == [
        dt.date(2024, 2, 10),
        dt.date(2024, 3, 14),
    ]
    assert [read.did_not_finish for read in book.reads.all()] == [False, False]


def test_review_create_done_reuses_existing_author(rf):
    existing = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    view = _wizard_view(
        rf,
        {
            "book": {
                "title": "The Lathe of Heaven",
                "title_slug": "the-lathe-of-heaven",
                "author_name": "Ursula K. Le Guin",
                "source": "",
                "pages": 184,
                "cover_source": None,
                "goodreads_id": None,
                "isbn10": None,
                "isbn13": None,
                "publication_year": 1971,
                "series": None,
                "series_position": "",
                "tags": [],
                "new_tags": [],
                "plot": "",
            },
            "review": {
                "dates_read": [dt.date(2024, 4, 1)],
                "rating": 4,
                "text": "Dream logic.",
                "tldr": "Good.",
                "did_not_finish": False,
            },
        },
    )

    view.done(form_list=[])

    book = Book.objects.get(title="The Lathe of Heaven")
    assert book.primary_author == existing
    assert Author.objects.filter(name="Ursula K. Le Guin").count() == 1
    assert list(book.tags.all()) == []


def test_review_create_done_publishes_existing_queued_book(rf):
    """Reviewing a book that already exists in the queue (status to_review,
    e.g. from the quick add form) must update that row in place instead of
    tripping over the unique (author, title_slug) constraint."""
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    queued = BookFactory(
        title="The Word for World Is Forest",
        title_slug="the-word-for-world-is-forest",
        primary_author=author,
        pages=None,
        status=BookStatus.TO_REVIEW,
    )
    view = _wizard_view(
        rf,
        {
            "book": {
                "title": "The Word for World is Forest",
                "title_slug": "the-word-for-world-is-forest",
                "author_name": "Ursula K. Le Guin",
                "source": "",
                "pages": 189,
                "cover_source": None,
                "goodreads_id": None,
                "isbn10": None,
                "isbn13": None,
                "publication_year": 1972,
                "series": None,
                "series_position": "",
                "tags": [],
                "new_tags": [],
                "plot": "",
            },
            "review": {
                "dates_read": [dt.date(2024, 5, 2)],
                "rating": 4,
                "text": "Trees.",
                "tldr": "Green.",
                "did_not_finish": False,
            },
        },
    )

    view.done(form_list=[])

    queued.refresh_from_db()
    assert queued.status == BookStatus.REVIEWED
    assert queued.title == "The Word for World is Forest"
    assert queued.pages == 189
    assert Book.all_objects.filter(primary_author=author).count() == 1
    assert queued.rating == 4
    assert queued.text == "Trees."


def _wizard_steps(book=None, review=None):
    """Cleaned wizard step data as done() receives it, with per-step
    overrides for the scenarios below."""
    book_data = {
        "title": "The Word for World Is Forest",
        "title_slug": "the-word-for-world-is-forest",
        "author_name": "Ursula K. Le Guin",
        "source": "",
        "pages": 189,
        "cover_source": None,
        "goodreads_id": None,
        "isbn10": None,
        "isbn13": None,
        "publication_year": 1972,
        "series": None,
        "series_position": "",
        "tags": [],
        "new_tags": [],
        "plot": "",
    }
    book_data.update(book or {})
    review_data = {
        "dates_read": [dt.date(2024, 5, 2)],
        "rating": 4,
        "text": "Trees.",
        "tldr": "Green.",
        "did_not_finish": False,
    }
    review_data.update(review or {})
    return {"book": book_data, "review": review_data}


def test_review_create_done_refuses_to_overwrite_published_review(rf):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    book = make_reviewed_book(
        title="The Word for World Is Forest",
        title_slug="the-word-for-world-is-forest",
        primary_author=author,
        text="Original review.",
    )
    view = _wizard_view(rf, _wizard_steps(review={"text": "Sneaky overwrite."}))

    response = view.done(form_list=[])

    assert response.status_code == 302
    assert response.url == f"/b/{book.slug}/"
    book.refresh_from_db()
    assert book.text == "Original review."
    assert [m.level_tag for m in view.request._messages] == ["error"]


def test_review_create_done_blank_fields_keep_queued_metadata(rf):
    """The wizard's book form starts blank, so empty fields must not wipe
    metadata that the queued book already carries (series, source, ...)."""
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    series = SeriesFactory(name="Hainish Cycle", name_slug="hainish-cycle")
    queued = BookFactory(
        title="The Word for World Is Forest",
        title_slug="the-word-for-world-is-forest",
        primary_author=author,
        series=series,
        series_position="6",
        source="gift",
        status=BookStatus.TO_REVIEW,
    )
    view = _wizard_view(rf, _wizard_steps())

    view.done(form_list=[])

    queued.refresh_from_db()
    assert queued.status == BookStatus.REVIEWED
    assert queued.series == series
    assert queued.series_position == "6"
    assert queued.source == "gift"


def test_review_create_done_does_not_duplicate_queued_read(rf):
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    queued = BookFactory(
        title="The Word for World Is Forest",
        title_slug="the-word-for-world-is-forest",
        primary_author=author,
        status=BookStatus.TO_REVIEW,
    )
    ReadFactory(
        book=queued, finished_on=dt.date(2024, 5, 2), notes="From the queue form."
    )
    view = _wizard_view(rf, _wizard_steps())

    view.done(form_list=[])

    read = Read.objects.get(book=queued)
    assert read.finished_on == dt.date(2024, 5, 2)
    assert read.notes == "From the queue form."


def test_review_create_done_reuses_author_slug_for_casing_variant(rf):
    existing = AuthorFactory(name="Ursula K. le Guin", name_slug="ursula-k-le-guin")
    view = _wizard_view(rf, _wizard_steps(book={"author_name": "ursula k. le guin"}))

    view.done(form_list=[])

    book = Book.objects.get(title="The Word for World Is Forest")
    assert book.primary_author == existing
    assert list(Author.objects.all()) == [existing]


# --- ReviewEdit -------------------------------------------------------------


def _book_post_data(book, tags, **overrides):
    """Minimal valid POST payload for BookEditForm + ReviewEditForm merged.
    Caller must supply at least one Tag instance because Book.tags is a
    non-blank M2M field (the form rejects an empty selection)."""
    data = {
        # BookEditForm fields
        "title": book.title,
        "title_slug": book.title_slug,
        "primary_author": book.primary_author_id,
        "additional_authors": [],
        "cover_source": "",
        "goodreads_id": "",
        "isbn10": "",
        "isbn13": "",
        "source": "",
        "pages": book.pages or "",
        "publication_year": book.publication_year or "",
        "series": "",
        "series_position": "",
        "tags": [t.pk for t in tags],
        "new_tags": "",
        "plot": "",
        # ReviewEditForm fields
        "dates_read": "2024-06-15",
        "rating": 4,
        "text": "Updated review body.",
        "tldr": "Short.",
        "did_not_finish": False,
    }
    data.update(overrides)
    return data


def test_review_edit_get_uses_book_object_and_renders_review_fields(
    admin_logged_in_client,
):
    book = make_reviewed_book(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=AuthorFactory(
            name="Ursula K. Le Guin", name_slug="ursula-k-le-guin"
        ),
    )

    response = admin_logged_in_client.get("/b/ursula-k-le-guin/the-dispossessed/")

    assert response.status_code == 200
    assert response.context["form"].instance == book
    # The unbound ReviewEditForm is rendered into the template via
    # @context-decorated review_form. We verify by looking for its field names
    # in the rendered HTML, because Jinja2 context vars don't surface in
    # response.context the same way Django template context vars do.
    body = response.content.decode()
    assert 'name="dates_read"' in body
    assert 'name="rating"' in body
    assert 'name="tldr"' in body


def test_review_edit_shows_reread_highlights(admin_logged_in_client):
    """A reread pushed from KOReader lands on the review edit page (the
    to-review views reject published books), so its highlights show up
    there, copy buttons included."""
    book = make_reviewed_book(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=AuthorFactory(
            name="Ursula K. Le Guin", name_slug="ursula-k-le-guin"
        ),
    )
    reread = ReadFactory(
        book=book,
        finished_on=dt.date(2026, 6, 1),
        highlights=[
            {
                "text": "True journey is return.",
                "note": None,
                "chapter": "Chapter 13",
                "pageno": 386,
            }
        ],
    )

    response = admin_logged_in_client.get("/b/ursula-k-le-guin/the-dispossessed/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "True journey is return." in body
    assert "Chapter 13" in body
    assert "Copy all" in body
    assert f'id="highlights-data-{reread.pk}"' in body


def test_review_edit_post_valid_saves_both_forms_and_adds_new_tag(
    admin_logged_in_client,
):
    author = AuthorFactory(name="Author Q", name_slug="author-q")
    book = make_reviewed_book(
        title="Old Title",
        title_slug="old-title",
        primary_author=author,
        pages=100,
        publication_year=2000,
    )
    existing_tag = TagFactory(category="genre", name_slug="novel", name="Novel")
    book.tags.add(existing_tag)

    response = admin_logged_in_client.post(
        f"/b/{author.name_slug}/{book.title_slug}/",
        _book_post_data(
            book,
            [existing_tag],
            title="New Title",
            tldr="Refreshed.",
            new_tags="themes:hope",
        ),
    )

    assert response.status_code == 302
    assert response.url == f"/{author.name_slug}/old-title/"
    book.refresh_from_db()
    assert book.title == "New Title"
    assert book.tldr == "Refreshed."
    assert set(book.tags.values_list("name_slug", flat=True)) == {"novel", "hope"}
    assert Tag.objects.filter(name_slug="hope", category="themes").count() == 1


def test_review_edit_post_valid_without_new_tags_skips_tag_creation(
    admin_logged_in_client,
):
    """Covers the 247->253 branch: if new_tags is empty, form_valid skips the
    Tag.create loop entirely and goes straight to the redirect."""
    author = AuthorFactory(name="Author T", name_slug="author-t")
    book = make_reviewed_book(
        title="No Tags Added", title_slug="no-tags-added", primary_author=author
    )
    tag = TagFactory(category="genre", name_slug="essay", name="Essay")
    book.tags.add(tag)
    tag_count_before = Tag.objects.count()

    response = admin_logged_in_client.post(
        f"/b/{author.name_slug}/{book.title_slug}/",
        _book_post_data(book, [tag], text="Touched body."),
    )

    assert response.status_code == 302
    assert response.url == f"/{author.name_slug}/no-tags-added/"
    assert Tag.objects.count() == tag_count_before
    book.refresh_from_db()
    assert book.text == "Touched body."


def test_review_edit_post_invalid_book_form_re_renders_with_errors(
    admin_logged_in_client,
):
    author = AuthorFactory(name="Author R", name_slug="author-r")
    book = make_reviewed_book(
        title="Keep Me", title_slug="keep-me", primary_author=author
    )
    tag = TagFactory(category="genre", name_slug="novella", name="Novella")
    book.tags.add(tag)

    response = admin_logged_in_client.post(
        f"/b/{author.name_slug}/{book.title_slug}/",
        _book_post_data(book, [tag], title=""),
    )

    assert response.status_code == 200
    assert response.context["form"].errors.get("title")
    book.refresh_from_db()
    assert book.title == "Keep Me"


def test_review_edit_post_invalid_review_form_raises(admin_logged_in_client):
    """If BookEditForm is valid but ReviewEditForm is not, form_valid raises
    ValueError — this is the sad-path branch at admin.py:241-243."""
    author = AuthorFactory(name="Author S", name_slug="author-s")
    book = make_reviewed_book(
        title="Intact", title_slug="intact", primary_author=author
    )
    tag = TagFactory(category="genre", name_slug="short", name="Short")
    book.tags.add(tag)

    with pytest.raises(ValueError):
        admin_logged_in_client.post(
            f"/b/{author.name_slug}/{book.title_slug}/",
            _book_post_data(book, [tag], rating="not-a-number"),
        )
    book.refresh_from_db()
    assert book.title == "Intact"


# --- QuoteCreate initial / form_valid branches ------------------------------


def test_quote_create_get_prefills_source_book_from_query(admin_logged_in_client):
    book = make_reviewed_book()

    response = admin_logged_in_client.get(f"/b/quotes/new/?book={book.pk}")

    assert response.status_code == 200
    assert response.context["form"].initial["source_book"] == book


def test_quote_create_get_ignores_unknown_book_query(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/quotes/new/?book=99999")

    assert response.status_code == 200
    assert "source_book" not in response.context["form"].initial


def test_quote_create_get_prefills_source_author_from_query(admin_logged_in_client):
    author = AuthorFactory()

    response = admin_logged_in_client.get(f"/b/quotes/new/?author={author.pk}")

    assert response.status_code == 200
    assert response.context["form"].initial["source_author"] == author


def test_quote_create_get_ignores_unknown_author_query(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/quotes/new/?author=99999")

    assert response.status_code == 200
    assert "source_author" not in response.context["form"].initial


def test_quote_create_more_for_author_redirects_back_with_author_param(
    admin_logged_in_client,
):
    author = AuthorFactory()

    response = admin_logged_in_client.post(
        "/b/quotes/new/",
        {
            "source_author": author.pk,
            "text": "Author quote.",
            "language": "en",
            "action": "more",
        },
    )

    assert response.status_code == 302
    assert response.url == f"/b/quotes/new/?author={author.pk}"


def test_quote_create_more_without_source_redirects_plain_new(admin_logged_in_client):
    response = admin_logged_in_client.post(
        "/b/quotes/new/", {"text": "Orphan quote.", "language": "en", "action": "more"}
    )

    assert response.status_code == 302
    assert response.url == "/b/quotes/new/"


# --- QuoteEdit form_valid branches ------------------------------------------


def test_quote_edit_saves_and_redirects_to_quote(admin_logged_in_client):
    book = make_reviewed_book()
    quote = QuoteFactory(source_book=book, text="Original.", language="en")

    response = admin_logged_in_client.post(
        f"/b/quotes/{quote.pk}/",
        {"source_book": book.pk, "text": "Edited.", "language": "en"},
    )

    assert response.status_code == 302
    assert response.url == f"/q/{quote.pk}/"
    quote.refresh_from_db()
    assert quote.text == "Edited."


def test_quote_edit_with_action_more_for_book_redirects_back(admin_logged_in_client):
    book = make_reviewed_book()
    quote = QuoteFactory(source_book=book, text="Original.", language="en")

    response = admin_logged_in_client.post(
        f"/b/quotes/{quote.pk}/",
        {"source_book": book.pk, "text": "Edited.", "language": "en", "action": "more"},
    )

    assert response.status_code == 302
    assert response.url == f"/b/quotes/new/?book={book.pk}"


def test_quote_edit_with_action_more_for_author_redirects_back(admin_logged_in_client):
    author = AuthorFactory()
    quote = QuoteFactory(source_author=author, text="Original.", language="en")

    response = admin_logged_in_client.post(
        f"/b/quotes/{quote.pk}/",
        {
            "source_author": author.pk,
            "text": "Edited.",
            "language": "en",
            "action": "more",
        },
    )

    assert response.status_code == 302
    assert response.url == f"/b/quotes/new/?author={author.pk}"


def test_quote_edit_with_action_more_without_source_redirects_plain(
    admin_logged_in_client,
):
    quote = QuoteFactory(text="Orphan.", language="en")

    response = admin_logged_in_client.post(
        f"/b/quotes/{quote.pk}/",
        {"text": "Edited orphan.", "language": "en", "action": "more"},
    )

    assert response.status_code == 302
    assert response.url == "/b/quotes/new/"


# --- QuoteDelete remaining branches -----------------------------------------


def test_quote_delete_for_author_redirects_to_author_page(admin_logged_in_client):
    author = AuthorFactory(name="Someone", name_slug="someone")
    quote = QuoteFactory(source_author=author, text="Bye.", language="en")

    response = admin_logged_in_client.get(f"/b/quotes/{quote.pk}/delete")

    assert response.status_code == 302
    assert response.url == f"/a/{author.name_slug}/"
    assert not Quote.objects.filter(pk=quote.pk).exists()


def test_quote_delete_without_source_redirects_to_quote_index(admin_logged_in_client):
    quote = QuoteFactory(text="Orphan.", language="en")

    response = admin_logged_in_client.get(f"/b/quotes/{quote.pk}/delete")

    assert response.status_code == 302
    assert response.url == "/q"
    assert not Quote.objects.filter(pk=quote.pk).exists()


# --- Poems ------------------------------------------------------------------


def test_poem_create_saves_and_redirects_to_absolute_url(admin_logged_in_client):
    author = AuthorFactory(name="Poet", name_slug="poet")

    response = admin_logged_in_client.post(
        "/b/poems/new/",
        {
            "title": "Ode",
            "slug": "ode",
            "author": author.pk,
            "text": "Lines and lines.",
            "language": "en",
            "status": PoemStatus.ARCHIVED,
        },
    )

    assert response.status_code == 302
    assert response.url == f"/{author.name_slug}/poems/ode/"
    poem = Poem.objects.get(slug="ode")
    assert poem.author == author


def test_poem_edit_get_uses_poem_and_pre_fills_instance(admin_logged_in_client):
    author = AuthorFactory(name="Poet", name_slug="poet")
    poem = PoemFactory(
        author=author, title="Old Title", slug="the-poem", text="Old body."
    )

    response = admin_logged_in_client.get(f"/b/{author.name_slug}/poems/{poem.slug}/")

    assert response.status_code == 200
    assert response.context["form"].instance == poem


def test_poem_edit_post_saves_and_redirects_to_absolute_url(admin_logged_in_client):
    author = AuthorFactory(name="Poet", name_slug="poet")
    poem = PoemFactory(
        author=author, title="Old Title", slug="the-poem", text="Old body."
    )

    response = admin_logged_in_client.post(
        f"/b/{author.name_slug}/poems/{poem.slug}/",
        {
            "title": "New Title",
            "slug": poem.slug,
            "author": author.pk,
            "text": "New body.",
            "language": "en",
            "status": PoemStatus.ARCHIVED,
        },
    )

    assert response.status_code == 302
    assert response.url == f"/{author.name_slug}/poems/{poem.slug}/"
    poem.refresh_from_db()
    assert poem.title == "New Title"
    assert poem.text == "New body."


# --- ToReview create form_valid ---------------------------------------------


def test_to_review_create_saves_book_and_read_and_redirects_back_to_new(
    admin_logged_in_client,
):
    response = admin_logged_in_client.post(
        "/b/toreview/new",
        {
            "title": "Queued",
            "author": "Some One",
            "date": "2024-05-01",
            "series": "A Cycle",
            "series_position": "2",
            "notes": "Read on holiday.",
        },
    )

    assert response.status_code == 302
    assert response.url == "/b/toreview/new"
    book = Book.all_objects.get(title="Queued")
    assert book.status == BookStatus.TO_REVIEW
    assert book.primary_author.name == "Some One"
    assert book.primary_author.name_slug == "some-one"
    assert book.series.name == "A Cycle"
    assert book.series_position == "2"
    read = Read.objects.get(book=book)
    assert read.finished_on == dt.date(2024, 5, 1)
    assert read.source == "manual"
    assert read.notes == "Read on holiday."


def test_to_review_create_get_renders_form(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/toreview/new")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'name="title"' in body
    assert 'name="author"' in body
    assert 'name="date"' in body


# --- API tokens ---------------------------------------------------------------


def test_token_list_shows_tokens_with_values(admin_logged_in_client):
    token = ApiTokenFactory(name="KOReader")
    used = ApiTokenFactory(name="CLI")
    ApiToken.objects.filter(pk=used.pk).update(
        last_used=dt.datetime(2024, 5, 1, 12, 0, tzinfo=dt.UTC)
    )

    response = admin_logged_in_client.get("/b/tokens/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "KOReader" in body
    assert token.token in body
    assert "CLI" in body
    assert "2024-05-01" in body
    assert "never" in body  # the unused token has no last_used


def test_token_create_generates_server_side_token_and_displays_it(
    admin_logged_in_client, user
):
    response = admin_logged_in_client.post(
        "/b/tokens/", {"name": "CLI", "token": "attacker-chosen"}
    )

    token = ApiToken.objects.get()
    assert response.status_code == 302
    assert response.url == f"/b/tokens/?created={token.pk}"
    assert token.user == user
    assert token.name == "CLI"
    # The token value is generated server-side, never taken from the request.
    assert token.token != "attacker-chosen"  # noqa: S105
    assert len(token.token) > 30

    followup = admin_logged_in_client.get(response.url)
    assert token.token in followup.content.decode()


def test_token_create_generates_unique_tokens(admin_logged_in_client):
    admin_logged_in_client.post("/b/tokens/", {"name": "One"})
    admin_logged_in_client.post("/b/tokens/", {"name": "Two"})

    tokens = ApiToken.objects.values_list("token", flat=True)
    assert len(tokens) == 2
    assert len(set(tokens)) == 2


def test_token_list_ignores_bogus_created_parameter(admin_logged_in_client):
    response = admin_logged_in_client.get("/b/tokens/?created=bogus")

    assert response.status_code == 200
    assert "created:" not in response.content.decode()


def test_token_revoke_deletes_token(admin_logged_in_client):
    token = ApiTokenFactory(name="Old")

    response = admin_logged_in_client.post(f"/b/tokens/{token.pk}/delete")

    assert response.status_code == 302
    assert response.url == "/b/tokens/"
    assert not ApiToken.objects.exists()


def test_token_revoke_requires_post(admin_logged_in_client):
    token = ApiTokenFactory(name="Old")

    response = admin_logged_in_client.get(f"/b/tokens/{token.pk}/delete")

    assert response.status_code == 405
    assert ApiToken.objects.exists()


def test_token_revoke_requires_login(client):
    token = ApiTokenFactory(name="Old")

    response = client.post(f"/b/tokens/{token.pk}/delete")

    assert response.status_code == 302
    assert "login" in response.url
    assert ApiToken.objects.exists()
