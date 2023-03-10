from django import forms

from scriptorium.main.models import Author, Book, Review
from scriptorium.main.utils import slugify


class LoginForm(forms.Form):

    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ("name", "name_slug", "text")


class BookSearchForm(forms.Form):
    search_input = forms.CharField()


class BookSelectForm(forms.Form):
    search_selection = forms.ChoiceField()

    def __init__(self, *args, works, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["search_selection"].choices = works


class EditionSelectForm(forms.Form):
    edition_selection = forms.ChoiceField()

    def __init__(self, *args, editions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["edition_selection"].choices = editions


class BookWizardForm(forms.ModelForm):
    new_tags = forms.CharField(required=False)
    author_name = forms.CharField()

    def __init__(self, *args, openlibrary=None, **kwargs):
        initial = kwargs.pop("initial", {})
        if openlibrary:
            initial["title"] = initial.get("title") or openlibrary["title"]
            initial["openlibrary_id"] = openlibrary["identifiers"]["openlibrary"]
            initial["isbn13"] = openlibrary["identifiers"]["isbn_13"][0]
            initial["goodreads_id"] = openlibrary["identifiers"].get("goodreads")
            initial["pages"] = openlibrary.get(
                "number_of_pages", openlibrary.get("pagination")
            )
            initial["cover_source"] = openlibrary["cover"].get("large")
            initial["publication_year"] = openlibrary["publish_date"]
            initial["author_name"] = " & ".join(
                a["name"] for a in openlibrary["authors"]
            )
        if initial.get("title"):
            initial["title_slug"] = slugify(initial["title"])
        super().__init__(*args, **kwargs, initial=initial)

    class Meta:
        model = Book
        # TODO handle authors here D:
        fields = (
            "title",
            "title_slug",
            "author_name",
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


class ReviewWizardForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("dates_read", "rating", "text", "tldr", "did_not_finish")


class BookEditForm(forms.ModelForm):
    new_tags = forms.CharField(required=False)

    def save(self, *args, **kwargs):
        # TODO put all this in BookMixin
        # download cover if necessary and recalculate spine colour
        # if part of a series, make sure series height is matching
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


class ReviewEditForm(forms.ModelForm):
    def save(self, *args, **kwargs):
        # put all this in ReviewMixin
        # check dates_read to be a list of dates
        # set latest_date
        # validate rating
        return super().save(*args, **kwargs)

    class Meta:
        model = Review
        fields = ("dates_read", "rating", "text", "tldr", "did_not_finish")
