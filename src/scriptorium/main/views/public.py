import random

from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django_context_decorator import context


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
