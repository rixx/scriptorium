import datetime as dt
import hashlib
import math
import random
import uuid
from io import BytesIO
from itertools import groupby
from pathlib import Path

import requests
from django.core.files.base import ContentFile
from django.db import models
from django.utils.functional import cached_property
from PIL import Image

from .utils import get_spine_color


def get_cover_path(instance, filename):
    return f"{instance.slug}/cover{Path(filename).suffix}"


def get_thumbnail_path(instance, filename):
    return f"{instance.book.slug}/{instance.size}{Path(filename).suffix}"


class ToRead(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300)
    shelf = models.CharField(max_length=300)
    pages = models.IntegerField(null=True, blank=True)
    source = models.CharField(default="calibre", max_length=300)

    def __str__(self):
        return f"{self.title} by {self.author}"

    class Meta:
        unique_together = (("title", "author"),)


class Author(models.Model):
    name = models.CharField(max_length=300)
    name_slug = models.CharField(max_length=300)
    text = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    def all_books(self):
        return Book.objects.filter(
            models.Q(primary_author=self) | models.Q(additional_authors=self)
        )


class Tag(models.Model):
    class TagCategory(models.TextChoices):
        GENRE = "genre", "genre"
        FORMAT = "format", "format"
        LANGUAGE = "language", "language"
        AWARDS = "awards", "awards"
        THEMES = "themes", "themes"

    category = models.CharField(
        max_length=300, choices=TagCategory.choices, default=TagCategory.GENRE
    )
    name_slug = models.CharField(max_length=300)
    text = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ("category", "name_slug")


class BookManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("review", "primary_author")
            .prefetch_related("additional_authors")
        ).filter(review__is_draft=False)

    def with_drafts(self):
        return super().get_queryset()

    def get_by_slug(self, slug):
        author, book = slug.strip("/").split("/")
        return self.get_queryset().get(
            primary_author__name_slug=author, title_slug=book
        )


class Book(models.Model):
    title = models.CharField(max_length=300)
    title_slug = models.CharField(max_length=300)
    additional_authors = models.ManyToManyField(Author, blank=True)
    primary_author = models.ForeignKey(
        Author, null=True, on_delete=models.PROTECT, related_name="books"
    )

    cover = models.ImageField(
        null=True, blank=True, upload_to=get_cover_path, max_length=800
    )
    cover_source = models.CharField(max_length=300, null=True, blank=True)
    spine_color = models.CharField(max_length=7, null=True, blank=True)

    goodreads_id = models.CharField(max_length=30, null=True, blank=True)
    openlibrary_id = models.CharField(max_length=30, null=True, blank=True)
    isbn10 = models.CharField(max_length=30, null=True, blank=True)
    isbn13 = models.CharField(max_length=30, null=True, blank=True)

    dimensions = models.JSONField(null=True, blank=True)
    source = models.CharField(max_length=300, null=True, blank=True)
    pages = models.IntegerField(null=True, blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    date_added = models.DateField(auto_now_add=True)

    series = models.CharField(max_length=300, null=True, blank=True)
    series_position = models.CharField(max_length=5, null=True, blank=True)

    tags = models.ManyToManyField(Tag)
    plot = models.TextField(null=True, blank=True)

    objects = BookManager()

    def __str__(self):
        return f"{self.title} by {self.author_string}"

    @cached_property
    def slug(self):
        return f"{self.primary_author.name_slug}/{self.title_slug}"

    @cached_property
    def spine(self):
        return Spine(self)

    @cached_property
    def authors(self):
        return [self.primary_author] + list(self.additional_authors.all())

    @cached_property
    def author_string(self):
        if len(self.authors) == 1:
            return self.authors[0].name
        first = ", ".join([a.name for a in self.authors[:-1]])
        return f"{first} & {self.authors[-1].name}"

    @cached_property
    def quotes_by_language(self):
        return {
            key: list(value)
            for key, value in groupby(self.quotes.all(), lambda q: q.language)
        }

    @cached_property
    def isbn(self):
        return self.isbn13 or self.isbn10

    @cached_property
    def cover_thumbnail(self):
        return Thumbnail.objects.filter(book=self, size="thumbnail").first()

    @cached_property
    def cover_square(self):
        return Thumbnail.objects.filter(book=self, size="square").first()

    def download_cover(self):
        if not self.cover_source:
            return
        try:
            response = requests.get(self.cover_source, timeout=5)
            response.raise_for_status()
        except Exception:
            return
        if self.cover:
            self.cover.delete()
        Thumbnail.objects.filter(book=self).delete()
        self.cover.save(f"{self.title_slug}.jpg", ContentFile(response.content))
        self.update_spine_color()

    def update_thumbnail(self):
        if not self.cover:
            return
        if self.cover_thumbnail:
            del self.cover_thumbnail
        if self.cover_square:
            del self.cover_square
        im = Image.open(self.cover.path)
        if im.width > 240 and im.height > 240:
            im.thumbnail((240, 240))
        buffer = BytesIO()
        im.save(fp=buffer, format="JPEG", quality=95)
        imgfile = ContentFile(buffer.getvalue())

        t = Thumbnail.objects.create(book=self, size="thumbnail")
        t.thumb.save("thumbnail.jpg", imgfile)

        im = Image.open(self.cover.path)
        im.thumbnail((240, 240))
        dimension = max(im.size)
        im = Image.new("RGBA", size=(dimension, dimension), color=(255, 255, 255, 0))

        if im.height > im.width:
            im.paste(im, box=((dimension - im.width) // 2, 0))
        else:
            im.paste(im, box=(0, (dimension - im.height) // 2))

        buffer = BytesIO()
        im.save(fp=buffer, format="PNG", quality=95)
        imgfile = ContentFile(buffer.getvalue())
        t = Thumbnail.objects.create(book=self, size="square")
        t.thumb.save("square.png", imgfile)

    def update_spine_color(self):
        if self.cover:
            self.spine_color = get_spine_color(self.cover)

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if not self.cover and self.cover_source:
            self.download_cover()
        return result


class BookRelation(models.Model):
    source = models.ForeignKey(
        to=Book, on_delete=models.CASCADE, related_name="related_books"
    )
    destination = models.ForeignKey(to=Book, on_delete=models.CASCADE, related_name="+")
    text = models.TextField()


class QuoteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("source_book", "source_author")


class Quote(models.Model):
    source_book = models.ForeignKey(
        to=Book, on_delete=models.CASCADE, related_name="quotes", null=True
    )
    source_author = models.ForeignKey(
        to=Author, on_delete=models.CASCADE, related_name="quotes", null=True
    )
    text = models.TextField()
    language = models.CharField(max_length=2, default="en")
    order = models.IntegerField(null=True, blank=True)

    objects = QuoteManager

    class Meta:
        ordering = ("source_author", "source_book", "order", "id")


class ReviewManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("book", "book__primary_author")
            .prefetch_related("book__additional_authors")
        ).filter(is_draft=False)

    def with_drafts(self):
        return super().get_queryset()


class Review(models.Model):
    book = models.OneToOneField(Book, on_delete=models.PROTECT, related_name="review")

    text = models.TextField()
    tldr = models.TextField(null=True, blank=True)

    rating = models.IntegerField(null=True, blank=True)
    did_not_finish = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)

    latest_date = models.DateField()
    dates_read = models.CharField(max_length=300, null=True, blank=True)

    social = models.JSONField(null=True)

    def __str__(self):
        return f"Review ({self.rating}/5) for {self.book}"

    @cached_property
    def dates_read_list(self):
        return [
            dt.datetime.strptime(date, "%Y-%m-%d").date()
            for date in self.dates_read.split(",")
        ]

    @cached_property
    def date_read_lookup(self):
        return {date.year: date for date in self.dates_read_list}

    @cached_property
    def word_count(self):
        return len(self.text.split())

    @cached_property
    def first_paragraph(self):
        return self.text.strip().split("\n\n")[0] if self.text else ""

    @cached_property
    def feed_uuid(self):
        m = hashlib.md5()
        m.update(
            f"{self.book.title}:reviews:{self.latest_date.isoformat()}:{self.book.goodreads_id or ''}".encode()
        )
        return str(uuid.UUID(m.hexdigest()))


class Spine:
    def __init__(self, book):
        self.book = book
        self.height = self.get_spine_height()
        self.width = self.get_spine_width()
        self.color = self.book.spine_color
        self.cover = self.book.cover
        self.starred = self.book.review.rating == 5

    def random_height(self):
        return random.randint(16, 25)

    def normalize_height(self, height):
        return max(min(int(height * 4), 110), 50)

    def get_spine_height(self):
        height = self.book.dimensions.get("height") if self.book.dimensions else None
        if not height:
            height = self.random_height()
        return self.normalize_height(height)

    def get_spine_width(self):
        width = self.book.dimensions.get("thickness") if self.book.dimensions else None
        if not width:
            pages = self.book.pages
            if not pages:
                width = random.randint(1, 4) / 2
            else:
                width = (
                    int(pages) * 0.0075
                )  # Factor taken from known thickness/page ratio
        return min(max(int(width * 4), 12), 32)  # Clamp between 12 and 32

    def get_margin(self, tilt):
        tilt = abs(tilt)
        long_side = self.height * math.cos(math.radians(90 - tilt))
        short_side = self.width * math.cos(math.radians(tilt))
        total_required_margin = long_side + short_side - self.width
        return total_required_margin / 2


class Page(models.Model):
    title = models.CharField(max_length=300)
    slug = models.CharField(max_length=300, unique=True)
    text = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.title


class Thumbnail(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="thumbnails")
    size = models.CharField(max_length=255)
    thumb = models.FileField(upload_to=get_thumbnail_path)
