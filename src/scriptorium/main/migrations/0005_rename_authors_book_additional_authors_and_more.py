# Generated by Django 4.1.5 on 2023-01-02 22:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0004_rename_book_tags_book_tags_alter_review_book"),
    ]

    operations = [
        migrations.RenameField(
            model_name="book",
            old_name="authors",
            new_name="additional_authors",
        ),
        migrations.AddField(
            model_name="book",
            name="primary_author",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="books",
                to="main.author",
            ),
        ),
    ]
