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
        books = json.loads(result)
        ToRead.objects.bulk_create(
            [ToRead(title=b["title"], author=b["authors"], shelf=b["*shelf"], pages=b["*pages"], source="calibre")
            for b in books],
            ignore_conflicts=True,
        )
