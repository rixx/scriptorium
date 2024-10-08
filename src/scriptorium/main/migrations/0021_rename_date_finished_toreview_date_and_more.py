# Generated by Django 4.1.13 on 2024-08-03 20:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0020_toreview"),
    ]

    operations = [
        migrations.RenameField(
            model_name="toreview",
            old_name="date_finished",
            new_name="date",
        ),
        migrations.RemoveField(
            model_name="toreview",
            name="date_started",
        ),
        migrations.AddField(
            model_name="toreview",
            name="book",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="main.book",
            ),
        ),
    ]
