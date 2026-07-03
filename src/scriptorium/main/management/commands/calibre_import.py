import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from scriptorium.main.models import Author, Book, BookStatus
from scriptorium.main.utils import slugify


class Command(BaseCommand):
    help = "Sync the to-read queue from a calibre_export JSON file"

    def add_arguments(self, parser):
        parser.add_argument("json_file")

    def handle(self, *args, json_file, **options):
        with Path(json_file).open() as f:
            result = json.load(f)
        # Authors (and titles) are deduplicated by slug on import, so the
        # stored spelling can differ from calibre's -- key both sides on
        # slugs to keep the comparison stable across spelling variants.
        calibre_books = {
            (slugify(b["title"]), slugify(b["authors"])): b for b in result
        }
        queue = Book.all_objects.filter(status=BookStatus.TO_READ).select_related(
            "primary_author"
        )
        scriptorium_books = {
            (
                b.title_slug or slugify(b.title),
                b.primary_author.name_slug or slugify(b.primary_author.name),
            ): b.id
            for b in queue
        }
        unknown = set(calibre_books) - set(scriptorium_books)
        too_many = set(scriptorium_books) - set(calibre_books)

        with transaction.atomic():
            Book.all_objects.filter(
                id__in=(v for k, v in scriptorium_books.items() if k in too_many)
            ).delete()
            for key in unknown:
                calibre_book = calibre_books[key]
                author, _ = Author.objects.get_or_create_by_name(
                    calibre_book["authors"]
                )
                title_slug = slugify(calibre_book["title"])
                if Book.all_objects.filter(
                    primary_author=author, title_slug=title_slug
                ).exists():
                    continue
                Book.all_objects.create(
                    title=calibre_book["title"],
                    title_slug=title_slug,
                    primary_author=author,
                    status=BookStatus.TO_READ,
                    shelf=calibre_book["*shelf"],
                    pages=calibre_book.get("*pages", 0),
                    source="calibre",
                )
