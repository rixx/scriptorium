from collections import defaultdict
from itertools import groupby

import networkx as nx
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.template import loader
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import ListView, TemplateView
from django_context_decorator import context

from scriptorium.main.forms import CatalogueForm
from scriptorium.main.models import Author, Book, Review, Tag, ToRead
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
        return Book.objects.all().order_by("-review__latest_date")[:5]


def feed_view(request):
    template = loader.get_template("feed.atom")
    context = {
        "reviews": Review.objects.all()
        .filter(is_draft=False)
        .annotate(
            relevant_date=Coalesce(
                "feed_date",
                "latest_date",
            )
        )
        .order_by("-relevant_date")[:20]
    }
    headers = {
        "Content-Type": "application/atom+xml",
    }
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
    def reviews(self):
        return sorted(
            Review.objects.all()
            .filter(dates_read__contains=self.year)
            .select_related("book", "book__primary_author")
            .prefetch_related("book__additional_authors"),
            key=lambda review: review.date_read_lookup[self.year],
            reverse=True,
        )

    @context
    @cached_property
    def books(self):
        return [review.book for review in self.reviews]


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
        authors = (
            Author.objects.all()
            .prefetch_related(
                "books",
                "books__review",
                "books__additional_authors",
                "books__primary_author",
            )
            .order_by("name")
        )
        authors = {}
        for book in (
            Book.objects.all()
            .select_related("primary_author", "review")
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
                    list(sorted(authors.values(), key=sort_authors)),
                    key=sort_authors,
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
        context["missing_nodes"] = (
            Review.objects.all().count() - graph.number_of_nodes()
        )
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
            self.book.refresh_from_db()
        return FileResponse(self.book.cover_thumbnail.thumb)


class ReviewCoverSquareView(ReviewView):
    def dispatch(self, *args, **kwargs):
        if not self.book.cover:
            return HttpResponseNotFound()
        if not self.book.cover_square or not self.book.cover_square.thumb:
            self.book.update_thumbnail()
            self.book.refresh_from_db()
        return FileResponse(self.book.cover_square.thumb)


class QueueView(ActiveTemplateMixin, TemplateView):
    template_name = "public/list_queue.html"
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
            .annotate(
                book_count=Count("book"),
                rating=Avg("book__review__rating"),
            )
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
        return Tag.objects.prefetch_related("book_set", "book_set__review").get(
            name_slug=self.kwargs["tag"]
        )

    @context
    def books(self):
        return self.tag_obj.book_set.all().order_by("-review__rating")


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
