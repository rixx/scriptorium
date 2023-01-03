import json
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand
from scriptorium.main.models import ToRead


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def handle(self, *args, **options):

        query = "'tags:\"=on-device\"'"
        result = subprocess.check_output(
            f"calibredb list -s {query} --fields authors,title,*pages,*shelf --for-machine",
            shell=True,
            env={},
        ).decode()
        calibre_books = {(b["title"], b["authors"]): b for b in json.loads(result)}
        scriptorium_books = {(b.title, b.author): b.id for b in ToRead.objects.all()}
        unknown = set(calibre_books) - set(scriptorium_books)
        too_many = set(scriptorium_books) - set(calibre_books)
        ToRead.objects.filter(id__in=(v for k, v in scriptorium_books.items() if k in too_many))
        ToRead.objects.bulk_create(
            [ToRead(title=b["title"], author=b["authors"], shelf=b["*shelf"], pages=b["*pages"], source="calibre")
            for k, b in calibre_books.items() if k in unknown],
            ignore_conflicts=True,
        )
