import datetime as dt

import factory
from django.contrib.auth import get_user_model

from scriptorium.main.models import (
    Author,
    Book,
    Page,
    Poem,
    PoemStatus,
    Quote,
    Review,
    Tag,
    ToRead,
    ToReview,
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


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f"Book Title {n}")
    title_slug = factory.Sequence(lambda n: f"book-title-{n}")
    primary_author = factory.SubFactory(AuthorFactory)
    pages = 200
    publication_year = 2020


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review

    book = factory.SubFactory(BookFactory)
    text = "A thoughtful review of the book."
    tldr = "Short."
    rating = 4
    latest_date = factory.LazyFunction(lambda: dt.date(2024, 6, 15))
    is_draft = False


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


class ToReadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ToRead

    title = factory.Sequence(lambda n: f"To read {n}")
    author = factory.Sequence(lambda n: f"To read author {n}")
    shelf = "fiction"
    pages = 300


class ToReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ToReview

    title = factory.Sequence(lambda n: f"To review {n}")
    author = factory.Sequence(lambda n: f"To review author {n}")
    date = factory.LazyFunction(lambda: dt.date(2024, 6, 15))


def make_reviewed_book(**book_kwargs):
    """Create a Book with a published (non-draft) Review attached."""
    review_kwargs = {
        key: book_kwargs.pop(key)
        for key in ("rating", "text", "tldr", "latest_date", "dates_read", "is_draft")
        if key in book_kwargs
    }
    book = BookFactory(**book_kwargs)
    ReviewFactory(book=book, **review_kwargs)
    return book
