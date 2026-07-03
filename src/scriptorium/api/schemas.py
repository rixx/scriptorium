import datetime as dt

from ninja import Field, Schema

from scriptorium.main.models import BookStatus


class MessageOut(Schema):
    detail: str


class ReadOut(Schema):
    date: dt.date = Field(alias="finished_on")
    format: str | None = None
    source: str | None = None
    notes: str | None = None


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
    text: str | None = None
    reads: list[ReadOut]
    quotes_count: int
    isbn: str | None
    openlibrary_id: str | None = None

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
