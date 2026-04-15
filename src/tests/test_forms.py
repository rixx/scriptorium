import io

import pytest
from PIL import Image

from scriptorium.main.forms import (
    BookEditForm,
    BookSelectForm,
    BookWizardForm,
    CatalogueForm,
    EditionSelectForm,
    QuoteForm,
)
from tests.factories import AuthorFactory, BookFactory, TagFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


# --- CatalogueForm ----------------------------------------------------------


def test_catalogue_form_get_queryset_returns_none_for_invalid_form():
    form = CatalogueForm(data={"order_by": "not-a-real-choice"})

    assert form.is_valid() is False
    assert "order_by" in form.errors
    assert list(form.get_queryset()) == []


def test_catalogue_form_filters_by_primary_author():
    target_author = AuthorFactory()
    other_author = AuthorFactory()
    kept = make_reviewed_book(primary_author=target_author)
    make_reviewed_book(primary_author=other_author)

    form = CatalogueForm(data={"author": str(target_author.pk)})

    assert form.is_valid()
    assert list(form.get_queryset()) == [kept]


def test_catalogue_form_filters_by_additional_author():
    primary = AuthorFactory()
    additional = AuthorFactory()
    matching = make_reviewed_book(primary_author=primary)
    matching.additional_authors.add(additional)
    make_reviewed_book(primary_author=primary)

    form = CatalogueForm(data={"author": str(additional.pk)})

    assert form.is_valid()
    assert list(form.get_queryset()) == [matching]


def test_catalogue_form_filters_by_series():
    hainish = make_reviewed_book(series="Hainish Cycle")
    make_reviewed_book(series="Earthsea")

    form = CatalogueForm(data={"series": "Hainish Cycle"})

    assert form.is_valid()
    assert list(form.get_queryset()) == [hainish]


def test_catalogue_form_fulltext_search_matches_review_text():
    match = make_reviewed_book(
        title="Unrelated Title", text="Contains the magic keyword somewhere."
    )
    make_reviewed_book(title="Other", text="Nothing interesting here.")

    form = CatalogueForm(data={"search_input": "magic keyword", "fulltext": "on"})

    assert form.is_valid()
    assert list(form.get_queryset()) == [match]


def test_catalogue_form_fulltext_search_matches_plot():
    match = make_reviewed_book(
        title="Cover Title", plot="A sprawling plot about robots."
    )
    make_reviewed_book(title="Other", plot="Unrelated summary.")

    form = CatalogueForm(data={"search_input": "robots", "fulltext": "on"})

    assert form.is_valid()
    assert list(form.get_queryset()) == [match]


def test_catalogue_form_non_fulltext_search_ignores_review_text():
    """Without the fulltext flag the review text should not be searched."""
    reviewed = make_reviewed_book(
        title="Plain Book", text="Contains the magic keyword somewhere."
    )

    form = CatalogueForm(data={"search_input": "magic keyword"})

    assert form.is_valid()
    # The book does not match through title/author/etc.
    assert list(form.get_queryset()) == []
    # Sanity check that the review really did contain the keyword.
    assert "magic keyword" in reviewed.review.text


def test_catalogue_form_order_by_rating_is_descending():
    low = make_reviewed_book(title="Low", rating=2)
    high = make_reviewed_book(title="High", rating=5)

    form = CatalogueForm(data={"order_by": "review__rating"})

    assert form.is_valid()
    assert list(form.get_queryset()) == [high, low]


def test_catalogue_form_order_by_title_is_ascending():
    alpha = make_reviewed_book(title="Alpha")
    zeta = make_reviewed_book(title="Zeta")

    form = CatalogueForm(data={"order_by": "title"})

    assert form.is_valid()
    assert list(form.get_queryset()) == [alpha, zeta]


# --- BookSelectForm / EditionSelectForm ------------------------------------


def test_book_select_form_appends_manual_option_to_works():
    works = [("OL1W", "Work One"), ("OL2W", "Work Two")]

    form = BookSelectForm(works=works)

    assert form.fields["search_selection"].choices == [
        ("OL1W", "Work One"),
        ("OL2W", "Work Two"),
        ("manual", "Manual entry"),
    ]


def test_book_select_form_validates_manual_choice():
    form = BookSelectForm(data={"search_selection": "manual"}, works=[])

    assert form.is_valid()
    assert form.cleaned_data["search_selection"] == "manual"


def test_edition_select_form_uses_provided_editions():
    editions = [("OL1M", "Edition One"), ("OL2M", "Edition Two")]

    form = EditionSelectForm(editions=editions)

    assert form.fields["edition_selection"].choices == editions


def test_edition_select_form_defaults_to_empty_when_editions_missing():
    form = EditionSelectForm()

    assert form.fields["edition_selection"].choices == []


# --- BookWizardForm --------------------------------------------------------


OPENLIBRARY_FIXTURE = {
    "title": "The Left Hand of Darkness",
    "identifiers": {
        "openlibrary": "OL12345W",
        "isbn_13": ["9780441007318"],
        "goodreads": ["18423"],
    },
    "number_of_pages": 304,
    "cover": {"large": "https://covers.example.com/large.jpg"},
    "publish_date": "1969",
    "authors": [{"name": "Ursula K. Le Guin"}, {"name": "Co Author"}],
}


def test_book_wizard_form_prefills_from_openlibrary():
    form = BookWizardForm(openlibrary=OPENLIBRARY_FIXTURE)

    assert form.initial["title"] == "The Left Hand of Darkness"
    assert form.initial["openlibrary_id"] == "OL12345W"
    assert form.initial["isbn13"] == "9780441007318"
    assert form.initial["goodreads_id"] == "18423"
    assert form.initial["pages"] == 304
    assert form.initial["cover_source"] == "https://covers.example.com/large.jpg"
    assert form.initial["publication_year"] == "1969"
    assert form.initial["author_name"] == "Ursula K. Le Guin & Co Author"
    assert form.initial["title_slug"] == "the-left-hand-of-darkness"


def test_book_wizard_form_falls_back_to_pagination_and_missing_cover():
    data = {
        "title": "A Book",
        "identifiers": {"openlibrary": "OL1W"},
        "pagination": "xii+250",
        "publish_date": "2001",
        "authors": [{"name": "Someone"}],
    }

    form = BookWizardForm(openlibrary=data)

    assert form.initial["pages"] == "xii+250"
    assert "cover_source" not in form.initial
    assert form.initial["isbn13"] == ""
    assert form.initial["goodreads_id"] == ""


def test_book_wizard_form_preserves_initial_title_over_openlibrary():
    form = BookWizardForm(
        openlibrary=OPENLIBRARY_FIXTURE, initial={"title": "My Override"}
    )

    assert form.initial["title"] == "My Override"
    assert form.initial["title_slug"] == "my-override"


def test_book_wizard_form_without_openlibrary_leaves_initial_untouched():
    form = BookWizardForm(initial={"title": "Bare Title"})

    assert form.initial["title"] == "Bare Title"
    assert form.initial["title_slug"] == "bare-title"
    assert "openlibrary_id" not in form.initial


def test_book_wizard_form_clean_new_tags_splits_and_strips():
    form = BookWizardForm()
    form.cleaned_data = {"new_tags": "  fantasy ,, science fiction , "}

    assert form.clean_new_tags() == ["fantasy", "science fiction"]


def test_book_wizard_form_clean_new_tags_returns_empty_when_blank():
    form = BookWizardForm()
    form.cleaned_data = {"new_tags": ""}

    assert form.clean_new_tags() == []


def test_book_wizard_form_clean_generates_missing_title_slug():
    form = BookWizardForm()
    form.cleaned_data = {"title": "An Untitled Work", "title_slug": ""}

    form.clean()

    assert form.cleaned_data["title_slug"] == "an-untitled-work"


def test_book_wizard_form_clean_preserves_explicit_title_slug():
    form = BookWizardForm()
    form.cleaned_data = {"title": "An Untitled Work", "title_slug": "custom-slug"}

    form.clean()

    assert form.cleaned_data["title_slug"] == "custom-slug"


# --- BookEditForm ----------------------------------------------------------


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _book_edit_post(book, tag, **overrides):
    """Build a minimal POST payload mirroring BookEditForm's field set."""
    payload = {
        "title": book.title,
        "title_slug": book.title_slug,
        "primary_author": str(book.primary_author_id),
        "additional_authors": [],
        "cover_source": book.cover_source or "",
        "goodreads_id": book.goodreads_id or "",
        "isbn10": book.isbn10 or "",
        "isbn13": book.isbn13 or "",
        "dimensions": "",
        "source": book.source or "",
        "pages": str(book.pages) if book.pages is not None else "",
        "publication_year": (
            str(book.publication_year) if book.publication_year is not None else ""
        ),
        "series": book.series or "",
        "series_position": book.series_position or "",
        "plot": book.plot or "",
        "tags": [str(tag.pk)],
        "new_tags": "",
    }
    payload.update(overrides)
    return payload


def test_book_edit_form_save_downloads_cover_when_source_changed(
    settings, tmp_path, monkeypatch
):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory(cover_source=None)
    tag = TagFactory()
    downloaded = _png_bytes()

    class _FakeResponse:
        content = downloaded
        status_code = 200

        def raise_for_status(self):
            pass

    calls = []

    def fake_get(url, timeout=5):  # noqa: ARG001
        calls.append(url)
        return _FakeResponse()

    monkeypatch.setattr("scriptorium.main.models.requests.get", fake_get)

    form = BookEditForm(
        data=_book_edit_post(book, tag, cover_source="https://example.com/new.jpg"),
        instance=book,
    )

    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert calls == ["https://example.com/new.jpg"]
    assert saved.cover.name
    with saved.cover.open("rb") as fp:
        assert fp.read() == downloaded
    # download_cover clears cover_source after a successful download.
    assert saved.cover_source is None


def test_book_edit_form_save_skips_download_when_cover_source_unchanged(
    settings, tmp_path, monkeypatch
):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory(cover_source=None, title="Original")
    tag = TagFactory()

    def boom(url, timeout=5):  # noqa: ARG001
        raise AssertionError("download_cover should not run for unchanged cover_source")

    monkeypatch.setattr("scriptorium.main.models.requests.get", boom)

    form = BookEditForm(data=_book_edit_post(book, tag, title="Renamed"), instance=book)

    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert saved.title == "Renamed"
    assert not saved.cover


def test_book_edit_form_clean_new_tags_splits_input():
    book = BookFactory()
    tag = TagFactory()

    form = BookEditForm(
        data=_book_edit_post(book, tag, new_tags=" a, b ,, c "), instance=book
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["new_tags"] == ["a", "b", "c"]


# --- QuoteForm -------------------------------------------------------------


def test_quote_form_sets_initial_from_source_book_and_author():
    book = BookFactory()
    author = AuthorFactory()

    form = QuoteForm(source_book=book, source_author=author)

    assert form.fields["source_book"].initial == book
    assert form.fields["source_author"].initial == author


def test_quote_form_orders_source_choices_alphabetically():
    zeta_author = AuthorFactory(name="Zeta")
    alpha_author = AuthorFactory(name="Alpha")
    # Reuse the existing authors so the factory doesn't quietly create extras,
    # and attach reviews so the default BookManager doesn't hide them.
    zeta_book = make_reviewed_book(title="Zeta Book", primary_author=zeta_author)
    alpha_book = make_reviewed_book(title="Alpha Book", primary_author=alpha_author)

    form = QuoteForm()

    assert list(form.fields["source_author"].queryset) == [alpha_author, zeta_author]
    assert list(form.fields["source_book"].queryset) == [alpha_book, zeta_book]
