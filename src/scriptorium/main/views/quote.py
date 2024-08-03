from django.utils.functional import cached_property
from django.views.generic import DetailView
from django_context_decorator import context

from scriptorium.main.models import Quote


class QuoteView(DetailView):
    model = Quote
    template_name = "public/quote.html"
    context_object_name = "quote"

    @context
    @cached_property
    def title(self):
        return self.get_object().short_string
