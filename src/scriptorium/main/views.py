from itertools import groupby

import networkx as nx
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Sum
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import FormView, TemplateView
from django_context_decorator import context

from scriptorium.main.forms import LoginForm
from scriptorium.main.models import Author, Book, Review, Tag, ToRead
from scriptorium.main.stats import (
    get_all_years,
    get_edges,
    get_graph,
    get_nodes,
    get_stats_grid,
    get_stats_table,
    get_year_stats,
)


class ActiveTemplateView(TemplateView):
    @context
    def active(self):
        return getattr(self, "active", None)


class IndexView(ActiveTemplateView):
    template_name = "index.html"

    @context
    def shelf_books(self):
        return Book.objects.all().order_by("primary_author__name")

    @context
    def books(self):
        return Book.objects.all().order_by("-review__latest_date")[:5]


def feed_view(request):
    from django.template import loader

    template = loader.get_template("feed.atom")
    context = {"reviews": Review.objects.all().order_by("-latest_date")[:20]}
    headers = {
        "Content-Type": "application/atom+xml",
    }
    return HttpResponse(template.render(context, request), headers=headers)


class YearNavMixin:
    @context
    def all_years(self):
        return get_all_years()


class YearView(YearNavMixin, ActiveTemplateView):
    template_name = "list_reviews.html"
    active = "read"

    @context
    @cached_property
    def year(self):
        return self.kwargs.get("year") or now().year

    @context
    @cached_property
    def current_year(self):
        return self.year == now().year

    @context
    @cached_property
    def title(self):
        return f"Books read in {self.year}"

    @context
    @cached_property
    def reviews(self):
        return sorted(
            Review.objects.all().filter(dates_read__contains=self.year),
            key=lambda review: review.date_read_lookup[self.year],
            reverse=True,
        )

    @context
    @cached_property
    def books(self):
        return [review.book for review in self.reviews]


class YearInBooksView(YearView):
    template_name = "year_stats.html"
    active = "read"

    @context
    @cached_property
    def title(self):
        return f"{self.year} in books"

    @context
    @cached_property
    def stats(self):
        return get_year_stats(self.year)


class ReviewByAuthor(YearNavMixin, ActiveTemplateView):
    template_name = "list_by_author.html"
    active = "read"

    @context
    @cached_property
    def title(self):
        return "Books by author"

    @context
    @cached_property
    def year(self):
        return "by-author"

    @context
    @cached_property
    def authors(self):
        authors = (
            Author.objects.all()
            .prefetch_related("books", "books__review")
            .order_by("name")
        )
        return sorted(
            [
                (letter, list(authors))
                for letter, authors in groupby(
                    authors,
                    key=lambda author: (
                        author.name[0].upper() if author.name[0].isalpha() else "_"
                    ),
                )
            ],
            key=lambda x: (not x[0].isalpha(), x[0].upper()),
        )


class ReviewByTitle(YearNavMixin, ActiveTemplateView):
    template_name = "list_by_title.html"
    active = "read"

    @context
    @cached_property
    def title(self):
        return "Books by title"

    @context
    @cached_property
    def year(self):
        return "by-title"

    @context
    @cached_property
    def books(self):
        return sorted(
            [
                (letter, list(reviews))
                for (letter, reviews) in groupby(
                    Book.objects.all().order_by("title"),
                    key=lambda book: (
                        book.title[0].upper()
                        if book.title[0].upper().isalpha()
                        else "_"
                    ),
                )
            ],
            key=lambda x: (not x[0].isalpha(), x[0].upper()),
        )


class ReviewBySeries(YearNavMixin, ActiveTemplateView):
    template_name = "list_by_series.html"
    active = "read"

    @context
    @cached_property
    def title(self):
        return "Books by series"

    @context
    @cached_property
    def year(self):
        return "by-series"

    @context
    @cached_property
    def books(self):
        series_reviews = [
            (
                series,
                sorted(list(books), key=lambda book: float(book.series_position)),
            )
            for series, books in groupby(
                sorted(
                    Book.objects.all()
                    .filter(series__isnull=False, series_position__isnull=False)
                    .exclude(series="")
                    .exclude(series_position=""),
                    key=lambda book: book.series,
                ),
                key=lambda book: book.series,
            )
        ]
        return sorted(
            [s for s in series_reviews if len(s[1]) > 1],
            key=lambda x: (not x[0][0].isalpha(), x[0].upper()),
        )


class StatsView(ActiveTemplateView):
    template_name = "stats.html"
    active = "stats"

    @context
    def grid(self):
        return get_stats_grid()

    @context
    def table(self):
        return get_stats_table()


class GraphView(ActiveTemplateView):
    template_name = "graph.html"
    active = "graph"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        graph = get_graph()
        context["node_count"] = graph.number_of_nodes()
        context["edge_count"] = graph.number_of_edges()
        context["missing_nodes"] = (
            Review.objects.all().count() - graph.number_of_nodes()
        )
        context["parts"] = nx.number_connected_components(graph)
        context["is_connected"] = nx.is_connected(graph)
        return context


def graph_data(request):
    graph = get_graph()
    return JsonResponse({"nodes": get_nodes(graph), "links": get_edges(graph)})


def search_data(request):
    # TODO tag search
    # search_tags = [
    # {
    #     "slug": tag.slug,
    #     "name": tag.metadata.get("title") or tag.slug,
    #     "search": (tag.metadata.get("title") or tag.slug).lower().split(),
    # }
    # for tag in tags.keys()
    # ]
    return JsonResponse({"books": get_nodes(), "tags": []})


class ReviewView(ActiveTemplateView):
    template_name = "review.html"
    active = "review"

    @context
    @cached_property
    def book(self):
        return Book.objects.get(
            primary_author__name_slug=self.kwargs["author"],
            title_slug=self.kwargs["book"],
        )

    @context
    @cached_property
    def review(self):
        return self.book.review


class ReviewCoverView(ReviewView):
    def dispatch(self, *args, **kwargs):
        if not self.book.cover:
            return HttpResponseNotFound()
        return FileResponse(self.book.cover)


class QueueView(ActiveTemplateView):
    template_name = "list_queue.html"
    active = "queue"

    @context
    def shelves(self):
        shelf_order = sorted(
            ToRead.objects.all().values_list("shelf", flat=True).distinct()
        )
        return [
            {
                "name": shelf,
                "books": ToRead.objects.all().filter(shelf=shelf),
                "page_count": ToRead.objects.all()
                .filter(shelf=shelf)
                .aggregate(page_count=Sum("pages"))["page_count"],
            }
            for shelf in shelf_order
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_books"] = ToRead.objects.all().count()
        context["total_pages"] = ToRead.objects.all().aggregate(
            page_count=Sum("pages")
        )["page_count"]
        past_year_reviews = Review.objects.all().filter(
            dates_read__contains=now().year - 1
        )
        context["past_year_books"] = past_year_reviews.count()
        context["past_year_pages"] = past_year_reviews.aggregate(
            page_count=Sum("book__pages")
        )["page_count"]
        context["factor_books"] = round(
            context["total_books"] / context["past_year_books"], 1
        )
        context["factor_pages"] = round(
            context["total_pages"] / context["past_year_pages"], 1
        )
        return context


class ListView(ActiveTemplateView):
    template_name = "tags.html"
    active = "list"

    @context
    def tags(self):
        result = []
        for tag in (
            Tag.objects.all()
            .prefetch_related("book_set", "book_set__review")
            .annotate(book_count=Count("book"), page_count=Sum("book__pages"))
            .order_by("-book_count")
        ):
            tag.top_books = tag.book_set.order_by("-review__rating")[:8]
            result.append(tag)
        return result


class ListDetail(ActiveTemplateView):
    template_name = "tag.html"
    active = "list"

    @context
    @cached_property
    def tag_obj(self):
        return Tag.objects.prefetch_related("book_set", "book_set__review").get(
            name_slug=self.kwargs["tag"]
        )

    @context
    def books(self):
        return self.tag_obj.book_set.all().order_by("-review__rating")


class AuthorView(ActiveTemplateView):
    template_name = "author.html"
    active = "review"

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


class LoginView(FormView):
    template_name = "login.html"
    form_class = LoginForm

    def post(self, request):
        form = self.get_form()
        if form.is_valid():
            user = authenticate(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user:
                login(request, user)
                return redirect("/bibliothecarius/new")
        return redirect("/bibliothecarius/login")


def logout_view(request):
    logout(request)
    return redirect("/")


class AuthorEdit(ActiveTemplateView):
    template_name = "index.html"
    active = "review"


class ReviewCreate(ReviewView):
    template_name = "index.html"
    active = "review"


class ReviewEdit(ReviewView):
    template_name = "index.html"
    active = "review"
