import random
from collections import defaultdict
from itertools import groupby

import networkx as nx
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect
from django.template import loader
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)
from django_context_decorator import context
from formtools.wizard.views import SessionWizardView

from scriptorium.main.forms import (
    AuthorForm,
    BookEditForm,
    BookSearchForm,
    BookSelectForm,
    BookWizardForm,
    CatalogueForm,
    EditionSelectForm,
    LoginForm,
    PageForm,
    PoemForm,
    QuoteForm,
    ReviewEditForm,
    ReviewWizardForm,
)
from scriptorium.main.models import Author, Book, Page, Poem, Quote, Review, Tag, ToRead
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
from scriptorium.main.utils import slugify


class ActiveTemplateMixin:
    @context
    def active(self):
        return getattr(self, "active", None)


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


class AuthorView(AuthorMixin, ActiveTemplateMixin, TemplateView):
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


def show_edition_step(wizard):
    return (wizard.get_cleaned_data_for_step("select") or {}).get(
        "search_selection"
    ) != "manual"


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
    condition_dict = {
        "edition": show_edition_step,
    }
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
            try:
                kwargs["works"] = search_book(
                    self.get_cleaned_data_for_step("search")["search_input"]
                )
            except Exception:
                messages.error(
                    self.request,
                    "Something went wrong while searching for books. Please try again or enter the data yourself.",
                )
                kwargs["works"] = [("manual", "Enter manually")]
        elif step == "edition":
            # includes cover
            select_data = self.get_cleaned_data_for_step("select")
            if select_data and select_data.get("search_selection") != "manual":
                try:
                    editions = get_openlibrary_editions(select_data["search_selection"])
                    kwargs["editions"] = (
                        editions  # form can use url https://covers.openlibrary.org/b/olid/{key}-L.jpg to preview the cover, and should build a select from key, title, language, whatever
                    )
                except Exception:
                    messages.error(
                        self.request,
                        "Something went wrong while searching for books. Please try again or enter the data yourself.",
                    )
                    kwargs["editions"] = []
        elif step == "book":
            if "edition" in self.get_form_list():
                olid = self.get_cleaned_data_for_step("edition")["edition_selection"]
                try:
                    book = get_openlibrary_book(olid=olid)
                    kwargs["openlibrary"] = book
                except Exception:
                    kwargs["openlibrary"] = {}
            # kwargs = {# TODO pre-fill fields here!}
        elif step == "review":
            select_data = self.get_cleaned_data_for_step("select")
        return kwargs

    @transaction.atomic()
    def done(self, form_list, *args, **kwargs):
        steps = {
            step: self.get_cleaned_data_for_step(step)
            for step in self.get_form_list().keys()
        }
        author_name = steps["book"].pop("author_name")
        author, _ = Author.objects.get_or_create(
            name=author_name, defaults={"name_slug": slugify(author_name)}
        )
        new_tags = steps["book"].pop("new_tags")
        tags = list(steps["book"].pop("tags")) or []
        if new_tags:
            for tag in new_tags:
                category, name = tag.split(":", maxsplit=1)
                tags.append(Tag.objects.create(name_slug=name, category=category))
        book = Book.objects.create(**steps["book"], primary_author=author)
        book.tags.set(tags)
        Review.objects.create(
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

    def form_invalid(self, form):
        messages.error(self.request, form.errors)
        return super().form_invalid(form)

    def form_valid(self, form):
        if not self.review_form.is_valid():
            messages.error(self.request, self.review_form.errors)
            raise Exception(self.review_form.errors)
        form.save()
        self.review_form.save()
        new_tags = form.cleaned_data.pop("new_tags")
        if new_tags:
            for tag in new_tags:
                category, name = tag.split(":", maxsplit=1)
                form.instance.tags.add(
                    Tag.objects.create(name_slug=name, category=category)
                )
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

    @context
    @cached_property
    def title(self):
        return str(self.page)

    @context
    @cached_property
    def page(self):
        return Page.objects.get(slug=self.kwargs["slug"])


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


class QuoteCreate(LoginRequiredMixin, CreateView):
    model = Quote
    form_class = QuoteForm
    template_name = "private/quote_create.html"

    def get_initial(self):
        initial = super().get_initial()
        if "book" in self.request.GET:
            book = Book.objects.filter(pk=self.request.GET["book"]).first()
            if book:
                initial["source_book"] = book
        elif "author" in self.request.GET:
            author = Author.objects.filter(pk=self.request.GET["author"]).first()
            if author:
                initial["source_author"] = author
        return initial

    def form_valid(self, form):
        form.save()
        action = self.request.POST.get("action")
        if action == "more":
            if form.instance.source_book:
                return redirect(f"/b/quotes/new/?book={form.instance.source_book_id}")
            if form.instance.source_author:
                return redirect(
                    f"/b/quotes/new/?author={form.instance.source_author_id}"
                )
            return redirect("/b/quotes/new/")
        return redirect(f"/q/{form.instance.id}/")


class QuoteEdit(LoginRequiredMixin, UpdateView):
    model = Quote
    form_class = QuoteForm
    template_name = "private/quote_edit.html"

    def form_valid(self, form):
        form.save()
        action = self.request.POST.get("action")
        if action == "more":
            if form.instance.source_book:
                return redirect(f"/b/quotes/new/?book={form.instance.source_book_id}")
            if form.instance.source_author:
                return redirect(
                    f"/b/quotes/new/?author={form.instance.source_author_id}"
                )
            return redirect("/b/quotes/new/")
        return redirect(f"/q/{form.instance.id}/")


class QuoteDelete(LoginRequiredMixin, DetailView):
    model = Quote

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        book = self.object.source_book
        author = self.object.source_author
        self.object.delete()
        if book:
            return redirect(f"/{book.slug}/")
        if author:
            return redirect(f"/a/{author.name_slug}/")
        return redirect("/q")


class QuoteView(DetailView):
    model = Quote
    template_name = "public/quote.html"
    context_object_name = "quote"

    @context
    @cached_property
    def title(self):
        return self.get_object().short_string


def border_image(request):
    number = request.GET.get("border")
    border_color = request.GET.get("color") or "990000"
    max_border = settings.MAX_BORDER
    if number:
        try:
            number = int(number)
            if number not in range(1, max_border + 1):
                raise ValueError
        except ValueError:
            print("error")
            number = None
    if not number:
        number = random.randint(1, max_border)

    template = loader.get_template(f"_borders/{number}.svg")
    rendered = template.render({"border_color": f"#{border_color}"})
    return HttpResponse(rendered, content_type="image/svg+xml")


class BorderImageList(TemplateView):
    template_name = "public/border_image_list.html"

    @context
    @cached_property
    def title(self):
        return "Border Images"

    @context
    @cached_property
    def max_border(self):
        return settings.MAX_BORDER


class PoemList(ActiveTemplateMixin, ListView):
    template_name = "public/poem_list.html"
    model = Poem
    context_object_name = "poems"
    active = "poems"


class PoemPrivateList(LoginRequiredMixin, ActiveTemplateMixin, ListView):
    template_name = "private/poem_list.html"
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


class PoemView(PoemMixin, ActiveTemplateMixin, DetailView):
    template_name = "public/poem_detail.html"
    model = Poem


class PoemEdit(PoemMixin, LoginRequiredMixin, FormView):
    template_name = "private/poem_edit.html"
    form_class = PoemForm

    def get_form_kwargs(self, **kwargs):
        kwargs = super().get_form_kwargs(**kwargs)
        kwargs["instance"] = self.poem
        return kwargs

    def form_valid(self, form):
        self.form = form
        form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return self.form.instance.get_absolute_url()


class PoemCreate(LoginRequiredMixin, CreateView):
    template_name = "private/poem_edit.html"
    form_class = PoemForm
    active = "poems"

    def get_success_url(self):
        return self.object.get_absolute_url()
