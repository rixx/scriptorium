from django.db.models import Count
from ninja import Router

from scriptorium.api.schemas import TagOut
from scriptorium.main.models import Tag

router = Router(tags=["tags"])


@router.get("/", response=list[TagOut], summary="List tags")
def list_tags(request):
    # Annotating drops the model's default ordering, so restate it.
    return Tag.objects.annotate(book_count=Count("book")).order_by(
        "category", "name_slug"
    )
