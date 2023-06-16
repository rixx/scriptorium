import json

from django.core.management.base import BaseCommand
from django.db import transaction

from scriptorium.main.models import ToRead


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        parser.add_argument("json_file")

    def handle(self, *args, json_file, **options):
        with open(json_file) as f:
            result = json.load(f)
        calibre_books = {(b["title"], b["authors"]): b for b in result}
        scriptorium_books = {(b.title, b.author): b.id for b in ToRead.objects.all()}
        unknown = set(calibre_books) - set(scriptorium_books)
        too_many = set(scriptorium_books) - set(calibre_books)

        with transaction.atomic():
            ToRead.objects.filter(
                id__in=(v for k, v in scriptorium_books.items() if k in too_many)
            ).delete()
            ToRead.objects.bulk_create(
                [
                    ToRead(
                        title=b["title"],
                        author=b["authors"],
                        shelf=b["*shelf"],
                        pages=b.get("*pages", 0),
                        source="calibre",
                    )
                    for k, b in calibre_books.items()
                    if k in unknown
                ],
                ignore_conflicts=True,
            )
