import datetime as dt
import hashlib
import math
import random
import textwrap
import uuid
from io import BytesIO
from itertools import groupby
from pathlib import Path

import requests
from django.core.files.base import ContentFile
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
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


class ToReview(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300)
    series = models.CharField(max_length=300, null=True, blank=True)
    series_position = models.CharField(max_length=10, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(to="Book", on_delete=models.CASCADE, null=True, blank=True)
    quotes_file = models.FileField(null=True, blank=True)

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

    def tag_author(self, tag):
        for book in self.books.all():
            book.tags.add(tag)


class Tag(models.Model):
    class TagCategory(models.TextChoices):
        GENRE = "genre", "genre"
        FORMAT = "format", "format"
        LANGUAGE = "language", "language"
        AWARDS = "awards", "awards"
        THEMES = "themes", "themes"
        AUTHOR = "author", "author"

    category = models.CharField(
        max_length=300, choices=TagCategory.choices, default=TagCategory.GENRE
    )
    name_slug = models.CharField(max_length=300)
    text = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.category}:{self.name_slug}"

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
    def tags_by_category(self):
        return {
            key: list(value)
            for key, value in groupby(self.tags.all(), lambda t: t.category)
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
        self.cover_source = None
        self.spine_color = None
        self.save()

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
        im.convert("RGB").save(fp=buffer, format="JPEG", quality=95)
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

    @cached_property
    def spine_color_darkened(self):
        # Calculate brightness, then darken if necessary
        if not self.spine_color:
            return None
        # Spine color is given in hex, e.g. #f0f0f0
        r, g, b = tuple(int(self.spine_color[i : i + 2], 16) for i in (1, 3, 5))
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        target_brightness = 100
        if brightness > target_brightness:
            diff = int(brightness) - target_brightness
            r = max(0, r - diff)
            g = max(0, g - diff)
            b = max(0, b - diff)
        return f"#{r:02x}{g:02x}{b:02x}"


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
        to=Book,
        on_delete=models.CASCADE,
        related_name="quotes",
        null=True,
        blank=True,
    )
    source_author = models.ForeignKey(
        to=Author,
        on_delete=models.CASCADE,
        related_name="quotes",
        null=True,
        blank=True,
    )
    text = models.TextField()
    language = models.CharField(max_length=2, default="en")
    order = models.IntegerField(null=True, blank=True)

    objects = QuoteManager

    class Meta:
        ordering = ("source_author", "source_book", "order", "id")

    @property
    def short_string(self):
        short_quote = textwrap.shorten(self.text, width=70, placeholder="…")
        if self.source_book:
            return f"“{short_quote}” — {self.source_book.title}"
        elif self.source_author:
            return f"“{short_quote}” — {self.source_author.name}"
        return f"“{short_quote}”"


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
    feed_date = models.DateField(null=True)
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
        feed_date = self.feed_date or self.latest_date
        m.update(
            f"{self.book.title}:reviews:{feed_date.isoformat()}:{self.book.goodreads_id or ''}".encode()
        )
        return str(uuid.UUID(m.hexdigest()))

    def save(self, *args, **kwargs):
        pre_save = Review.objects.get(pk=self.pk) if self.pk else None
        today = now().date()
        if pre_save:
            # if the review is updated, the feed date should only be updated if I read the book again
            if pre_save.latest_date < self.latest_date:
                self.feed_date = today
        else:
            # new reviews always get the creation date as feed date
            self.feed_date = today
        if not self.dates_read:
            self.dates_read = self.latest_date.isoformat()
        return super().save(*args, **kwargs)


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
    thumb = models.FileField(upload_to=get_thumbnail_path, max_length=800)

    def delete(self, **kwargs):
        self.thumb.delete()
        super().delete(**kwargs)


class PoemStatus(models.TextChoices):
    ARCHIVED = "A", "archived"
    WAITING = "W", "waiting"
    LEARNING = "L", "learning"
    MEMORIZED = "M", "memorized"


class Poem(models.Model):
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name="poems", null=True, blank=True
    )
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="poems",
        null=True,
        blank=True,
        help_text="Use if the book is not in the database",
    )
    author_name = models.CharField(
        max_length=300,
        null=True,
        blank=True,
        help_text="Use if the author is not in the database",
    )
    url_slug = models.CharField(
        max_length=300,
        null=True,
        blank=True,
        help_text="Use if neither book nor author are in the database. Slug field!",
    )

    title = models.CharField(max_length=300)
    slug = models.CharField(max_length=300)
    text = models.TextField()
    context = models.TextField(null=True, blank=True)
    language = models.CharField(max_length=2, default="en")
    status = models.CharField(
        max_length=1,
        choices=PoemStatus.choices,
        default=PoemStatus.ARCHIVED,
    )
    learning_data = models.JSONField(null=True, blank=True)

    date_added = models.DateField(auto_now_add=True)
    last_studied = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("book", "slug")

    def get_absolute_url(self, private=False):
        if self.book:
            result = f"/{self.book.slug}/poems/{self.slug}/"
        elif self.author:
            result = f"/{self.author.name_slug}/poems/{self.slug}/"
        else:
            result = f"/poems/{self.url_slug}/{self.slug}/"
        if private:
            result = f"/b{result}"
        return result

    @cached_property
    def line_count(self):
        return len([line for line in self.text.split("\n") if line.strip()])
