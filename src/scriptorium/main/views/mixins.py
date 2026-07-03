from django.utils.functional import cached_property
from django_context_decorator import context

from scriptorium.main.models import Author, Book, Poem


class ActiveTemplateMixin:
    @context
    def active(self):
        return getattr(self, "active", None)


class ReviewMixin:
    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        # The URL kwarg "book" (just the title slug) shadows the @context
        # property below, so set the Book object explicitly.
        result["book"] = self.book
        return result

    @context
    @cached_property
    def book(self):
        return (
            Book.objects.select_related("primary_author")
            .prefetch_related(
                "tags",
                "additional_authors",
                "reads",
                "related_books__destination",
                "related_books__destination__primary_author",
                "related_books__destination__additional_authors",
                "quotes",
            )
            .get(
                primary_author__name_slug=self.kwargs["author"],
                title_slug=self.kwargs["book"],
            )
        )

    @context
    @cached_property
    def title(self):
        return f"{self.book.title} by {self.book.author_string}"


class AuthorMixin:
    @context
    @cached_property
    def title(self):
        return str(self.author_obj)

    @context
    @cached_property
    def author_obj(self):
        return Author.objects.get(name_slug=self.kwargs["author"])

    @context
    def books(self):
        return (
            self.author_obj.books.all()
            .select_related("primary_author")
            .prefetch_related("additional_authors")
            .order_by("-rating")
        )


class PoemMixin:
    active = "poems"

    def get_object(self):
        if "book" in self.kwargs:
            return Poem.objects.get(
                book__title_slug=self.kwargs["book"],
                book__primary_author__name_slug=self.kwargs["author"],
                slug=self.kwargs["slug"],
            )
        try:
            return Poem.objects.get(
                author__name_slug=self.kwargs["author"], slug=self.kwargs["slug"]
            )
        except Poem.DoesNotExist:
            return Poem.objects.get(
                url_slug=self.kwargs["author"], slug=self.kwargs["slug"]
            )

    @context
    @cached_property
    def poem(self):
        return self.get_object()

    @context
    @cached_property
    def book(self):
        return self.poem.book
