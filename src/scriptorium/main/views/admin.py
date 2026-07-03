import logging
from pathlib import Path

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.decorators.http import require_POST
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
    ApiTokenForm,
    AuthorForm,
    BookEditForm,
    BookSearchForm,
    BookSelectForm,
    BookToReviewEditForm,
    BookToReviewForm,
    BookWizardForm,
    EditionSelectForm,
    LoginForm,
    PageForm,
    PoemForm,
    QuoteForm,
    ReviewEditForm,
    ReviewWizardForm,
)
from scriptorium.main.models import (
    ApiToken,
    Author,
    Book,
    BookStatus,
    Page,
    Poem,
    Quote,
    Tag,
)
from scriptorium.main.views.mixins import (
    ActiveTemplateMixin,
    AuthorMixin,
    PoemMixin,
    ReviewMixin,
)

logger = logging.getLogger(__name__)


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

    @context
    def deploy_enabled(self):
        return bool(django_settings.DEPLOY_FLAG_FILE)


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
    ]
    condition_dict = {"edition": show_edition_step}
    template_name = "private/review_create.html"

    def get_form_kwargs(self, step=None):
        kwargs = {}
        from scriptorium.main.metadata import (  # noqa: PLC0415
            get_openlibrary_book,
            get_openlibrary_editions,
            search_book,
        )

        if step == "select":
            try:
                kwargs["works"] = search_book(
                    self.get_cleaned_data_for_step("search")["search_input"]
                )
            except Exception:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001
                    kwargs["openlibrary"] = {}
            # TODO pre-fill fields here
        elif step == "review":
            select_data = self.get_cleaned_data_for_step("select")
        return kwargs

    @transaction.atomic()
    def done(self, form_list, *args, **kwargs):
        steps = {
            step: self.get_cleaned_data_for_step(step) for step in self.get_form_list()
        }
        author_name = steps["book"].pop("author_name")
        author, _ = Author.objects.get_or_create_by_name(author_name)
        book = Book.all_objects.filter(
            primary_author=author, title_slug=steps["book"]["title_slug"]
        ).first()
        if book and book.status == BookStatus.REVIEWED:
            messages.error(
                self.request,
                f"“{book.title}” already has a published review — edit that instead.",
            )
            return redirect(f"/b/{book.slug}/")
        new_tags = steps["book"].pop("new_tags")
        tags = list(steps["book"].pop("tags")) or []
        if new_tags:
            for tag in new_tags:
                category, name = tag.split(":", maxsplit=1)
                tags.append(Tag.objects.create(name_slug=name, category=category))
        review_data = steps["review"]
        dates_read = review_data.pop("dates_read")
        did_not_finish = review_data.pop("did_not_finish")
        if book:
            # The wizard picked up a queued (to-read or to-review) book;
            # update it in place instead of hitting the unique slug constraint.
            # Blank wizard fields keep the queued values -- the wizard can't
            # blank an existing field (the book edit form can).
            for field, value in (steps["book"] | review_data).items():
                if value is not None and value != "":
                    setattr(book, field, value)
            book.status = BookStatus.REVIEWED
            book.save()
        else:
            book = Book.objects.create(
                **steps["book"],
                **review_data,
                primary_author=author,
                status=BookStatus.REVIEWED,
            )
        book.tags.set(tags)
        # A queued book already has Read rows (from the review queue form);
        # only create reads for dates it doesn't have yet.
        book.sync_reads(dates_read, did_not_finish=did_not_finish)
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
            return ReviewEditForm(self.request.POST, instance=self.book)
        return ReviewEditForm(instance=self.book)

    def form_invalid(self, form):
        messages.error(self.request, form.errors)
        return super().form_invalid(form)

    def form_valid(self, form):
        if not self.review_form.is_valid():
            messages.error(self.request, self.review_form.errors)
            raise ValueError(self.review_form.errors)
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


class PoemPrivateList(LoginRequiredMixin, ActiveTemplateMixin, ListView):
    template_name = "private/poem_list.html"
    model = Poem
    context_object_name = "poems"
    active = "poems"


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


class ToReviewCreate(LoginRequiredMixin, FormView):
    form_class = BookToReviewForm
    template_name = "private/toreview_edit.html"

    def form_valid(self, form):
        form.save()
        return redirect("/b/toreview/new")


class ToReviewList(LoginRequiredMixin, ListView):
    template_name = "private/toreview_list.html"
    context_object_name = "books"

    def get_queryset(self):
        return Book.all_objects.needs_review()


class ToReviewEdit(LoginRequiredMixin, FormView):
    form_class = BookToReviewEditForm
    template_name = "private/toreview_edit.html"

    @context
    @cached_property
    def book(self):
        return get_object_or_404(
            Book.all_objects.filter(status=BookStatus.TO_REVIEW), pk=self.kwargs["pk"]
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.book
        return kwargs

    def form_valid(self, form):
        form.save()
        return redirect("/b/toreview/")


class ToReviewDelete(LoginRequiredMixin, DetailView):
    def get_queryset(self):
        return Book.all_objects.filter(status=BookStatus.TO_REVIEW)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return redirect("/b/toreview")


@login_required
@require_POST
def to_review_dismiss(request, pk):
    """Dismiss a queued reread: the published review still stands, so stamp
    it as current instead of editing or deleting anything. Only published
    books can be dismissed -- unreviewed queue entries need a review."""
    book = get_object_or_404(Book.all_objects.filter(status=BookStatus.REVIEWED), pk=pk)
    book.mark_review_current()
    return redirect("/b/toreview/")


class ApiTokenList(LoginRequiredMixin, CreateView):
    """List, create and revoke API tokens. Token values are displayed in
    full: this is a single-user personal app, and clients like KOReader need
    the value re-entered from this page."""

    template_name = "private/token_list.html"
    form_class = ApiTokenForm

    @context
    def tokens(self):
        return ApiToken.objects.order_by("created")

    @context
    def created_token(self):
        """The token created by the just-submitted form, highlighted so its
        value can be copied straight away."""
        try:
            return ApiToken.objects.get(pk=self.request.GET.get("created"))
        except (ApiToken.DoesNotExist, ValueError):
            return None

    def form_valid(self, form):
        form.instance.user = self.request.user
        self.object = form.save()
        return redirect(f"/b/tokens/?created={self.object.pk}")


@login_required
@require_POST
def api_token_delete(request, pk):
    token = get_object_or_404(ApiToken, pk=pk)
    token.delete()
    return redirect("/b/tokens/")


@login_required
@require_POST
def trigger_deploy(request):
    flag_file = django_settings.DEPLOY_FLAG_FILE
    if not flag_file:
        return JsonResponse({"error": "Deploy not configured"}, status=400)

    Path(flag_file).touch()
    logger.info("Deploy flag set: %s", flag_file)
    return JsonResponse({"status": "deploying"})


def healthz(request):
    return JsonResponse({"status": "ok"})
