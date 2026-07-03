import datetime as dt

import factory
from django.contrib.auth import get_user_model

from scriptorium.main.models import (
    Author,
    Book,
    BookStatus,
    Page,
    Poem,
    PoemStatus,
    Quote,
    Read,
    Review,
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


class ReadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Read

    book = factory.SubFactory(BookFactory)
    finished_on = factory.LazyFunction(lambda: dt.date(2024, 6, 15))


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review
        skip_postgeneration_save = True

    book = factory.SubFactory(BookFactory)
    text = "A thoughtful review of the book."
    tldr = "Short."
    rating = 4
    latest_date = factory.LazyFunction(lambda: dt.date(2024, 6, 15))

    @factory.post_generation
    def reads(self, create, extracted, **kwargs):
        """Every review comes with one Read per date in ``reads`` (defaulting
        to a single read on ``latest_date``); pass ``reads=[]`` to skip."""
        if not create:
            return
        dates = extracted if extracted is not None else [self.latest_date]
        for date in dates:
            ReadFactory(book=self.book, finished_on=date)

    @factory.post_generation
    def publish(self, create, extracted, **kwargs):
        """Creating a review publishes the book, mirroring the production
        flows; pass ``publish=False`` to keep the book's current status."""
        if not create or extracted is False:
            return
        if self.book.status != BookStatus.REVIEWED:
            self.book.status = BookStatus.REVIEWED
            self.book.save(update_fields=["status"])


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


def make_reviewed_book(**book_kwargs):
    """Create a published (status ``reviewed``) Book with a Review attached."""
    review_kwargs = {
        key: book_kwargs.pop(key)
        for key in ("rating", "text", "tldr", "latest_date", "reads")
        if key in book_kwargs
    }
    book = BookFactory(**book_kwargs, status=BookStatus.REVIEWED)
    ReviewFactory(book=book, **review_kwargs)
    return book
