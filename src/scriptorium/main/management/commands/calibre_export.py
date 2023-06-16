import json
import subprocess

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def handle(self, *args, **options):
        query = "'tags:\"=on-device\" tags:\"to-read\"'"
        result = subprocess.check_output(
            f"calibredb list -s {query} --fields authors,title,*pages,*shelf --for-machine",
            shell=True,
            env={},
        ).decode()
        with open("calibre_books.json", "w") as f:
            # Round-trip through json to make sure it's valid
            json.dump(json.loads(result), f)
            print("Wrote calibre_books.json")
