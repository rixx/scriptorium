import datetime as dt

import pytest

from scriptorium.main.models import BookRelation
from scriptorium.main.stats import (
    LineBar,
    _get_chart,
    get_nodes,
    get_stats_grid,
    get_year_stats,
)
from tests.factories import BookFactory, TagFactory, ToReviewFactory, make_reviewed_book

pytestmark = pytest.mark.django_db


@pytest.fixture
def _gender_tags():
    TagFactory(category="author", name="gender:female", name_slug="gender:female")
    TagFactory(category="author", name="gender:male", name_slug="gender:male")


def test_linebar_without_secondary_range_skips_rescale():
    chart = LineBar()

    assert chart.secondary_range is None
    assert not hasattr(chart, "_secondary_min")
    assert not hasattr(chart, "_secondary_max")


def test_linebar_with_secondary_range_enables_rescale():
    chart = LineBar(secondary_range=(5, 215))

    assert chart.secondary_range == (5, 215)
    assert chart._secondary_min == 5
    assert chart._secondary_max == 215


def test_get_stats_grid_counts_unmatched_to_reviews():
    """Unmatched ToReview entries (book is null) contribute to the month
    buckets alongside real reviews, so the grid reflects intent to read even
    when the book hasn't been imported yet."""
    # A real review keeps max_year/max_month non-zero so generate_svg doesn't
    # trip on a divide-by-zero for the totals rect width.
    make_reviewed_book(
        title="Anchor",
        title_slug="anchor",
        pages=250,
        latest_date=dt.date(2024, 3, 1),
        dates_read="2024-03-01",
    )
    ToReviewFactory(date=dt.date(2024, 6, 15), book=None)
    ToReviewFactory(date=dt.date(2024, 6, 20), book=None)

    stats = get_stats_grid()

    # The grid anchors both unmatched entries to the 2024-06 month bucket:
    # book count is 2, pages count is 0 because there is no Book attached.
    assert "2024-06: 2" in stats["books"]
    assert "2024-06: 0" in stats["pages"]
    # The March anchor review still shows up in the books grid.
    assert "2024-03: 1" in stats["books"]


@pytest.mark.usefixtures("_gender_tags")
def test_get_year_stats_recursively_includes_next_year():
    """When year+1 has at least one review, get_year_stats pulls a stripped
    `next` block for it. Previously uncovered because the fixture set only
    had 2023 + 2024 data and queried 2024, so year+1 (2025) never existed."""
    # get_year_stats with extra_years=True recurses into year-1 as well, so
    # 2022 needs at least one review or average_pages hits division-by-zero.
    make_reviewed_book(
        title="Year N-1 book",
        title_slug="year-n-minus-one-book",
        pages=150,
        publication_year=1999,
        rating=3,
        latest_date=dt.date(2022, 5, 1),
        dates_read="2022-05-01",
    )
    make_reviewed_book(
        title="Year N book",
        title_slug="year-n-book",
        pages=200,
        publication_year=2000,
        rating=4,
        latest_date=dt.date(2023, 5, 1),
        dates_read="2023-05-01",
    )
    next_year_book = make_reviewed_book(
        title="Year N+1 book",
        title_slug="year-n-plus-one-book",
        pages=300,
        publication_year=2001,
        rating=5,
        latest_date=dt.date(2024, 5, 1),
        dates_read="2024-05-01",
    )

    stats = get_year_stats(2023, extra_years=True)

    assert stats["next"] is not None
    assert stats["next"]["total_books"] == 1
    assert stats["next"]["last_book"] == next_year_book
    # extra_years=False on the recursive call → no further nesting.
    assert "next" not in stats["next"]


def test_get_nodes_skips_graph_nodes_without_matching_book():
    """A BookRelation can point at a Book that the default (non-draft)
    BookManager filters out. get_nodes must skip those graph nodes instead
    of exploding with KeyError."""
    source = make_reviewed_book(title="Source", title_slug="source")
    # Destination has no Review, so Book.objects.all() (which INNER JOINs
    # review and filters is_draft=False) excludes it from the lookup, while
    # the raw FK access in get_graph still surfaces its slug in the graph.
    orphan = BookFactory(title="Orphan", title_slug="orphan")
    BookRelation.objects.create(source=source, destination=orphan, text="see also")

    # A second, fully-reviewed relation keeps the graph non-empty so we can
    # assert that get_nodes yields exactly the matched book.
    sibling = make_reviewed_book(title="Sibling", title_slug="sibling")
    BookRelation.objects.create(source=source, destination=sibling, text="also")

    nodes = get_nodes()

    node_ids = {node["id"] for node in nodes}
    assert node_ids == {source.slug, sibling.slug}
    assert orphan.slug not in node_ids


@pytest.mark.parametrize("chart_type", ["line", "bar"])
def test_get_chart_renders_simple_types(chart_type):
    """get_charts() only exercises the 'linebar' branch, but _get_chart is a
    general helper that must still render plain line and bar charts — the
    branches covering pygal.Line / pygal.Bar construction live here."""
    data = [("2022", 3), ("2023", 4), ("2024", 5)]

    svg = _get_chart(data, _type=chart_type)

    assert svg.startswith("<?xml")
    assert "<svg" in svg
    # x_labels come through into the rendered output.
    assert "2024" in svg
