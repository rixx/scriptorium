from django.utils.functional import cached_property
from django_context_decorator import context

from scriptorium.main.models import Author, Book, Poem


class ActiveTemplateMixin:
    @context
    def active(self):
        return getattr(self, "active", None)


class ReviewMixin:
    @context
    @cached_property
    def book(self):
        return (
            Book.objects.select_related("primary_author", "review")
            .prefetch_related(
                "tags",
                "additional_authors",
                "related_books__destination",
                "related_books__destination__primary_author",
                "related_books__destination__additional_authors",
                "related_books__destination__review",
                "quotes",
            )
            .get(
                primary_author__name_slug=self.kwargs["author"],
                title_slug=self.kwargs["book"],
            )
        )

    @context
    @cached_property
    def review(self):
        return self.book.review

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
            .select_related("review", "primary_author")
            .prefetch_related("additional_authors")
            .order_by("-review__rating")
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
