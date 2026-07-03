import datetime as dt

import factory
from django.contrib.auth import get_user_model

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
    Series,
    Tag,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    is_staff = True
    is_superuser = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw = extracted or "password"
        self.set_password(raw)
        if create:
            self.save()


class ApiTokenFactory(factory.django.DjangoModelFactory):
    """The token value is intentionally left unset: the model generates it
    server-side on first save."""

    class Meta:
        model = ApiToken

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Token {n}")


class AuthorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Author

    name = factory.Sequence(lambda n: f"Author {n}")
    name_slug = factory.Sequence(lambda n: f"author-{n}")


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    category = Tag.TagCategory.GENRE
    name = factory.Sequence(lambda n: f"Tag {n}")
    name_slug = factory.Sequence(lambda n: f"tag-{n}")


class SeriesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Series

    name = factory.Sequence(lambda n: f"Series {n}")
    name_slug = factory.Sequence(lambda n: f"series-{n}")


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f"Book Title {n}")
    title_slug = factory.Sequence(lambda n: f"book-title-{n}")
    primary_author = factory.SubFactory(AuthorFactory)
    pages = 200
    publication_year = 2020

    class Params:
        # A published book with review data; combine with make_reviewed_book
        # (or ReadFactory) so it also gets the matching Read rows.
        reviewed = factory.Trait(
            status=BookStatus.REVIEWED,
            text="A thoughtful review of the book.",
            tldr="Short.",
            rating=4,
        )


class ReadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Read

    book = factory.SubFactory(BookFactory)
    finished_on = factory.LazyFunction(lambda: dt.date(2024, 6, 15))


class QuoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Quote

    text = factory.Sequence(lambda n: f"Quote text number {n}")
    language = "en"


class PoemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Poem

    title = factory.Sequence(lambda n: f"Poem {n}")
    slug = factory.Sequence(lambda n: f"poem-{n}")
    text = "Line one.\nLine two.\nLine three."
    language = "en"
    status = PoemStatus.ARCHIVED


class PageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Page

    title = factory.Sequence(lambda n: f"Page {n}")
    slug = factory.Sequence(lambda n: f"page-{n}")
    text = "Some page content."


def make_reviewed_book(*, latest_date=None, reads=None, **book_kwargs):
    """Create a published (status ``reviewed``) Book with review fields set
    and one Read per date in ``reads`` (defaulting to a single read on
    ``latest_date``); pass ``reads=[]`` to skip the reads."""
    latest_date = latest_date or dt.date(2024, 6, 15)
    book = BookFactory(reviewed=True, **book_kwargs)
    for date in reads if reads is not None else [latest_date]:
        ReadFactory(book=book, finished_on=date)
    return book
