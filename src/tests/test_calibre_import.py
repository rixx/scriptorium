import json

import pytest
from django.core.management import call_command

from scriptorium.main.models import Book, BookStatus
from tests.factories import AuthorFactory, BookFactory

pytestmark = pytest.mark.django_db


def _write_calibre_json(tmp_path, books):
    path = tmp_path / "calibre_books.json"
    path.write_text(json.dumps(books))
    return str(path)


def test_calibre_import_keeps_queued_book_with_author_spelling_variant(tmp_path):
    """The sync key is slug-based, so a calibre author spelling that only
    differs in casing/punctuation from the stored author must not cause a
    delete-and-recreate churn of the same book on every run."""
    author = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")
    existing = BookFactory(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=author,
        status=BookStatus.TO_READ,
        shelf="paper",
    )
    json_file = _write_calibre_json(
        tmp_path,
        [
            {
                "title": "The Dispossessed",
                "authors": "ursula k. le guin",
                "*shelf": "paper",
                "*pages": 400,
            }
        ],
    )

    call_command("calibre_import", json_file)

    book = Book.all_objects.get()
    assert book.pk == existing.pk
    assert book.title == "The Dispossessed"
    assert book.primary_author == author
    assert book.shelf == "paper"


def test_calibre_import_creates_unknown_and_deletes_stale_queue_entries(tmp_path):
    stale = BookFactory(
        title="Gone From Calibre",
        title_slug="gone-from-calibre",
        status=BookStatus.TO_READ,
    )
    json_file = _write_calibre_json(
        tmp_path,
        [
            {
                "title": "A Wizard of Earthsea",
                "authors": "Ursula K. Le Guin",
                "*shelf": "ebook",
                "*pages": 200,
            }
        ],
    )

    call_command("calibre_import", json_file)

    created = Book.all_objects.get()
    assert created.pk != stale.pk
    assert created.title == "A Wizard of Earthsea"
    assert created.title_slug == "a-wizard-of-earthsea"
    assert created.primary_author.name == "Ursula K. Le Guin"
    assert created.status == BookStatus.TO_READ
    assert created.shelf == "ebook"
    assert created.pages == 200
    assert created.source == "calibre"
