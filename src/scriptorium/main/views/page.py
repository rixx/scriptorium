from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django_context_decorator import context

from scriptorium.main.models import Page


class PageView(TemplateView):
    template_name = "public/page.html"

    @context
    @cached_property
    def title(self):
        return str(self.page)

    @context
    @cached_property
    def page(self):
        return get_object_or_404(Page, slug=self.kwargs["slug"])
