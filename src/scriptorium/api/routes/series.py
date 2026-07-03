from django.db.models import Count
from ninja import Router
from ninja.pagination import paginate

from scriptorium.api.schemas import SeriesOut
from scriptorium.main.models import Series

router = Router(tags=["series"])


@router.get("/", response=list[SeriesOut], summary="List and search series")
@paginate
def list_series(request, q: str | None = None):
    series = Series.objects.annotate(book_count=Count("books")).order_by("name_slug")
    if q:
        series = series.filter(name__icontains=q)
    return series
