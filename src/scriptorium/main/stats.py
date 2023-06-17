import datetime as dt
import statistics
from collections import Counter, defaultdict

import networkx as nx
import pygal
from django.db.models import Avg, Q, Sum
from django.utils.timezone import now

from .models import Book, Review, Tag


def get_all_years():
    first = 1998
    current = now().year
    return list(range(current, first - 1, -1))


def xml_element(name, content, **kwargs):
    attribs = " ".join(
        f'{key.strip("_").replace("_", "-")}="{value}"' for key, value in kwargs.items()
    ).strip()
    attribs = f" {attribs}" if attribs else ""
    content = content or ""
    return f"<{name}{attribs}>{content}</{name}>"


def generate_svg(
    data, key, max_month, max_year, primary_color, secondary_color, offset
):
    current_year = dt.datetime.now().year
    fallback_color = "#ebedf0"
    content = ""
    year_width = 45
    rect_height = 15
    gap = 3
    block_width = rect_height + gap
    stats_width = 6 * block_width
    total_width = (block_width * 12) + year_width * 3 + stats_width
    total_height = block_width * len(data)
    for row, year in enumerate(data):
        year_content = (
            xml_element(
                "text",
                year["year"],
                x=year_width - gap * 2,
                y=row * 18 + 13,
                width=year_width,
                text_anchor="end",
            )
            + "\n"
        )
        for column, month in enumerate(year["months"]):
            total = month.get(f"total_{key}")
            title = xml_element("title", f"{month['date']}: {total}")
            if total:
                color = primary_color.format((total + offset) / max_month)
            elif year["year"] == current_year:
                continue
            else:
                color = fallback_color
            rect = xml_element(
                "rect",
                title,
                width=rect_height,
                height=rect_height,
                x=column * block_width + year_width,
                y=row * block_width,
                fill=color,
                _class="month",
            )
            year_content += (
                xml_element("a", rect, href=f"/reviews/{year['year']}/#{month['date']}")
                + "\n"
            )

        total = year.get(f"total_{key}")
        title = xml_element("title", f"{year['year']}: {total}")
        rect_width = total * stats_width / max_year
        rect = xml_element(
            "rect",
            title,
            width=rect_width,
            height=rect_height,
            x=12 * block_width + year_width,
            y=row * block_width,
            fill=secondary_color.format(0.42),
            _class="total",
        )
        content += year_content + rect + "\n"
        content += (
            xml_element(
                "text",
                total,
                x=12.5 * block_width + year_width + rect_width,
                y=row * 18 + 13,
                width=year_width * 2,
                fill="#97989a",
            )
            + "\n"
        )

    return xml_element(
        "svg", content, style=f"width: {total_width}px; height: {total_height}px"
    )


def get_stats_grid():
    stats = {}
    time_lookup = defaultdict(list)
    for review in Review.objects.all().select_related("book"):
        for timestamp in review.dates_read_list:
            key = timestamp.strftime("%Y-%m")
            time_lookup[key].append(review)

    most_monthly_books = 0
    most_monthly_pages = 0
    most_yearly_books = 0
    most_yearly_pages = 0
    numbers = []
    for year in get_all_years():
        total_pages = 0
        total_books = 0
        months = []
        for month in range(12):
            written_month = f"{month + 1:02}"
            written_date = f"{year}-{written_month}"
            reviews = time_lookup[written_date]
            book_count = len(reviews)
            page_count = sum(int(review.book.pages or 0) for review in reviews)
            total_pages += page_count
            total_books += book_count
            most_monthly_books = max(most_monthly_books, book_count)
            most_monthly_pages = max(most_monthly_pages, page_count)
            months.append(
                {
                    "month": written_month,
                    "date": written_date,
                    "total_books": book_count,
                    "total_pages": page_count,
                }
            )
        most_yearly_books = max(most_yearly_books, total_books)
        most_yearly_pages = max(most_yearly_pages, total_pages)
        numbers.append(
            {
                "year": year,
                "months": months,
                "total_pages": total_pages,
                "total_books": total_books,
            }
        )

    stats["pages"] = generate_svg(
        numbers,
        "pages",
        max_month=most_monthly_pages,
        max_year=most_yearly_pages,
        primary_color="rgba(0, 113, 113, {})",
        secondary_color="rgba(153, 0, 0, {})",
        offset=1000,
    )
    stats["books"] = generate_svg(
        numbers,
        "books",
        max_month=most_monthly_books,
        max_year=most_yearly_books,
        primary_color="rgba(153, 0, 0, {})",
        secondary_color="rgba(0, 113, 113, {})",
        offset=1,
    )
    return stats
    # stats["ratings"] = generate_bar_chart()  # TODO
    # rating per decade
    # rating per category
    # publication year per decade
    # books by page number
    # books per author


def median_year(reviews):
    return statistics.median(
        reviews.filter(book__publication_year__isnull=False).values_list(
            "book__publication_year", flat=True
        )
    )


def median_length(reviews):
    return statistics.median(
        reviews.filter(book__pages__isnull=False).values_list("book__pages", flat=True)
    )


def average_rating(reviews):
    return round(reviews.aggregate(Avg("rating"))["rating__avg"], 1)


def count_pages(reviews):
    return reviews.aggregate(Sum("book__pages"))["book__pages__sum"]


def get_tag_count(reviews, tag_name):
    category, name_slug = tag_name.split(":", maxsplit=1)
    return reviews.filter(
        book__tags__in=[Tag.objects.get(category=category, name_slug=name_slug)]
    ).count()


def get_stats_table():
    reviews = Review.objects.all()
    review_count = reviews.count()
    percent_female = round(
        get_tag_count(reviews, "author:gender:female") * 100 / review_count, 1
    )
    percent_male = round(
        get_tag_count(reviews, "author:gender:male") * 100 / review_count, 1
    )

    return [
        ("Total books", len(reviews)),
        ("Total pages", count_pages(reviews)),
        (
            "Books without review",
            reviews.filter(Q(text__isnull=True) | Q(text="")).count(),
        ),
        (
            "Books per week",
            round(
                review_count
                / ((dt.datetime.now().date() - dt.date(1998, 1, 1)).days / 7),
                2,
            ),
        ),
        ("Median publication year", median_year(reviews)),
        ("Median length", median_length(reviews)),  # TODO median_length(plans)),
        ("Average rating", average_rating(reviews)),
        ("Percent female/male authors", f"{percent_female}% / {percent_male}%"),
    ]


def get_year_stats(year, extra_years=True):
    reviews = Review.objects.filter(dates_read__contains=year).select_related("book")
    stats = {}
    total_books = len(reviews)
    stats["total_books"] = total_books
    stats["total_pages"] = count_pages(reviews)
    stats["average_pages"] = round(stats["total_pages"] / total_books, 1)
    stats["average_rating"] = average_rating(reviews)
    page_reviews = reviews.order_by("book__pages")
    stats["shortest_book"] = page_reviews.first().book
    stats["longest_book"] = page_reviews.last().book
    word_reviews = sorted(reviews, key=lambda r: r.word_count)
    stats["shortest_review"] = word_reviews[0].book
    stats["longest_review"] = word_reviews[-1].book
    stats["average_review"] = round(
        sum(review.word_count for review in reviews) / total_books, 1
    )
    stats["median_year"] = median_year(reviews)
    stats["median_length"] = median_length(reviews)
    stats["all_time"] = dict(get_stats_table())
    if extra_years:
        stats["previous"] = get_year_stats(year - 1, extra_years=False)
        if Review.objects.filter(dates_read__contains=year + 1).exists():
            stats["next"] = get_year_stats(year + 1, extra_years=False)
        else:
            stats["next"] = None
    stats["gender"] = {
        "male": get_tag_count(reviews, "author:gender:male"),
        "female": get_tag_count(reviews, "author:gender:female"),
    }
    reviews = sorted(reviews, key=lambda x: x.date_read_lookup[year], reverse=True)
    stats["first_book"] = reviews[-1].book
    stats["last_book"] = reviews[0].book
    month_counter = Counter([r.date_read_lookup[year].strftime("%B") for r in reviews])
    stats["busiest_month"] = month_counter.most_common()[0]
    return stats


def get_graph():
    graph = nx.Graph()
    for book in Book.objects.all().prefetch_related(
        "related_books", "related_books__destination"
    ):
        other = book.related_books.all()
        if not other:
            continue
        graph.add_node(book.slug)
        for related in other:
            graph.add_node(related.destination.slug)
            graph.add_edge(book.slug, related.destination.slug)
    return graph


def get_nodes(graph=None):
    graph = graph or get_graph()
    nodes = []
    book_lookup = {
        book.slug: book
        for book in Book.objects.all()
        .select_related("primary_author", "review")
        .prefetch_related("additional_authors")
    }
    for node in graph.nodes:
        try:
            book = book_lookup[node]
        except Exception:
            print(f"ERROR! Node {node} not found")
            continue
        nodes.append(
            {
                "id": node,
                "name": book.title,
                "cover": bool(book.cover),
                "author": book.author_string,
                "series": book.series,
                "rating": book.review.rating,
                "color": book.spine_color,
                "connections": len(list(graph.neighbors(node))),
                "search": [
                    term
                    for term in book.title.lower().split()
                    + book.primary_author.name.lower().split()
                    + (book.series or "").lower().split()
                    + [f"tag:{tag}" for tag in book.tags.all() or []]
                    + ([f"rating:{book.review.rating}"] if book.review.rating else [])
                    if term
                ],
            }
        )
    return nodes


def get_edges(graph=None):
    graph = graph or get_graph()
    return [{"source": source, "target": target} for source, target in graph.edges]


def _get_chart(data, y_label, _type="line", **kwargs):
    style = pygal.style.DefaultStyle
    style.colors = [
        "#990000",
        "#007171",
    ]
    style.font_family = "EB Garamond 12"
    style.label_font_size = 18
    style.major_label_font_size = 18
    style.value_font_size = 18
    style.major_value_font_size = 18
    style.tooltip_font_size = 18
    style.title_font_size = 24
    style.background = "transparent"

    config = {
        "interpolate": "cubic",
        "show_legend": False,
        "dot_size": 10,
        "js": ["/static/vendored/pygal-tooltips.min.js"],
        "style": style,
        "x_label_rotation": 40,
    }
    for key, value in kwargs.items():
        config[key] = value
    if _type == "line":
        chart = pygal.Line(**config)
    elif _type == "bar":
        chart = pygal.Bar(**config)
    chart.x_labels = [x for x, _ in data]
    chart.add(y_label, [y for _, y in data])
    return chart


def get_charts():
    rating_over_time = [
        (
            year,
            Review.objects.filter(
                rating__isnull=False, dates_read__contains=year
            ).aggregate(Avg("rating"))["rating__avg"],
        )
        for year in reversed(get_all_years())
    ]

    page_buckets = [0, 50, 100, 150, 200, 250, 300, 350, 400, 500, 750, 1000, 2000]

    rating_over_pages = [
        (
            f"{pages}-{next_pages or '∞'}",
            round(
                Review.objects.filter(
                    rating__isnull=False,
                    book__pages__gte=pages,
                    book__pages__lt=next_pages,
                ).aggregate(Avg("rating"))["rating__avg"],
                1,
            ),
        )
        for pages, next_pages in zip(page_buckets, page_buckets[1:])
    ]
    rating_over_pages.append(
        (
            f"{page_buckets[-1]}+",
            Review.objects.filter(
                rating__isnull=False, book__pages__gte=page_buckets[-2]
            ).aggregate(Avg("rating"))["rating__avg"],
        )
    )

    publication_year_buckets = [
        0,
        1900,
        1925,
        1950,
        1975,
        1985,
        1990,
        1995,
        2000,
        2005,
        2010,
        2015,
        2020,
    ]
    rating_over_publication_year = [
        (
            f"{year}-{(next_year if next_year == 1900 else str(next_year)[2:]) or '∞'}",
            round(
                Review.objects.filter(
                    rating__isnull=False,
                    book__publication_year__gte=year,
                    book__publication_year__lt=next_year,
                ).aggregate(Avg("rating"))["rating__avg"],
                2,
            ),
        )
        for year, next_year in zip(
            publication_year_buckets, publication_year_buckets[1:]
        )
    ]
    rating_over_publication_year.append(
        (
            f"{publication_year_buckets[-1]}+",
            Review.objects.filter(
                rating__isnull=False,
                book__publication_year__gte=publication_year_buckets[-2],
            ).aggregate(Avg("rating"))["rating__avg"],
        )
    )
    books_per_publication_year = [
        (
            f"{year}-{(next_year if next_year == 1900 else str(next_year)[2:]) or '∞'}",
            Review.objects.filter(
                book__publication_year__gte=year, book__publication_year__lt=next_year
            ).count(),
        )
        for year, next_year in zip(
            publication_year_buckets, publication_year_buckets[1:]
        )
    ]

    return [
        {
            "title": "Average rating over time",
            "svg": _get_chart(rating_over_time, "Rating", range=(2.5, 4.5)).render(
                is_unicode=True
            ),
            "comment": "The first books are always the best. Wild oscillations when I read nearly nothing, then a steady decline as I turn into a crotchety old man. (The pandemic didn't help, either).",
        },
        {
            "title": "Average rating per page count",
            "svg": _get_chart(
                rating_over_pages,
                "Rating",
                range=(2.5, 4.5),
            ).render(is_unicode=True),
            "comment": "300 to 400 pages is my happy place, apparently. Expected a much steeper drop-off for the 2000+ books (aka fanfics).",
        },
        {
            "title": "Average rating per publication year",
            "svg": _get_chart(
                rating_over_publication_year,
                "Rating",
                range=(2.5, 4.5),
            ).render(is_unicode=True),
            "comment": "Look, I'm an early 90s kid, what did you expect?",
        },
        {
            "title": "Books per publication year",
            "svg": _get_chart(books_per_publication_year, "Books", _type="bar").render(
                is_unicode=True
            ),
            "comment": "Just as context for the previous chart.",
        },
    ]
