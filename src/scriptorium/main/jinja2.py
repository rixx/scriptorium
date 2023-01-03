import datetime as dt
import pathlib
from io import StringIO

import markdown
import smartypants
from django.contrib.staticfiles.storage import staticfiles_storage
from jinja2 import Environment, FileSystemLoader, Markup, select_autoescape
from markdown.extensions.smarty import SmartyExtension
from markdown.extensions.toc import TocExtension


def unmark_element(element, stream=None):
    if stream is None:
        stream = StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


# patching Markdown
markdown.Markdown.output_formats["plain"] = unmark_element
plain_markdown = markdown.Markdown(output_format="plain")
plain_markdown.stripTopLevelTags = False
md = markdown.Markdown(
    extensions=[SmartyExtension(), TocExtension(marker="", baselevel=2)]
)
md_quotes = markdown.Markdown(extensions=[SmartyExtension(), "nl2br"])


def render_markdown(text):
    md.reset()
    return md.convert(text)


def render_quotes(text):
    md_quotes.reset()
    return md_quotes.convert(text)


def render_toc(text):
    md.reset()
    md.convert(text)
    return md.toc


def strip_markdown(text):
    return plain_markdown.convert(text)


def render_date(date_value, link=True):
    if isinstance(date_value, dt.date):
        date_value = date_value.strftime("%Y-%m-%d")
    if not date_value:
        return
    if not link:
        return date_value
    year, rest = date_value.split("-", maxsplit=1)
    return Markup(f'<a href="/reviews/{year}">{year}</a>-{rest}')


def render_authors(authors):
    authors = [
        f'<a href="/{author.name_slug}/">{author.name}</a>' for author in authors
    ]
    if len(authors) == 1:
        return Markup(authors[0])
    result = ", ".join(authors[:-1])
    return Markup(f"{result} & {authors[-1]}")


def environment(**options):
    options["loader"] = FileSystemLoader(pathlib.Path(__file__).parent / "templates")
    options["autoescape"] = select_autoescape(["html", "xml"])

    env = Environment(**options)
    env.globals.update({"static": staticfiles_storage.url})
    env.filters["render_markdown"] = render_markdown
    env.filters["render_quotes"] = render_quotes
    env.filters["render_toc"] = render_toc
    env.filters["strip_markdown"] = strip_markdown
    env.filters["render_date"] = render_date
    env.filters["smartypants"] = smartypants.smartypants
    env.filters["render_authors"] = render_authors
    return env
