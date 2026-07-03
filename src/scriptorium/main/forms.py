import datetime as dt

from django import forms
from django.db.models import Q
from django.utils.timezone import now

from scriptorium.main.models import Author, Book, Page, Poem, Quote, Read, Series, Tag
from scriptorium.main.utils import slugify


class SeriesNameField(forms.CharField):
    """Free-text series input that resolves to a Series row on clean,
    creating the series (deduplicated by slug) if it doesn't exist yet."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def clean(self, value):
        name = super().clean(value)
        if not name:
            return None
        return Series.objects.get_or_create_by_name(name)[0]


class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ("name", "name_slug", "text")


class CatalogueForm(forms.Form):
    search_input = forms.CharField(
        label="Search for a book",
        widget=forms.TextInput(attrs={"autofocus": True}),
        required=False,
    )
    fulltext = forms.BooleanField(required=False)
    tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.none(), required=False)

    # Allow to search by author and series, but only via links
    author = forms.ModelChoiceField(
        queryset=Author.objects.all(), required=False, widget=forms.HiddenInput
    )
    series = forms.CharField(required=False, widget=forms.HiddenInput)

    order_by = forms.ChoiceField(
        choices=(
            ("rating", "Rating"),
            ("title", "Title"),
            ("primary_author__name", "Author"),
            ("publication_year", "Publication year"),
            ("pages", "Pages"),
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags"].queryset = Tag.objects.filter(book__isnull=False).distinct()

    def get_queryset(self):
        if not self.is_valid():
            return Book.objects.none()
        data = self.cleaned_data
        qs = (
            Book.objects.all()
            .select_related("primary_author")
            .prefetch_related("additional_authors", "tags")
        )

        if tags := data.get("tags"):
            for tag in tags:
                qs = qs.filter(tags__in=[tag])
        if author := data.get("author"):
            qs = qs.filter(
                Q(primary_author=author) | Q(additional_authors__in=[author])
            )
        if series := data.get("series"):
            qs = qs.filter(series__name=series)
        if search := data.get("search_input"):
            text_search = (
                Q(title__icontains=search)
                | Q(title_slug__icontains=search)
                | Q(primary_author__name__icontains=search)
                | Q(additional_authors__name__icontains=search)
                | Q(series__name__icontains=search)
                | Q(isbn10=search)
                | Q(isbn13=search)
            )
            if data.get("fulltext"):
                text_search = (
                    text_search | Q(text__icontains=search) | Q(plot__icontains=search)
                )
            qs = qs.filter(text_search)
        if order_by := data.get("order_by"):
            if order_by in ("rating", "publication_year", "pages"):
                order_by = f"-{order_by}"
            qs = qs.order_by(order_by)
        else:
            qs = qs.order_by("primary_author__name")
        return qs


class BookSearchForm(forms.Form):
    search_input = forms.CharField(
        label="Search for a book", widget=forms.TextInput(attrs={"autofocus": True})
    )


class BookSelectForm(forms.Form):
    search_selection = forms.ChoiceField(widget=forms.RadioSelect)

    def __init__(self, *args, works, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["search_selection"].choices = [*works, ("manual", "Manual entry")]


class EditionSelectForm(forms.Form):
    edition_selection = forms.ChoiceField(widget=forms.RadioSelect)

    def __init__(self, *args, editions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["edition_selection"].choices = editions or []


class BookWizardForm(forms.ModelForm):
    new_tags = forms.CharField(required=False)
    author_name = forms.CharField()
    title_slug = forms.CharField(required=False)
    series = SeriesNameField()

    def __init__(self, *args, openlibrary=None, **kwargs):
        initial = kwargs.pop("initial", {})
        if openlibrary:
            initial["title"] = initial.get("title") or openlibrary["title"]
            initial["openlibrary_id"] = openlibrary["identifiers"]["openlibrary"]
            initial["isbn13"] = openlibrary["identifiers"].get("isbn_13", [""])[0]
            initial["goodreads_id"] = openlibrary["identifiers"].get("goodreads", [""])[
                0
            ]
            initial["pages"] = openlibrary.get(
                "number_of_pages", openlibrary.get("pagination")
            )
            if "cover" in openlibrary:
                initial["cover_source"] = openlibrary["cover"].get("large")
            initial["publication_year"] = openlibrary["publish_date"]
            initial["author_name"] = " & ".join(
                a["name"] for a in openlibrary["authors"]
            )
        if initial.get("title"):
            initial["title_slug"] = slugify(initial["title"])
        super().__init__(*args, **kwargs, initial=initial)

    def clean_new_tags(self):
        new_tags = self.cleaned_data["new_tags"]
        if new_tags:
            return [t.strip() for t in new_tags.split(",") if t.strip()]
        return []

    def clean(self, *args, **kwargs):
        result = super().clean(*args, **kwargs)
        if not self.cleaned_data["title_slug"]:
            self.cleaned_data["title_slug"] = slugify(self.cleaned_data["title"])
        return result

    class Meta:
        model = Book
        # TODO handle authors here D:
        fields = (
            "title",
            "title_slug",
            "author_name",
            "source",
            "pages",
            "cover_source",
            "goodreads_id",
            "isbn10",
            "isbn13",
            "publication_year",
            "series",
            "series_position",
            "tags",
            "new_tags",
            "plot",
        )


class ReviewForm(forms.ModelForm):
    """Edits the review fields on a Book. The form still takes comma-separated
    read dates and a book-level DNF flag; both are translated to Read rows
    rather than stored on the Book."""

    dates_read = forms.CharField(
        help_text="Comma-separated dates, e.g. 2023-12-06,2024-01-31"
    )
    did_not_finish = forms.BooleanField(required=False)

    class Meta:
        model = Book
        fields = ("rating", "text", "tldr")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["dates_read"].initial = ",".join(
                date.isoformat() for date in self.instance.dates_read_list
            )
            self.fields["did_not_finish"].initial = self.instance.did_not_finish

    def clean_dates_read(self):
        try:
            dates = sorted(
                {
                    dt.date.fromisoformat(part.strip())
                    for part in self.cleaned_data["dates_read"].split(",")
                    if part.strip()
                }
            )
        except ValueError:
            raise forms.ValidationError(
                "Dates must be YYYY-MM-DD, separated by commas."
            ) from None
        if not dates:
            raise forms.ValidationError("At least one read date is required.")
        return dates


class ReviewWizardForm(ReviewForm):
    pass


class BookEditForm(forms.ModelForm):
    new_tags = forms.CharField(required=False)
    series = SeriesNameField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["series"] = (
                self.instance.series.name if self.instance.series else ""
            )

    def clean_new_tags(self):
        new_tags = self.cleaned_data["new_tags"]
        if new_tags:
            return [t.strip() for t in new_tags.split(",") if t.strip()]
        return []

    def save(self, *args, **kwargs):
        # TODO put all this in BookMixin
        # download cover if necessary and recalculate spine colour
        # if part of a series, make sure series height is matching
        if "cover_source" in self.changed_data:
            self.instance.download_cover()
        return super().save(*args, **kwargs)

    class Meta:
        model = Book
        fields = (
            "title",
            "title_slug",
            "primary_author",
            "additional_authors",
            "cover_source",
            "goodreads_id",
            "isbn10",
            "isbn13",
            "dimensions",
            "source",
            "pages",
            "publication_year",
            "series",
            "series_position",
            "tags",
            "new_tags",
            "plot",
        )


class ReviewEditForm(ReviewForm):
    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        dates = self.cleaned_data["dates_read"]
        old_dates = set(instance.reads.values_list("finished_on", flat=True))
        old_feed_date = instance.feed_date
        instance.sync_reads(dates, remove_extra=True)
        # Only flatten the book-level checkbox onto all reads when it changed,
        # so unrelated edits keep mixed per-read DNF flags intact.
        did_not_finish = self.cleaned_data["did_not_finish"]
        if did_not_finish != all(read.did_not_finish for read in instance.reads.all()):
            instance.reads.update(did_not_finish=did_not_finish)
        # An edit only re-enters the feed when the latest read date strictly
        # increased (a genuine reread); corrections and removals keep the
        # previous feed date instead of looking like a new read.
        old_latest = max(old_dates, default=None)
        if old_latest is None or dates[-1] > old_latest:
            instance.feed_date = now().date()
        else:
            instance.feed_date = old_feed_date
        Book.all_objects.filter(pk=instance.pk).update(feed_date=instance.feed_date)
        # Saving the review form is a deliberate "the review is current"
        # action even when the text didn't change: it clears queued rereads.
        instance.mark_review_current()
        # The read-derived properties were cached when the form was built.
        for prop in (
            "dates_read_list",
            "latest_date",
            "date_read_lookup",
            "did_not_finish",
        ):
            instance.__dict__.pop(prop, None)
        return instance


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ("title", "slug", "text")


class QuoteForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = ("source_book", "source_author", "text", "language")

    def __init__(self, *args, source_book=None, source_author=None, **kwargs):
        super().__init__(*args, **kwargs)
        if source_book:
            self.fields["source_book"].initial = source_book
        if source_author:
            self.fields["source_author"].initial = source_author
        self.fields["source_book"].queryset = Book.objects.order_by("title")
        self.fields["source_author"].queryset = Author.objects.order_by("name")


class PoemForm(forms.ModelForm):
    class Meta:
        model = Poem
        fields = (
            "title",
            "slug",
            "book",
            "author",
            "author_name",
            "url_slug",
            "language",
            "status",
            "text",
            "context",
        )


class BookToReviewForm(forms.Form):
    """Quickly queue a finished book for a later review: creates (or reuses)
    the author and book, marks the book as waiting for review, and records
    the read itself."""

    title = forms.CharField()
    author = forms.CharField()
    date = forms.DateField(help_text="The date you finished the book")
    series = SeriesNameField()
    series_position = forms.CharField(required=False, max_length=10)
    notes = forms.CharField(required=False, widget=forms.Textarea)

    def save(self):
        data = self.cleaned_data
        book, _ = Book.all_objects.queue_for_review(
            title=data["title"],
            author_name=data["author"],
            date=data["date"],
            series=data["series"],
            series_position=data["series_position"],
            notes=data["notes"],
        )
        return book


class BookToReviewEditForm(BookToReviewForm):
    """Edit a book already queued for review: updates the existing Book and
    its recorded Read instead of creating new rows."""

    def __init__(self, *args, instance, **kwargs):
        self.instance = instance
        self.read = instance.reads.order_by("-finished_on").first()
        initial = kwargs.pop("initial", {})
        initial.update(
            {
                "title": instance.title,
                "author": instance.primary_author.name,
                "series": instance.series.name if instance.series else "",
                "series_position": instance.series_position or "",
            }
        )
        if self.read:
            initial["date"] = self.read.finished_on
            initial["notes"] = self.read.notes or ""
        super().__init__(*args, initial=initial, **kwargs)

    def save(self):
        data = self.cleaned_data
        book = self.instance
        author, _ = Author.objects.get_or_create_by_name(data["author"])
        book.title = data["title"]
        book.title_slug = slugify(data["title"])
        book.primary_author = author
        book.series = data["series"]
        book.series_position = data["series_position"] or None
        book.save()
        if self.read:
            self.read.finished_on = data["date"]
            self.read.notes = data["notes"] or None
            self.read.save()
        else:
            Read.objects.create(
                book=book,
                finished_on=data["date"],
                source="manual",
                notes=data["notes"] or None,
            )
        return book
