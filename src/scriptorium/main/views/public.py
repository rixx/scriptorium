import random
import re

from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django_context_decorator import context

from scriptorium.main.utils import parse_border_number

HEX_COLOR = re.compile(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}")


def border_image(request):
    number = parse_border_number(request.GET.get("border"))
    border_color = request.GET.get("color", "")
    if not HEX_COLOR.fullmatch(border_color):
        border_color = "990000"
    if not number:
        number = random.randint(1, settings.MAX_BORDER)  # noqa: S311

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
