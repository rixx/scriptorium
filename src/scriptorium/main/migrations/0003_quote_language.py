# Generated by Django 4.1.5 on 2023-01-02 21:53

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0002_alter_book_cover"),
    ]

    operations = [
        migrations.AddField(
            model_name="quote",
            name="language",
            field=models.CharField(default="en", max_length=2),
        ),
    ]
