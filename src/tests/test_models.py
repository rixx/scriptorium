import datetime as dt
import io
import re
from pathlib import Path

import pytest
import requests
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image

from scriptorium.main.models import Author, Book, BookStatus, Spine, Tag, Thumbnail
from tests.factories import (
    AuthorFactory,
    BookFactory,
    PoemFactory,
    QuoteFactory,
    ReadFactory,
    SeriesFactory,
    TagFactory,
    make_reviewed_book,
)

pytestmark = pytest.mark.django_db


# --- Author -----------------------------------------------------------------


def test_author_str_returns_name():
    author = AuthorFactory(name="Jorge Luis Borges")

    assert str(author) == "Jorge Luis Borges"


def test_author_all_books_includes_primary_and_additional_authorship():
    primary = AuthorFactory()
    co_author = AuthorFactory()

    solo = make_reviewed_book(primary_author=primary)
    collab = make_reviewed_book(primary_author=primary)
    collab.additional_authors.add(co_author)
    unrelated = make_reviewed_book()

    assert set(primary.all_books()) == {solo, collab}
    assert set(co_author.all_books()) == {collab}
    assert unrelated not in primary.all_books()


def test_author_get_or_create_by_name_reuses_author_for_slug_variant():
    existing = AuthorFactory(name="Ursula K. Le Guin", name_slug="ursula-k-le-guin")

    author, created = Author.objects.get_or_create_by_name("ursula k. le guin")

    assert created is False
    assert author == existing
    assert author.name == "Ursula K. Le Guin"
    assert list(Author.objects.all()) == [existing]


def test_author_get_or_create_by_name_creates_author_with_slug():
    author, created = Author.objects.get_or_create_by_name("N. K. Jemisin")

    assert created is True
    assert author.name == "N. K. Jemisin"
    assert author.name_slug == "n-k-jemisin"


def test_author_tag_author_adds_tag_to_every_book(tag):
    author = AuthorFactory()
    book_one = make_reviewed_book(primary_author=author)
    book_two = make_reviewed_book(primary_author=author)

    author.tag_author(tag)

    assert set(book_one.tags.all()) == {tag}
    assert set(book_two.tags.all()) == {tag}


# --- Tag --------------------------------------------------------------------


def test_tag_save_falls_back_to_slug_when_name_missing():
    tag = Tag.objects.create(category="genre", name_slug="mystery")

    assert tag.name == "mystery"


def test_tag_str_includes_category_and_name():
    tag = TagFactory(category="genre", name="Horror", name_slug="horror")

    assert str(tag) == "genre:Horror"


# --- Series -----------------------------------------------------------------


def test_series_books_returns_published_books_in_series():
    series = SeriesFactory(name="Hainish Cycle", name_slug="hainish-cycle")
    book_one = make_reviewed_book(series=series)
    book_two = make_reviewed_book(series=series)
    # The reverse manager filters like the default Book manager does.
    queued = BookFactory(series=series, status=BookStatus.TO_READ)

    assert set(series.books.all()) == {book_one, book_two}
    assert set(Book.all_objects.filter(series=series)) == {book_one, book_two, queued}


# --- Book manager -----------------------------------------------------------


def test_book_manager_only_shows_reviewed_books_by_default():
    published = make_reviewed_book()
    queued = BookFactory(status=BookStatus.TO_READ)
    awaiting_review = BookFactory(status=BookStatus.TO_REVIEW)

    assert list(Book.objects.all()) == [published]
    assert set(Book.all_objects.all()) == {published, queued, awaiting_review}


def test_book_manager_get_by_slug_returns_the_book():
    author = AuthorFactory(name_slug="octavia-butler")
    book = make_reviewed_book(primary_author=author, title_slug="kindred")

    assert Book.objects.get_by_slug("octavia-butler/kindred") == book


# --- Book -------------------------------------------------------------------


def test_book_slug_combines_author_and_title():
    author = AuthorFactory(name_slug="le-guin")
    book = BookFactory(primary_author=author, title_slug="earthsea")

    assert book.slug == "le-guin/earthsea"


def test_book_author_string_single_author():
    author = AuthorFactory(name="Ada Palmer")
    book = BookFactory(primary_author=author)

    assert book.author_string == "Ada Palmer"


def test_book_author_string_two_authors_uses_ampersand():
    primary = AuthorFactory(name="Terry Pratchett")
    co = AuthorFactory(name="Neil Gaiman")
    book = BookFactory(primary_author=primary)
    book.additional_authors.add(co)

    assert book.author_string == "Terry Pratchett & Neil Gaiman"


def test_book_author_string_three_authors_uses_comma_and_ampersand():
    primary = AuthorFactory(name="A")
    second = AuthorFactory(name="B")
    third = AuthorFactory(name="C")
    book = BookFactory(primary_author=primary)
    book.additional_authors.add(second, third)

    assert book.author_string == "A, B & C"


def test_book_isbn_prefers_isbn13():
    book = BookFactory(isbn10="0000000001", isbn13="9780000000002")

    assert book.isbn == "9780000000002"


def test_book_isbn_falls_back_to_isbn10():
    book = BookFactory(isbn10="0000000001", isbn13=None)

    assert book.isbn == "0000000001"


def test_book_tags_by_category_groups_ordered_tags():
    book = make_reviewed_book()
    awards_tag = TagFactory(category="awards", name_slug="hugo")
    genre_tag = TagFactory(category="genre", name_slug="sci-fi")
    theme_tag = TagFactory(category="themes", name_slug="space")
    book.tags.add(awards_tag, genre_tag, theme_tag)

    grouped = book.tags_by_category

    assert grouped == {
        "awards": [awards_tag],
        "genre": [genre_tag],
        "themes": [theme_tag],
    }


def test_book_quotes_by_language_groups_adjacent_quotes():
    book = make_reviewed_book()
    en_one = QuoteFactory(source_book=book, language="en", text="First", order=1)
    en_two = QuoteFactory(source_book=book, language="en", text="Second", order=2)
    de_one = QuoteFactory(source_book=book, language="de", text="Drittens", order=3)

    grouped = book.quotes_by_language

    assert set(grouped.keys()) == {"en", "de"}
    assert grouped["en"] == [en_one, en_two]
    assert grouped["de"] == [de_one]


# --- Book review data ---------------------------------------------------------


def test_book_save_sets_feed_date_on_first_publication():
    book = BookFactory(status=BookStatus.TO_REVIEW)

    book.status = BookStatus.REVIEWED
    book.text = "A review."
    book.save()

    assert book.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_book_save_sets_feed_date_for_book_created_as_reviewed():
    book = BookFactory(reviewed=True)

    assert book.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_book_save_with_update_fields_persists_feed_date():
    book = BookFactory(status=BookStatus.TO_REVIEW)

    book.status = BookStatus.REVIEWED
    book.save(update_fields=["status"])

    book.refresh_from_db()
    assert book.status == BookStatus.REVIEWED
    assert book.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_book_save_keeps_feed_date_when_already_published():
    book = make_reviewed_book()
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2024, 1, 1))
    book.refresh_from_db()

    book.tldr = "edited"
    book.save()

    book.refresh_from_db()
    assert book.feed_date == dt.date(2024, 1, 1)


def test_book_save_keeps_feed_date_for_unpublished_books():
    book = BookFactory(status=BookStatus.TO_READ)

    book.status = BookStatus.TO_REVIEW
    book.save()

    assert book.feed_date is None


def test_book_dates_read_list_sorts_reads_chronologically():
    book = make_reviewed_book(
        reads=[dt.date(2024, 5, 1), dt.date(2020, 1, 2), dt.date(2022, 7, 10)]
    )

    assert book.dates_read_list == [
        dt.date(2020, 1, 2),
        dt.date(2022, 7, 10),
        dt.date(2024, 5, 1),
    ]
    assert book.latest_date == dt.date(2024, 5, 1)


def test_book_latest_date_is_none_without_reads():
    book = BookFactory()

    assert book.latest_date is None


def test_book_date_read_lookup_keyed_by_year():
    book = make_reviewed_book(reads=[dt.date(2020, 1, 2), dt.date(2024, 5, 1)])

    assert book.date_read_lookup == {
        2020: dt.date(2020, 1, 2),
        2024: dt.date(2024, 5, 1),
    }


def test_book_did_not_finish_only_when_every_read_is_unfinished():
    abandoned = make_reviewed_book(reads=[])
    ReadFactory(book=abandoned, did_not_finish=True)
    finished_on_reread = make_reviewed_book(reads=[])
    ReadFactory(book=finished_on_reread, did_not_finish=True)
    ReadFactory(book=finished_on_reread, did_not_finish=False)
    no_reads = make_reviewed_book(reads=[])

    assert abandoned.did_not_finish is True
    assert finished_on_reread.did_not_finish is False
    assert no_reads.did_not_finish is False


def test_book_sync_reads_creates_only_missing_dates():
    book = BookFactory()
    ReadFactory(book=book, finished_on=dt.date(2024, 1, 1), notes="Kept.")

    book.sync_reads([dt.date(2024, 1, 1), dt.date(2024, 2, 2)], source="manual")

    reads = book.reads.order_by("finished_on")
    assert [(read.finished_on, read.notes, read.source) for read in reads] == [
        (dt.date(2024, 1, 1), "Kept.", None),
        (dt.date(2024, 2, 2), None, "manual"),
    ]


def test_book_sync_reads_remove_extra_deletes_stale_reads():
    book = BookFactory()
    kept = ReadFactory(book=book, finished_on=dt.date(2024, 1, 1))
    ReadFactory(book=book, finished_on=dt.date(2023, 1, 1))
    ReadFactory(book=book, finished_on=dt.date(2022, 1, 1))

    book.sync_reads([dt.date(2024, 1, 1)], remove_extra=True)

    assert list(book.reads.all()) == [kept]


def test_book_sync_reads_single_date_swap_updates_read_in_place():
    book = BookFactory()
    read = ReadFactory(book=book, finished_on=dt.date(2024, 1, 1), notes="Notes stay.")

    book.sync_reads([dt.date(2024, 1, 5)], remove_extra=True)

    read.refresh_from_db()
    assert read.finished_on == dt.date(2024, 1, 5)
    assert read.notes == "Notes stay."
    assert list(book.reads.all()) == [read]


# --- Read -------------------------------------------------------------------


def test_read_save_bumps_feed_date_for_new_latest_read():
    book = make_reviewed_book(latest_date=dt.date(2020, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2020, 1, 1))

    ReadFactory(book=book, finished_on=dt.date(2024, 6, 1))

    book.refresh_from_db()
    assert book.latest_date == dt.date(2024, 6, 1)
    assert book.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_read_save_backfilling_older_read_does_not_bump():
    book = make_reviewed_book(latest_date=dt.date(2024, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2024, 1, 1))

    ReadFactory(book=book, finished_on=dt.date(2019, 5, 5))

    book.refresh_from_db()
    assert book.latest_date == dt.date(2024, 1, 1)
    assert book.feed_date == dt.date(2024, 1, 1)


def test_read_save_does_not_bump_unpublished_books():
    book = BookFactory(status=BookStatus.TO_REVIEW)

    ReadFactory(book=book, finished_on=dt.date(2024, 6, 1))

    book.refresh_from_db()
    assert book.feed_date is None


def test_read_save_updating_existing_read_does_not_bump():
    book = make_reviewed_book(latest_date=dt.date(2024, 1, 1))
    Book.all_objects.filter(pk=book.pk).update(feed_date=dt.date(2024, 1, 1))
    read = book.reads.get()

    read.notes = "reread for book club"
    read.save()

    book.refresh_from_db()
    assert book.feed_date == dt.date(2024, 1, 1)
    assert book.reads.get().notes == "reread for book club"


def test_book_word_count_counts_whitespace_separated_tokens():
    book = make_reviewed_book(text="one two three four five")

    assert book.word_count == 5


def test_book_word_count_is_zero_without_text():
    book = BookFactory()

    assert book.word_count == 0


def test_book_short_first_paragraph_stops_at_blank_line():
    book = make_reviewed_book(text="first paragraph\n\nsecond paragraph")

    assert book.short_first_paragraph == "first paragraph"


def test_book_short_first_paragraph_empty_without_text():
    book = BookFactory()

    assert book.short_first_paragraph == ""


def test_book_feed_uuid_is_stable_and_unique():
    book_one = make_reviewed_book(title="Alpha")
    book_two = make_reviewed_book(title="Beta")

    assert book_one.feed_uuid == book_one.feed_uuid
    assert book_one.feed_uuid != book_two.feed_uuid


def test_book_feed_uuid_falls_back_to_latest_read_date():
    fallback = make_reviewed_book(title="Alpha", latest_date=dt.date(2024, 2, 2))
    Book.all_objects.filter(pk=fallback.pk).update(feed_date=None)
    explicit = make_reviewed_book(title="Alpha", reads=[])
    Book.all_objects.filter(pk=explicit.pk).update(feed_date=dt.date(2024, 2, 2))

    fallback = Book.objects.get(pk=fallback.pk)
    explicit = Book.objects.get(pk=explicit.pk)

    # The books only differ in where the feed date comes from -- equal uuids
    # prove that the fallback derives the uuid from the latest read date.
    assert fallback.feed_uuid == explicit.feed_uuid


def test_book_read_in_year_matches_once_and_aggregates_cleanly():
    reread = make_reviewed_book(
        pages=100, reads=[dt.date(2023, 2, 1), dt.date(2023, 8, 1)]
    )
    make_reviewed_book(pages=100, latest_date=dt.date(2022, 1, 1))

    books = Book.objects.read_in_year(2023)

    assert list(books) == [reread]
    # two reads in the same year must not double the aggregates
    assert books.aggregate(pages_sum=models.Sum("pages"))["pages_sum"] == 100


# --- Quote ------------------------------------------------------------------


def test_quote_short_string_attributes_to_book_when_present(reviewed_book):
    quote = QuoteFactory(source_book=reviewed_book, text="A short quote.")

    assert quote.short_string == f"“A short quote.” — {reviewed_book.title}"


def test_quote_short_string_attributes_to_author_when_no_book():
    author = AuthorFactory(name="Rumi")
    quote = QuoteFactory(source_author=author, text="A very pithy saying.")

    assert quote.short_string == "“A very pithy saying.” — Rumi"


def test_quote_short_string_shortens_long_text():
    text = "word " * 60
    quote = QuoteFactory(text=text.strip())

    assert quote.short_string.endswith("…”")


# --- Poem -------------------------------------------------------------------


def test_poem_line_count_ignores_blank_lines():
    poem = PoemFactory(text="one\n\ntwo\n   \nthree\n")

    assert poem.line_count == 3


def test_poem_get_absolute_url_with_book():
    book = make_reviewed_book(
        primary_author=AuthorFactory(name_slug="rilke"), title_slug="neue-gedichte"
    )
    poem = PoemFactory(book=book, author=None, slug="der-panther")

    assert poem.get_absolute_url() == "/rilke/neue-gedichte/poems/der-panther/"
    assert poem.get_absolute_url(private=True) == (
        "/b/rilke/neue-gedichte/poems/der-panther/"
    )


def test_poem_get_absolute_url_with_author_only():
    author = AuthorFactory(name_slug="sappho")
    poem = PoemFactory(author=author, slug="fragment-31")

    assert poem.get_absolute_url() == "/sappho/poems/fragment-31/"


def test_poem_get_absolute_url_falls_back_to_url_slug():
    poem = PoemFactory(author=None, url_slug="anonymous", slug="epitaph")

    assert poem.get_absolute_url() == "/poems/anonymous/epitaph/"


# --- Spine ------------------------------------------------------------------


def test_spine_clamps_width_to_minimum():
    book = make_reviewed_book(pages=1, dimensions=None)

    spine = Spine(book)

    assert 12 <= spine.width <= 32


def test_spine_derives_width_from_page_count():
    thin = make_reviewed_book(pages=100, dimensions=None)
    thick = make_reviewed_book(pages=1000, dimensions=None)

    assert Spine(thin).width <= Spine(thick).width


def test_spine_uses_dimensions_when_provided():
    book = make_reviewed_book(pages=300, dimensions={"height": 20, "thickness": 3})

    spine = Spine(book)

    assert spine.height == 80  # normalize_height(20) == clamp(80) == 80
    assert spine.width == 12


def test_spine_starred_matches_five_star_rating():
    five_star = make_reviewed_book(rating=5)
    four_star = make_reviewed_book(rating=4)

    assert Spine(five_star).starred is True
    assert Spine(four_star).starred is False


# --- Book covers, thumbnails, spine colors ---------------------------------


def _png_bytes(size=(300, 400), color=(120, 50, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def test_book_save_downloads_cover_when_source_set(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    content = _png_bytes()
    monkeypatch.setattr(
        "scriptorium.main.models.requests.get",
        lambda url, timeout=5: _FakeResponse(content),  # noqa: ARG005
    )

    book = BookFactory(cover_source="https://example.com/cover.jpg")
    book.refresh_from_db()

    assert book.cover_source is None
    assert book.cover.name
    with book.cover.open("rb") as fp:
        assert fp.read() == content


def test_book_download_cover_noop_when_source_missing(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory(cover_source=None)

    book.download_cover()

    assert not book.cover


def test_book_download_cover_swallows_request_errors(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)

    def boom(url, timeout=5):  # noqa: ARG001
        raise requests.ConnectionError("nope")

    monkeypatch.setattr("scriptorium.main.models.requests.get", boom)

    book = BookFactory(cover_source="https://example.com/cover.jpg")
    book.refresh_from_db()

    assert not book.cover
    assert book.cover_source == "https://example.com/cover.jpg"


def test_book_download_cover_replaces_existing_cover(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    replacement = _png_bytes(color=(250, 250, 250))
    book = BookFactory()
    book.cover.save("old.png", ContentFile(_png_bytes(color=(10, 10, 10))), save=True)
    old_path = book.cover.path

    monkeypatch.setattr(
        "scriptorium.main.models.requests.get",
        lambda url, timeout=5: _FakeResponse(replacement),  # noqa: ARG005
    )
    book.cover_source = "https://example.com/new.jpg"
    book.download_cover()
    book.refresh_from_db()

    assert book.cover.name
    with book.cover.open("rb") as fp:
        assert fp.read() == replacement
    assert not Path(old_path).exists()
    assert book.cover_source is None


def test_book_spine_cached_property_returns_spine_instance():
    book = make_reviewed_book(pages=200, dimensions=None)

    first = book.spine
    second = book.spine

    assert isinstance(first, Spine)
    assert first is second
    assert first.book is book


def test_book_update_thumbnail_noop_without_cover():
    book = BookFactory()

    book.update_thumbnail()

    assert list(Thumbnail.objects.filter(book=book)) == []


def test_book_update_thumbnail_resizes_large_cover(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory()
    book.cover.save("cover.png", ContentFile(_png_bytes((500, 600))), save=True)

    book.update_thumbnail()

    thumb = Thumbnail.objects.get(book=book, size="thumbnail")
    with Image.open(thumb.thumb.path) as im:
        assert im.width <= 240
        assert im.height <= 240
        assert max(im.size) == 240


def test_book_update_thumbnail_keeps_small_cover_unresized(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory()
    book.cover.save("cover.png", ContentFile(_png_bytes((100, 100))), save=True)

    book.update_thumbnail()

    thumb = Thumbnail.objects.get(book=book, size="thumbnail")
    with Image.open(thumb.thumb.path) as im:
        assert im.size == (100, 100)


def test_book_update_thumbnail_invalidates_cached_thumbnail(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory()
    book.cover.save("cover.png", ContentFile(_png_bytes((300, 400))), save=True)
    Thumbnail.objects.create(book=book, size="thumbnail")
    # prime the cached_property so update_thumbnail must delete it
    _ = book.cover_thumbnail

    book.update_thumbnail()

    assert Thumbnail.objects.filter(book=book, size="thumbnail").count() == 2


def test_book_update_spine_color_noop_without_cover():
    book = BookFactory(spine_color=None)

    book.update_spine_color()

    assert book.spine_color is None


def test_book_update_spine_color_sets_hex_from_cover(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory(spine_color=None)
    book.cover.save(
        "cover.png", ContentFile(_png_bytes((100, 100), color=(220, 30, 30))), save=True
    )

    book.update_spine_color()

    assert re.fullmatch(r"#[0-9a-f]{6}", book.spine_color)


def test_book_update_ui_color_noop_without_cover():
    book = BookFactory(ui_color=None)

    book.update_ui_color()

    assert book.ui_color is None


def test_book_update_ui_color_sets_hex_from_cover(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory(ui_color=None)
    book.cover.save(
        "cover.png", ContentFile(_png_bytes((100, 100), color=(220, 30, 30))), save=True
    )

    book.update_ui_color()

    assert re.fullmatch(r"#[0-9a-f]{6}", book.ui_color)


def test_spine_get_margin_zero_when_not_tilted():
    book = make_reviewed_book(pages=200, dimensions={"height": 20, "thickness": 3})

    assert Spine(book).get_margin(0) == pytest.approx(0, abs=1e-9)


def test_spine_get_margin_symmetric_in_tilt_direction():
    book = make_reviewed_book(pages=200, dimensions={"height": 20, "thickness": 3})
    spine = Spine(book)

    assert spine.get_margin(30) == spine.get_margin(-30)
    assert spine.get_margin(30) > 0


def test_thumbnail_delete_removes_file_and_row(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    book = BookFactory()
    thumb = Thumbnail.objects.create(book=book, size="thumbnail")
    thumb.thumb.save("t.jpg", ContentFile(b"fake bytes"), save=True)
    file_path = thumb.thumb.path
    assert Path(file_path).exists()

    thumb.delete()

    assert not Thumbnail.objects.filter(pk=thumb.pk).exists()
    assert not Path(file_path).exists()
