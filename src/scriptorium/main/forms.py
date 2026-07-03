import datetime as dt

from django import forms
from django.db.models import Q

from scriptorium.main.models import (
    Author,
    Book,
    Page,
    Poem,
    Quote,
    Read,
    Review,
    Tag,
    ToReview,
)
from scriptorium.main.utils import slugify


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
            ("review__rating", "Rating"),
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
            .select_related("primary_author", "review")
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
            qs = qs.filter(series=series)
        if search := data.get("search_input"):
            text_search = (
                Q(title__icontains=search)
                | Q(title_slug__icontains=search)
                | Q(primary_author__name__icontains=search)
                | Q(additional_authors__name__icontains=search)
                | Q(series__icontains=search)
                | Q(isbn10=search)
                | Q(isbn13=search)
            )
            if data.get("fulltext"):
                text_search = (
                    text_search
                    | Q(review__text__icontains=search)
                    | Q(plot__icontains=search)
                )
            qs = qs.filter(text_search)
        if order_by := data.get("order_by"):
            if order_by in ("review__rating", "publication_year", "pages"):
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
    """The review form still takes comma-separated read dates and a book-level
    DNF flag; both are translated to Read rows rather than stored on Review."""

    dates_read = forms.CharField(
        help_text="Comma-separated dates, e.g. 2023-12-06,2024-01-31"
    )
    did_not_finish = forms.BooleanField(required=False)

    class Meta:
        model = Review
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
        reads = instance.book.reads
        reads.exclude(finished_on__in=dates).delete()
        existing = set(reads.values_list("finished_on", flat=True))
        for date in dates:
            if date not in existing:
                Read.objects.create(book=instance.book, finished_on=date)
        reads.update(did_not_finish=self.cleaned_data["did_not_finish"])
        # Read.save() only bumps latest_date upwards; removing the latest read
        # has to be reflected manually (without a feed date bump).
        instance.refresh_from_db(fields=["latest_date", "feed_date"])
        if instance.latest_date != dates[-1]:
            instance.latest_date = dates[-1]
            instance.save(update_fields=["latest_date"])
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


class ToReviewForm(forms.ModelForm):
    class Meta:
        model = ToReview
        fields = (
            "title",
            "author",
            "date",
            "series",
            "series_position",
            "notes",
            "quotes_file",
        )
