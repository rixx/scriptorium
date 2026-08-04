from collections import defaultdict

from django.db import migrations, models


def _merge(tags):
    """Fold a group of same-category duplicates into the row with the most
    books, keeping the more informative name and text."""
    tags.sort(key=lambda tag: (-tag.book_set.count(), tag.pk))
    keep, *duplicates = tags
    for duplicate in duplicates:
        keep.book_set.add(*duplicate.book_set.all())
        if not keep.text and duplicate.text:
            keep.text = duplicate.text
        if keep.name == keep.name_slug and duplicate.name != duplicate.name_slug:
            keep.name = duplicate.name
        duplicate.delete()
    if duplicates:
        keep.save(update_fields=["name", "text"])
    return keep


def deduplicate_tag_slugs(apps, schema_editor):
    """Make every tag slug unique, since /lists/<slug>/ resolves a single row.

    Duplicates within one category are merged; a slug shared across categories
    keeps the busiest row's slug and suffixes the others with their category.
    """
    Tag = apps.get_model("main", "Tag")

    by_slug = defaultdict(list)
    for tag in Tag.objects.all():
        by_slug[tag.name_slug].append(tag)

    for slug, tags in by_slug.items():
        if len(tags) == 1:
            continue
        by_category = defaultdict(list)
        for tag in tags:
            by_category[tag.category].append(tag)
        survivors = [_merge(group) for group in by_category.values()]
        survivors.sort(key=lambda tag: (-tag.book_set.count(), tag.pk))
        for tag in survivors[1:]:
            candidate = f"{slug}-{tag.category}"
            suffix = 2
            while Tag.objects.filter(name_slug=candidate).exclude(pk=tag.pk).exists():
                candidate = f"{slug}-{tag.category}-{suffix}"
                suffix += 1
            tag.name_slug = candidate
            tag.save(update_fields=["name_slug"])


class Migration(migrations.Migration):
    dependencies = [("main", "0034_read_highlights_read_koreader_md5")]

    operations = [
        migrations.RunPython(deduplicate_tag_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tag",
            name="name_slug",
            field=models.CharField(max_length=300, unique=True),
        ),
    ]
