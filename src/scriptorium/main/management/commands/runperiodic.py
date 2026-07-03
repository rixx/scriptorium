from django.core.management.base import BaseCommand
from django.db.models import Q

from scriptorium.main.models import Book


class Command(BaseCommand):
    help = "Regenerates missing spine colours and thumbnails"

    def handle(self, *args, **options):
        missing_colour = Q(spine_color__isnull=True) | Q(ui_color__isnull=True)
        for book in Book.all_objects.filter(missing_colour).exclude(cover=""):
            try:
                book.update_spine_color()
                book.update_ui_color()
                book.update_thumbnail()
                book.save()
            except Exception as e:  # noqa: BLE001
                print(e)
