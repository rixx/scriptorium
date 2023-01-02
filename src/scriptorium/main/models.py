import datetime as dt
import hashlib
import math
import random
import uuid

from django.db import models
from django.utils.functional import cached_property


class ToRead(models.Model):
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=300)
    shelf = models.CharField(max_length=300)
    pages = models.IntegerField(null=True, blank=True)
    source = models.CharField(default="calibre", max_length=300)


class Author(models.Model):
    name = models.CharField(max_length=300)
    name_slug = models.CharField(max_length=300)
    text = models.TextField(null=True, blank=True)


class Tag(models.Model):
    name = models.CharField(max_length=300)
    name_slug = models.CharField(max_length=300)
    text = models.TextField(null=True, blank=True)


class Book(models.Model):
    title = models.CharField(max_length=300)
    title_slug = models.CharField(max_length=300)
    authors = models.ManyToManyField(Author)

    cover = models.CharField(max_length=300, null=True, blank=True)
    cover_source = models.CharField(max_length=300, null=True, blank=True)
    spine_color = models.CharField(max_length=7, null=True, blank=True)

    goodreads_id = models.CharField(max_length=30, null=True, blank=True)
    isbn10 = models.CharField(max_length=30, null=True, blank=True)
    isbn13 = models.CharField(max_length=30, null=True, blank=True)

    dimensions = models.JSONField(null=True)
    source = models.CharField(max_length=300, null=True, blank=True)
    pages = models.IntegerField(null=True, blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    date_added = models.DateField()

    series = models.CharField(max_length=300, null=True, blank=True)
    series_position = models.CharField(max_length=5, null=True, blank=True)

    book_tags = models.ManyToManyField(Tag)
    plot = models.TextField(null=True, blank=True)


class BookRelation(models.Model):
    source = models.ForeignKey(
        to=Book, on_delete=models.CASCADE, related_name="related_books"
    )
    destination = models.ForeignKey(to=Book, on_delete=models.CASCADE, related_name="+")
    text = models.TextField()


class Quote(models.Model):
    source_book = models.ForeignKey(
        to=Book, on_delete=models.CASCADE, related_name="quotes", null=True
    )
    source_author = models.ForeignKey(
        to=Author, on_delete=models.CASCADE, related_name="quotes", null=True
    )
    text = models.TextField()
    order = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("source_author", "source_book", "order", "id")


class Review(models.Model):
    book = models.OneToOneField(Book, on_delete=models.PROTECT)

    text = models.TextField()
    tldr = models.TextField(null=True, blank=True)

    rating = models.IntegerField(null=True, blank=True)
    did_not_finish = models.BooleanField(default=False)

    latest_date = models.DateField()
    dates_read = models.CharField(max_length=300, null=True, blank=True)

    social = models.JSONField(null=True)

    @cached_property
    def spine(self):
        return Spine(self)

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
        return len(self.content.split())

    @cached_property
    def first_paragraph(self):
        print(self.content)
        return self.content.strip().split("\n\n")[0] if self.content else ""

    @cached_property
    def feed_uuid(self):
        m = hashlib.md5()
        m.update(
            f"{self.book_title}:reviews:{self.latest_date.isoformat()}:{self.book.goodreads_id or ''}".encode()
        )
        return str(uuid.UUID(m.hexdigest()))


class Spine:
    def __init__(self, review):
        self.review = review
        self.height = self.get_spine_height()
        self.width = self.get_spine_width()
        self.color = self.review.book_spine_color
        self.cover = self.review.book_cover_path
        self.starred = self.review.rating == 5
        # self.labels = []
        # for tag_name in self.review.book_tags:
        #     if tag_name not in TAG_CACHE:
        #         TAG_CACHE[tag_name] = Tag(tag_name)
        #     tag = TAG_CACHE[tag_name]
        #     color = tag.metadata.get("color")
        #     if color:
        #         self.labels.append(tag)

    def random_height(self):
        return random.randint(16, 25)

    def normalize_height(self, height):
        return max(min(int(height * 4), 110), 50)

    def get_spine_height(self):
        height = (
            self.review.book_dimensions.get("height")
            if self.review.book_dimensions
            else None
        )
        if not height:
            height = self.random_height()
        return self.normalize_height(height)

    def get_spine_width(self):
        width = (
            self.review.book_dimensions.get("thickness")
            if self.review.book_dimensions
            else None
        )
        if not width:
            pages = self.review.book_pages
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
