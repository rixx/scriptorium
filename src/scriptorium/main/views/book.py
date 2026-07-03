from collections import defaultdict
from itertools import groupby

import networkx as nx
from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.template import loader
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import ListView, TemplateView
from django_context_decorator import context

from scriptorium.main.forms import CatalogueForm
from scriptorium.main.models import Book, BookStatus, Tag
from scriptorium.main.stats import (
    get_all_years,
    get_charts,
    get_edges,
    get_graph,
    get_nodes,
    get_stats_grid,
    get_stats_table,
    get_year_stats,
)
from scriptorium.main.views.mixins import ActiveTemplateMixin, AuthorMixin, ReviewMixin


class IndexView(ActiveTemplateMixin, TemplateView):
    template_name = "public/index.html"

    @context
    def shelf_books(self):
        return Book.objects.all().order_by("primary_author__name")

    @context
    def books(self):
        return Book.objects.annotate(last_read=Max("reads__finished_on")).order_by(
            "-last_read"
        )[:5]


def feed_view(request):
    template = loader.get_template("feed.atom")
    context = {
        "books": Book.objects.annotate(
            relevant_date=Coalesce("feed_date", Max("reads__finished_on"))
        )
        .order_by("-relevant_date")
        .prefetch_related("reads")[:20]
    }
    headers = {"Content-Type": "application/atom+xml"}
    return HttpResponse(template.render(context, request), headers=headers)


class YearNavMixin:
    @context
    def all_years(self):
        return get_all_years()


class YearView(YearNavMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/list_reviews.html"
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
    def books(self):
        return sorted(
            Book.objects.read_in_year(self.year).prefetch_related("reads"),
            key=lambda book: book.date_read_lookup[self.year],
            reverse=True,
        )


class YearInBooksView(YearView):
    template_name = "public/year_stats.html"
    active = "read"

    @context
    @cached_property
    def title(self):
        return f"{self.year} in books"

    @context
    @cached_property
    def stats(self):
        return get_year_stats(self.year)


class ReviewByAuthor(YearNavMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/list_by_author.html"
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
        authors = {}
        for book in (
            Book.objects.all()
            .select_related("primary_author")
            .prefetch_related("additional_authors")
        ):
            for author in book.authors:
                if author.pk not in authors:
                    authors[author.pk] = author
                    authors[author.pk].book_list = []
                authors[author.pk].book_list.append(book)

        def sort_authors(author):
            return author.name[0].upper() if author.name[0].isalpha() else "_"

        return sorted(
            [
                (letter, list(authors))
                for letter, authors in groupby(
                    sorted(authors.values(), key=sort_authors), key=sort_authors
                )
            ],
            key=lambda x: (not x[0].isalpha(), x[0].upper()),
        )


class ReviewByTitle(YearNavMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/list_by_title.html"
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


def series_position_sort_key(book):
    # series_position is free text and may hold ranges like "1-3"
    try:
        return (0, float(book.series_position), "")
    except ValueError:
        return (1, 0.0, book.series_position)


class ReviewBySeries(YearNavMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/list_by_series.html"
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
            (series, sorted(books, key=series_position_sort_key))
            for series, books in groupby(
                sorted(
                    Book.objects.all()
                    .filter(series__isnull=False, series_position__isnull=False)
                    .exclude(series_position=""),
                    key=lambda book: book.series.name,
                ),
                key=lambda book: book.series.name,
            )
        ]
        return sorted(
            [s for s in series_reviews if len(s[1]) > 1],
            key=lambda x: (not x[0][0].isalpha(), x[0].upper()),
        )


class StatsView(ActiveTemplateMixin, TemplateView):
    template_name = "public/stats.html"
    active = "stats"

    @context
    @cached_property
    def grid(self):
        return get_stats_grid()

    @context
    @cached_property
    def table(self):
        return get_stats_table()

    @context
    @cached_property
    def charts(self):
        return get_charts()

    @context
    @cached_property
    def title(self):
        return "Reading stats"


class GraphView(ActiveTemplateMixin, TemplateView):
    template_name = "public/graph.html"
    active = "graph"

    @context
    @cached_property
    def title(self):
        return "Book graph"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        graph = get_graph()
        context["node_count"] = graph.number_of_nodes()
        context["edge_count"] = graph.number_of_edges()
        context["missing_nodes"] = Book.objects.all().count() - graph.number_of_nodes()
        context["parts"] = nx.number_connected_components(graph)
        context["is_connected"] = nx.is_connected(graph)
        return context


def graph_data(request):
    graph = get_graph()
    return JsonResponse({"nodes": get_nodes(graph), "links": get_edges(graph)})


class ReviewView(ReviewMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/review.html"
    active = "review"


class ReviewCoverView(ReviewView):
    def dispatch(self, *args, **kwargs):
        if not self.book.cover:
            return HttpResponseNotFound()
        return FileResponse(self.book.cover)


class ReviewCoverThumbnailView(ReviewView):
    def dispatch(self, *args, **kwargs):
        if not self.book.cover:
            return HttpResponseNotFound()
        if not self.book.cover_thumbnail or not self.book.cover_thumbnail.thumb:
            self.book.update_thumbnail()
            self.book.__dict__.pop("cover_thumbnail", None)
        return FileResponse(self.book.cover_thumbnail.thumb)


class QueueView(ActiveTemplateMixin, TemplateView):
    template_name = "public/list_queue.html"
    active = "queue"

    @cached_property
    def queue(self):
        return Book.all_objects.filter(status=BookStatus.TO_READ).select_related(
            "primary_author"
        )

    @context
    def shelves(self):
        shelf_order = sorted(
            self.queue.exclude(shelf__isnull=True)
            .values_list("shelf", flat=True)
            .distinct()
        )
        return [
            {
                "name": shelf,
                "books": self.queue.filter(shelf=shelf),
                "page_count": self.queue.filter(shelf=shelf).aggregate(
                    page_count=Sum("pages")
                )["page_count"],
            }
            for shelf in shelf_order
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_books"] = self.queue.count()
        context["total_pages"] = self.queue.aggregate(page_count=Sum("pages"))[
            "page_count"
        ]
        past_year_books = Book.objects.read_in_year(now().year - 1)
        context["past_year_books"] = past_year_books.count()
        context["past_year_pages"] = past_year_books.aggregate(page_count=Sum("pages"))[
            "page_count"
        ]
        context["factor_books"] = round(
            context["total_books"] / context["past_year_books"], 1
        )
        context["factor_pages"] = round(
            context["total_pages"] / context["past_year_pages"], 1
        )
        return context

    @context
    @cached_property
    def title(self):
        return "Reading queue"


class TagView(ActiveTemplateMixin, TemplateView):
    template_name = "public/tags.html"
    active = "list"

    @context
    @cached_property
    def title(self):
        return "Tags"

    @context
    def tags(self):
        tags = (
            Tag.objects.all()
            .annotate(book_count=Count("book"), rating=Avg("book__rating"))
            .filter(book_count__gt=0)
            .order_by("-book_count")
        )
        # grouped by category
        grouped_tags = defaultdict(list)
        for tag in tags:
            grouped_tags[tag.category].append(tag)
        return grouped_tags


class ListDetail(ActiveTemplateMixin, TemplateView):
    template_name = "public/tag.html"
    active = "list"

    @context
    @cached_property
    def title(self):
        return str(self.tag_obj)

    @context
    @cached_property
    def tag_obj(self):
        return Tag.objects.prefetch_related("book_set").get(
            name_slug=self.kwargs["tag"]
        )

    @context
    def books(self):
        return self.tag_obj.book_set.all().order_by("-rating")


class AuthorView(AuthorMixin, ActiveTemplateMixin, TemplateView):
    template_name = "public/author.html"
    active = "review"


class CatalogueView(ListView):
    template_name = "public/catalogue.html"
    paginate_by = 100
    model = Book
    context_object_name = "books"
    active = "catalogue"

    @context
    @cached_property
    def title(self):
        return "Catalogue"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = CatalogueForm(self.request.GET)
        context["active"] = self.active
        return context

    def get_queryset(self):
        form = CatalogueForm(self.request.GET)
        if form.is_valid():
            return form.get_queryset()
        return Book.objects.none()
