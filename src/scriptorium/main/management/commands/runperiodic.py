from django.core.management.base import BaseCommand

from scriptorium.main.models import Book


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def handle(self, *args, **options):
        for book in Book.objects.filter(spine_color__isnull=True):
            book.update_spine_color()
            book.update_thumbnail()
            book.save()
