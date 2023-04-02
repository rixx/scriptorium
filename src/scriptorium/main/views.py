from itertools import groupby

import networkx as nx
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import CreateView, FormView, TemplateView, UpdateView
from django_context_decorator import context
from formtools.wizard.views import SessionWizardView

from scriptorium.main.forms import (
    AuthorForm,
    BookEditForm,
    BookSearchForm,
    BookSelectForm,
    BookWizardForm,
    EditionSelectForm,
    LoginForm,
    PageForm,
    ReviewEditForm,
    ReviewWizardForm,
)
from scriptorium.main.models import Author, Book, Page, Review, Tag, ToRead
from scriptorium.main.stats import (
    get_all_years,
    get_edges,
    get_graph,
    get_nodes,
    get_stats_grid,
    get_stats_table,
    get_year_stats,
)
from scriptorium.main.utils import slugify


class ActiveTemplateView(TemplateView):
    @context
    def active(self):
        return getattr(self, "active", None)


class IndexView(ActiveTemplateView):
    template_name = "public/index.html"

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
            Review.objects.all().filter(dates_read__contains=self.year),
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


class ReviewByAuthor(YearNavMixin, ActiveTemplateView):
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


class ReviewBySeries(YearNavMixin, ActiveTemplateView):
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


class StatsView(ActiveTemplateView):
    template_name = "public/stats.html"
    active = "stats"

    @context
    def grid(self):
        return get_stats_grid()

    @context
    def table(self):
        return get_stats_table()


class GraphView(ActiveTemplateView):
    template_name = "public/graph.html"
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


class ReviewMixin:
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


class ReviewView(ReviewMixin, ActiveTemplateView):
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


class QueueView(ActiveTemplateView):
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


class ListView(ActiveTemplateView):
    template_name = "public/tags.html"
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
    template_name = "public/tag.html"
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


class AuthorMixin:
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


class AuthorView(AuthorMixin, ActiveTemplateView):
    template_name = "public/author.html"
    active = "review"


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
                return redirect("/b/new")
        return redirect("/b/login")


def logout_view(request):
    logout(request)
    return redirect("/")


class TohuwabohuView(LoginRequiredMixin, TemplateView):
    template_name = "private/tohuwabohu.html"

    @context
    def no_pages(self):
        return Book.objects.filter(Q(pages__isnull=True) | Q(pages__lte=1))

    @context
    def no_related(self):
        return Book.objects.filter(related_books__isnull=True)

    @context
    def no_plot(self):
        return Book.objects.filter(Q(plot__isnull=True) | Q(plot=""))

    @context
    def no_cover(self):
        return Book.objects.filter(Q(cover__isnull=True) | Q(cover=""))

    @context
    def goodreads_cover(self):
        return Book.objects.filter(cover__isnull=False, spine_color="#dad2bf")


class Bibliothecarius(LoginRequiredMixin, TemplateView):
    template_name = "private/bibliothecarius.html"


class AuthorEdit(AuthorMixin, LoginRequiredMixin, UpdateView):
    template_name = "private/author_edit.html"
    model = Author
    form_class = AuthorForm

    def get_object(self):
        return self.author_obj

    def form_valid(self, form):
        form.save()
        return redirect(f"/{form.instance.name_slug}/")


class ReviewCreate(LoginRequiredMixin, SessionWizardView):
    active = "review"
    form_list = [
        ("search", BookSearchForm),
        ("select", BookSelectForm),
        ("edition", EditionSelectForm),
        ("book", BookWizardForm),
        ("review", ReviewWizardForm),
        # ("quotes", QuoteWizardForm),
    ]
    template_name = "private/review_create.html"

    #     def get_template_names(self):
    #         return f"new_review_{self.steps.current}.html"

    def get_form_kwargs(self, step=None):
        kwargs = {}
        from scriptorium.main.metadata import (
            get_openlibrary_book,
            get_openlibrary_editions,
            search_book,
        )

        if step == "select":
            kwargs["works"] = search_book(
                self.get_cleaned_data_for_step("search")["search_input"]
            )
        elif step == "edition":
            # includes cover
            select_data = self.get_cleaned_data_for_step("select")
            editions = get_openlibrary_editions(select_data["search_selection"])
            kwargs[
                "editions"
            ] = editions  # form can use url https://covers.openlibrary.org/b/olid/{key}-L.jpg to preview the cover, and should build a select from key, title, language, whatever
        elif step == "book":
            olid = self.get_cleaned_data_for_step("edition")["edition_selection"]
            book = get_openlibrary_book(olid=olid)
            kwargs["openlibrary"] = book
            # kwargs = {# TODO pre-fill fields here!}
        elif step == "review":
            select_data = self.get_cleaned_data_for_step("select")
        return kwargs

    @transaction.atomic()
    def done(self, form_list, *args, **kwargs):
        steps = {
            step: self.get_cleaned_data_for_step(step) for step in self.form_list.keys()
        }
        author_name = steps["book"].pop("author_name")
        author, _ = Author.objects.get_or_create(
            name=author_name, defaults={"name_slug": slugify(author_name)}
        )
        new_tags = steps["book"].pop("new_tags").split(",")
        tags = list(steps["book"].pop("tags")) or []
        if new_tags:
            for tag in new_tags:
                tags.append(
                    Tag.objects.create(name=tag.strip(), name_slug=slugify(tag))
                )
        book = Book.objects.create(**steps["book"], primary_author=author)
        book.tags.set(tags)
        review = Review.objects.create(
            **steps["review"],
            book=book,
            latest_date=steps["review"]["dates_read"].split(",")[-1],
        )
        # TODO create quotes
        # TODO download cover, update dimensions etc
        return redirect(f"/{book.slug}/")


class ReviewEdit(LoginRequiredMixin, ReviewMixin, UpdateView):
    template_name = "private/review_edit.html"
    model = Book
    form_class = BookEditForm

    def get_object(self):
        return self.book

    @context
    @cached_property
    def review_form(self):
        if self.request.method == "POST":
            return ReviewEditForm(self.request.POST, instance=self.book.review)
        return ReviewEditForm(instance=self.book.review)

    def form_valid(self, form):
        if not self.review_form.is_valid():
            raise Exception(self.review_form.errors)
        form.save()
        self.review_form.save()
        return redirect(f"/{form.instance.slug}/")


class PageCreate(LoginRequiredMixin, CreateView):
    model = Page
    form_class = PageForm
    template_name = "private/page_create.html"

    def form_valid(self, form):
        form.save()
        return redirect(f"/p/{form.instance.slug}/")


class PageEdit(LoginRequiredMixin, UpdateView):
    model = Page
    form_class = PageForm
    template_name = "private/page_edit.html"

    def get_object(self):
        return Page.objects.get(slug=self.kwargs["slug"])

    def form_valid(self, form):
        form.save()
        return redirect(f"/p/{form.instance.slug}/")


class PageList(LoginRequiredMixin, TemplateView):
    template_name = "private/page_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pages"] = Page.objects.all()
        return context


class PageView(TemplateView):
    template_name = "public/page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = Page.objects.get(slug=self.kwargs["slug"])
        context["page"] = page
        return context
