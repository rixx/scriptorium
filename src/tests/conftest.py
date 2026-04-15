import datetime as dt

import pytest

from tests.factories import (
    AuthorFactory,
    BookFactory,
    PageFactory,
    PoemFactory,
    QuoteFactory,
    ReviewFactory,
    TagFactory,
    ToReadFactory,
    ToReviewFactory,
    UserFactory,
    make_reviewed_book,
)


@pytest.fixture(autouse=True)
def _simple_static_storage(settings):
    """Scriptorium uses whitenoise's CompressedManifestStaticFilesStorage in
    production, which requires a pre-built manifest. Tests run against the
    source tree without that manifest, so fall back to the plain storage
    backend for rendering purposes."""
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def author():
    return AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")


@pytest.fixture
def book(author):
    return BookFactory(
        title="The Dispossessed",
        title_slug="the-dispossessed",
        primary_author=author,
        pages=341,
        publication_year=1974,
        series="Hainish Cycle",
        series_position="5",
    )


@pytest.fixture
def review(book):
    return ReviewFactory(
        book=book,
        rating=5,
        text="A brilliant exploration of competing utopias.",
        latest_date=dt.date(2024, 3, 14),
        dates_read="2024-03-14",
    )


@pytest.fixture
def reviewed_book(review):
    """A Book with a published Review. Accessing this fixture ensures the
    Book passes the default (non-draft) BookManager filter."""
    return review.book


@pytest.fixture
def tag():
    return TagFactory(category="genre", name="Science Fiction", name_slug="sci-fi")


@pytest.fixture
def quote(reviewed_book):
    return QuoteFactory(source_book=reviewed_book, text="To be whole is to be part.")


@pytest.fixture
def poem(author):
    return PoemFactory(
        author=author,
        title="A Song",
        slug="a-song",
        text="First line of the song.\nSecond line.",
    )


@pytest.fixture
def page():
    return PageFactory(title="About", slug="about", text="About this site.")


@pytest.fixture
def to_read():
    return ToReadFactory()


@pytest.fixture
def to_review():
    return ToReviewFactory()


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def admin_logged_in_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def populated_library(author):
    """A small library covering the main shapes used by list views: two
    reviewed books by the same author in a series, one extra book by another
    author, and a tag that groups them."""
    tag = TagFactory(category="genre", name="Fantasy", name_slug="fantasy")

    book_one = make_reviewed_book(
        title="Book One",
        title_slug="book-one",
        primary_author=author,
        series="A Series",
        series_position="1",
        rating=4,
        latest_date=dt.date(2024, 1, 10),
        dates_read="2024-01-10",
    )
    book_two = make_reviewed_book(
        title="Book Two",
        title_slug="book-two",
        primary_author=author,
        series="A Series",
        series_position="2",
        rating=5,
        latest_date=dt.date(2024, 2, 20),
        dates_read="2024-02-20",
    )
    other_author = AuthorFactory(name="Other Writer", name_slug="other-writer")
    book_three = make_reviewed_book(
        title="Solo Volume",
        title_slug="solo-volume",
        primary_author=other_author,
        rating=3,
        latest_date=dt.date(2023, 12, 1),
        dates_read="2023-12-01",
    )

    for book in (book_one, book_two, book_three):
        book.tags.add(tag)

    return {
        "tag": tag,
        "author": author,
        "other_author": other_author,
        "book_one": book_one,
        "book_two": book_two,
        "book_three": book_three,
    }
