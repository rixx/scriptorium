import datetime as dt
from typing import Literal

from ninja import Field, Schema

from scriptorium.main.models import BookStatus


class MessageOut(Schema):
    detail: str


class ReadOut(Schema):
    date: dt.date = Field(alias="finished_on")
    format: str | None = None
    source: str | None = None
    notes: str | None = None


class ReadDetailOut(ReadOut):
    id: int
    book: str
    started_on: dt.date | None = None
    did_not_finish: bool

    @staticmethod
    def resolve_book(obj):
        return obj.book.slug


class BookListOut(Schema):
    id: int
    title: str
    slug: str
    authors: list[str]
    series: str | None
    series_position: str | None = None
    rating: int | None = None
    tldr: str | None = None
    status: str
    latest_read: dt.date | None
    pages: int | None = None
    tags: list[str]

    @staticmethod
    def resolve_authors(obj):
        return [author.name for author in obj.authors]

    @staticmethod
    def resolve_series(obj):
        return obj.series.name if obj.series else None

    @staticmethod
    def resolve_latest_read(obj):
        return obj.latest_date

    @staticmethod
    def resolve_tags(obj):
        return [str(tag) for tag in obj.tags.all()]


class BookDetailOut(BookListOut):
    url: str
    text: str | None = None
    reads: list[ReadOut]
    quotes_count: int
    isbn: str | None
    openlibrary_id: str | None = None

    @staticmethod
    def resolve_url(obj, context):
        return context["request"].build_absolute_uri(f"/{obj.slug}/")

    @staticmethod
    def resolve_quotes_count(obj):
        return obj.quotes.count()


class QueueReadOut(Schema):
    date: dt.date = Field(alias="finished_on")
    notes: str | None = None


class QueueItemOut(Schema):
    id: int
    slug: str
    title: str
    author: str = Field(alias="author_string")
    series: str | None
    series_position: str | None = None
    status: str
    date: dt.date | None = Field(
        None, description="Latest read date; the queue is ordered by it."
    )
    why: str
    reads: list[QueueReadOut]

    @staticmethod
    def resolve_series(obj):
        return obj.series.name if obj.series else None

    @staticmethod
    def resolve_why(obj):
        return "unreviewed" if obj.status == BookStatus.TO_REVIEW else "reread"


class QueueAddIn(Schema):
    title: str = Field(min_length=1)
    author_name: str = Field(min_length=1)
    series: str | None = None
    series_position: str | None = None
    date_read: dt.date | None = None
    notes: str | None = None
    shelf: str | None = None


class QuoteOut(Schema):
    id: int
    text: str
    language: str
    order: int | None = None
    book: str | None = None
    author: str | None = None

    @staticmethod
    def resolve_book(obj):
        return obj.source_book.slug if obj.source_book else None

    @staticmethod
    def resolve_author(obj):
        return obj.source_author.name_slug if obj.source_author else None


class QuoteIn(Schema):
    text: str
    language: str = "en"
    order: int | None = None
    source_author: str | None = Field(None, description="Author slug")


class QuotePatchIn(Schema):
    text: str = None
    language: str = None
    order: int | None = None
    source_author: str | None = Field(None, description="Author slug")


class BookMetadataIn(Schema):
    """The metadata patch accepted by the composite review endpoint."""

    pages: int | None = None
    publication_year: int | None = None
    series: str | None = None
    series_position: str | None = None
    isbn13: str | None = None
    openlibrary_id: str | None = None
    cover_source: str | None = None
    tags: list[str] | None = Field(
        None, description="Tags as 'category:slug' strings; replaces the tag set."
    )


class BookPatchIn(BookMetadataIn):
    """Partial book update: metadata plus the review fields. Slugs (title,
    author) and reads are managed elsewhere and not editable here."""

    isbn10: str | None = None
    goodreads_id: str | None = None
    plot: str | None = None
    text: str | None = None
    tldr: str | None = None
    rating: int | None = Field(None, ge=0, le=5)


class ReviewSubmitIn(Schema):
    text: str = Field(min_length=1)
    tldr: str | None = None
    rating: int | None = Field(None, ge=0, le=5)
    dates_read: list[dt.date] = Field(min_length=1)
    did_not_finish: bool = False
    overwrite: bool = False
    metadata: BookMetadataIn | None = None
    quotes: list[QuoteIn] = []


class ReadIn(Schema):
    date: dt.date
    started_on: dt.date | None = None
    format: Literal["paper", "ebook", "audio"] | None = None
    source: str | None = None
    notes: str | None = None
    did_not_finish: bool = False


class ReadPatchIn(Schema):
    date: dt.date = None
    started_on: dt.date | None = None
    format: Literal["paper", "ebook", "audio"] | None = None
    source: str | None = None
    notes: str | None = None
    did_not_finish: bool = None


class AuthorOut(Schema):
    id: int
    name: str
    slug: str = Field(alias="name_slug")


class AuthorDetailOut(AuthorOut):
    text: str | None = None
    books: list[BookListOut]

    @staticmethod
    def resolve_books(obj):
        return obj.all_books().order_by("title_slug")


class AuthorPatchIn(Schema):
    name: str = Field(None, min_length=1)
    text: str | None = None


class TagOut(Schema):
    category: str
    name: str
    slug: str = Field(alias="name_slug")
    text: str | None = None
    book_count: int


class SeriesOut(Schema):
    id: int
    name: str
    slug: str = Field(alias="name_slug")
    book_count: int


class OpenLibraryWorkOut(Schema):
    id: str
    title: str
    authors: list[str]
    year: int | None = None
    cover_url: str | None = None


class OpenLibraryEditionOut(Schema):
    id: str
    title: str
    publish_date: str
    language: str
    pages: int
    cover_url: str


class OpenLibraryBookOut(Schema):
    """Edition metadata keyed like our own book fields, ready to feed into
    the queue-add and book PATCH/review endpoints."""

    title: str | None
    author_name: str
    openlibrary_id: str
    isbn13: str | None = None
    isbn10: str | None = None
    goodreads_id: str | None = None
    pages: int | None = None
    publication_year: int | None = None
    cover_source: str | None = None
