# Generated by Django 4.1.9 on 2023-10-20 15:12

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0016_add_poem_model"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="poem",
            name="book_title",
        ),
        migrations.AddField(
            model_name="poem",
            name="author_name",
            field=models.CharField(
                blank=True,
                help_text="Use if the author is not in the database",
                max_length=300,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="poem",
            name="url_slug",
            field=models.CharField(
                blank=True,
                help_text="Use if neither book nor author are in the database. Slug field!",
                max_length=300,
                null=True,
            ),
        ),
    ]
