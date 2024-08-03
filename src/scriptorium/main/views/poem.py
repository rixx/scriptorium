from django.db.models import Q
from django.views.generic import DetailView, ListView

from scriptorium.main.models import Poem
from scriptorium.main.views.mixins import (
    ActiveTemplateMixin,
    AuthorMixin,
    PoemMixin,
    ReviewMixin,
)


class PoemList(ActiveTemplateMixin, ListView):
    template_name = "public/poem_list.html"
    model = Poem
    context_object_name = "poems"
    active = "poems"


class PoemAuthorList(AuthorMixin, ActiveTemplateMixin, ListView):
    template_name = "public/poem_author_list.html"
    model = Poem
    context_object_name = "poems"
    active = "poems"

    def get_queryset(self):
        return Poem.objects.all().filter(
            Q(author__name_slug=self.kwargs["author"])
            | Q(book__primary_author__name_slug=self.kwargs["author"])
            | Q(book__additional_authors__name_slug=self.kwargs["author"])
        )


class PoemBookList(ReviewMixin, ActiveTemplateMixin, ListView):
    template_name = "public/poem_book_list.html"
    model = Poem
    context_object_name = "poems"
    active = "poems"

    def get_queryset(self):
        return Poem.objects.all().filter(
            book__primary_author__name_slug=self.kwargs["author"],
            book__title_slug=self.kwargs["book"],
        )


class PoemView(PoemMixin, ActiveTemplateMixin, DetailView):
    template_name = "public/poem_detail.html"
    model = Poem
