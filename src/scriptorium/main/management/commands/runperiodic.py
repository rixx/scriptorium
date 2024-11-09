from django.core.management.base import BaseCommand
from django.db.models import Count, F

from scriptorium.main.models import Book, Review, ToReview


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def handle(self, *args, **options):
        for book in Book.objects.filter(spine_color__isnull=True).exclude(cover=""):
            try:
                book.update_spine_color()
                book.update_thumbnail()
                book.save()
            except Exception as e:
                print(e)

        for toreview in ToReview.objects.all().filter(book__isnull=True):
            toreview.match()

        toreview_objects = []
        qs = (
            Review.objects.with_dates_read()
            .annotate(toreview_count=Count("book__toreview"))
            .filter(toreview_count__lt=F("dates_read_count"))
        )
        for review in qs:
            for i in range(review.dates_read_count - review.toreview_count):
                toreview_objects.append(
                    ToReview(
                        book=review.book,
                        title=review.book.title,
                        author=review.book.primary_author.name,
                        series=review.book.series,
                        series_position=review.book.series_position,
                        date=review.dates_read_list[-i - 1],
                    )
                )

        ToReview.objects.bulk_create(toreview_objects)
