import datetime as dt
import statistics
from collections import Counter, defaultdict

import networkx as nx
from django.db.models import Q
from django.utils.timezone import now

from .models import Book, Review


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
    for review in Review.objects.all():
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
        Review.objects.all()
        .filter(book__publication_year__isnull=False)
        .values_list("book__publication_year", flat=True)
    )


def median_length(reviews):
    return statistics.median(
        Review.objects.all()
        .filter(book__pages__isnull=False)
        .values_list("book__pages", flat=True)
    )


def get_stats_table():
    reviews = Review.objects.all()
    review_count = reviews.count()
    return [
        ("Total books", len(reviews)),
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
    ]


def get_year_stats(year):
    reviews = Review.objects.filter(dates_read__contains=year)
    stats = {}
    total_books = len(reviews)
    stats["total_books"] = total_books
    stats["total_pages"] = sum(review.book.pages or 0 for review in reviews)
    stats["average_pages"] = round(stats["total_pages"] / total_books, 1)
    stats["average_rating"] = round(
        sum(review.rating or 0 for review in reviews) / total_books, 1
    )
    page_reviews = reviews.order_by("book__pages")
    stats["shortest_book"] = page_reviews.first().book
    stats["longest_book"] = page_reviews.last().book
    word_reviews = sorted(reviews, key=lambda r: r.word_count)
    stats["shortest_review"] = word_reviews[0].book
    stats["longest_review"] = word_reviews[-1].book
    stats["average_review"] = round(
        sum(review.word_count for review in reviews) / total_books, 1
    )
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
                    + [f"tag:{tag.name}" for tag in book.tags.all() or []]
                    + ([f"rating:{book.review.rating}"] if book.review.rating else [])
                    if term
                ],
            }
        )
    return nodes


def get_edges(graph=None):
    graph = graph or get_graph()
    return [{"source": source, "target": target} for source, target in graph.edges]
