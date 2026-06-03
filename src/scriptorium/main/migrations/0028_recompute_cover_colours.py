"""Recompute every book's spine colour (now sampled from the left strip in
CIELAB) and populate the new equalised ui_color. Slow but one-off; safe to
re-run since it only ever reads covers and overwrites the two colour fields."""

from django.db import migrations

from scriptorium.main.utils import get_spine_color, get_ui_color


def recompute_colours(apps, schema_editor):
    Book = apps.get_model("main", "Book")
    books = Book.objects.exclude(cover="").exclude(cover__isnull=True)
    total = books.count()
    for i, book in enumerate(books.iterator(), 1):
        if not book.cover:
            continue
        try:
            book.spine_color = get_spine_color(book.cover)
            book.ui_color = get_ui_color(book.cover)
        except (OSError, ValueError) as e:
            print(f"  ! {book.pk} {book.cover.name}: {e}")  # noqa: T201
            continue
        book.save(update_fields=["spine_color", "ui_color"])
        if i % 50 == 0:
            print(f"  ... {i}/{total}")  # noqa: T201


class Migration(migrations.Migration):
    dependencies = [("main", "0027_book_ui_color")]

    operations = [migrations.RunPython(recompute_colours, migrations.RunPython.noop)]
