import datetime as dt

import pytest

from scriptorium.main.models import Book, Review, Spine, Tag
from tests.factories import (
    AuthorFactory,
    BookFactory,
    PoemFactory,
    QuoteFactory,
    ReviewFactory,
    TagFactory,
    ToReviewFactory,
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


# --- Book manager -----------------------------------------------------------


def test_book_manager_excludes_drafts_by_default():
    published = make_reviewed_book()
    draft_book = BookFactory()
    ReviewFactory(book=draft_book, is_draft=True)

    assert list(Book.objects.all()) == [published]
    assert set(Book.objects.with_drafts()) == {published, draft_book}


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


def test_book_spine_color_darkened_darkens_bright_colors():
    book = BookFactory(spine_color="#ffffff")

    darkened = book.spine_color_darkened

    r, g, b = (int(darkened[i : i + 2], 16) for i in (1, 3, 5))
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    assert brightness <= 100
    assert darkened != "#ffffff"


def test_book_spine_color_darkened_leaves_dark_colors_alone():
    book = BookFactory(spine_color="#102030")

    assert book.spine_color_darkened == "#102030"


def test_book_spine_color_darkened_none_when_unset():
    book = BookFactory(spine_color=None)

    assert book.spine_color_darkened is None


def test_book_quotes_by_language_groups_adjacent_quotes():
    book = make_reviewed_book()
    en_one = QuoteFactory(source_book=book, language="en", text="First", order=1)
    en_two = QuoteFactory(source_book=book, language="en", text="Second", order=2)
    de_one = QuoteFactory(source_book=book, language="de", text="Drittens", order=3)

    grouped = book.quotes_by_language

    assert set(grouped.keys()) == {"en", "de"}
    assert grouped["en"] == [en_one, en_two]
    assert grouped["de"] == [de_one]


# --- Review -----------------------------------------------------------------


def test_review_save_populates_dates_read_from_latest_date():
    book = BookFactory()
    review = Review(book=book, text="x", rating=3, latest_date=dt.date(2024, 5, 1))

    review.save()

    assert review.dates_read == "2024-05-01"


def test_review_save_sets_feed_date_on_creation():
    book = BookFactory()
    review = Review(book=book, text="x", rating=3, latest_date=dt.date(2024, 5, 1))

    review.save()

    assert review.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_review_save_updates_feed_date_on_reread():
    book = BookFactory()
    review = ReviewFactory(
        book=book, latest_date=dt.date(2020, 1, 1), dates_read="2020-01-01"
    )
    Review.objects.filter(pk=review.pk).update(feed_date=dt.date(2020, 1, 1))
    review.refresh_from_db()

    review.latest_date = dt.date(2024, 6, 1)
    review.save()

    assert review.feed_date == dt.datetime.now(tz=dt.UTC).date()


def test_review_save_keeps_feed_date_when_not_a_reread():
    book = BookFactory()
    review = ReviewFactory(
        book=book, latest_date=dt.date(2024, 1, 1), dates_read="2024-01-01"
    )
    stored_feed_date = review.feed_date

    review.tldr = "edited"
    review.save()

    assert review.feed_date == stored_feed_date


def test_review_dates_read_list_parses_comma_separated_dates():
    review = ReviewFactory(
        latest_date=dt.date(2024, 5, 1), dates_read="2020-01-02,2022-07-10,2024-05-01"
    )

    assert review.dates_read_list == [
        dt.date(2020, 1, 2),
        dt.date(2022, 7, 10),
        dt.date(2024, 5, 1),
    ]


def test_review_date_read_lookup_keyed_by_year():
    review = ReviewFactory(
        latest_date=dt.date(2024, 5, 1), dates_read="2020-01-02,2024-05-01"
    )

    assert review.date_read_lookup == {
        2020: dt.date(2020, 1, 2),
        2024: dt.date(2024, 5, 1),
    }


def test_review_word_count_counts_whitespace_separated_tokens():
    review = ReviewFactory(text="one two three four five")

    assert review.word_count == 5


def test_review_short_first_paragraph_stops_at_blank_line():
    review = ReviewFactory(text="first paragraph\n\nsecond paragraph")

    assert review.short_first_paragraph == "first paragraph"


def test_review_feed_uuid_is_stable_and_unique():
    book_one = make_reviewed_book(title="Alpha")
    book_two = make_reviewed_book(title="Beta")

    assert book_one.review.feed_uuid == book_one.review.feed_uuid
    assert book_one.review.feed_uuid != book_two.review.feed_uuid


def test_review_manager_excludes_drafts():
    published_book = BookFactory()
    published = ReviewFactory(book=published_book)
    draft_book = BookFactory()
    ReviewFactory(book=draft_book, is_draft=True)

    assert list(Review.objects.all()) == [published]
    assert Review.objects.with_drafts().count() == 2


def test_review_with_dates_read_annotates_count():
    one_read = make_reviewed_book().review
    one_read.dates_read = "2024-01-01"
    one_read.save(update_fields=["dates_read"])

    three_reads = make_reviewed_book().review
    three_reads.dates_read = "2020-01-01,2022-01-01,2024-01-01"
    three_reads.save(update_fields=["dates_read"])

    counts = {r.pk: r.dates_read_count for r in Review.objects.with_dates_read()}
    assert counts[one_read.pk] == 1
    assert counts[three_reads.pk] == 3


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


# --- ToReview ---------------------------------------------------------------


def test_to_review_match_links_book_and_returns_true():
    author = AuthorFactory()
    book = make_reviewed_book(
        primary_author=author,
        title_slug="my-book",
        latest_date=dt.date(2024, 6, 15),
        dates_read="2024-06-15",
    )
    to_review = ToReviewFactory(title="My Book", date=dt.date(2024, 6, 16))

    assert to_review.match() is True
    to_review.refresh_from_db()
    assert to_review.book == book


def test_to_review_match_rejects_when_dates_disagree():
    author = AuthorFactory()
    make_reviewed_book(
        primary_author=author,
        title_slug="my-book",
        latest_date=dt.date(2024, 1, 1),
        dates_read="2024-01-01",
    )
    to_review = ToReviewFactory(title="My Book", date=dt.date(2024, 6, 15))

    assert to_review.match() is False
    to_review.refresh_from_db()
    assert to_review.book is None


def test_to_review_match_returns_false_when_no_book_exists():
    to_review = ToReviewFactory(title="Unknown Title", date=dt.date(2024, 1, 1))

    assert to_review.match() is False
