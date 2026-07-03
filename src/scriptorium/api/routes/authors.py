from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.pagination import paginate

from scriptorium.api.schemas import AuthorDetailOut, AuthorOut, AuthorPatchIn
from scriptorium.main.models import Author

router = Router(tags=["authors"])


@router.get("/", response=list[AuthorOut], summary="List and search authors")
@paginate
def list_authors(request, q: str | None = None):
    authors = Author.objects.order_by("name_slug")
    if q:
        authors = authors.filter(name__icontains=q)
    return authors


@router.get(
    "/{author_slug}/",
    response=AuthorDetailOut,
    summary="Author detail with published books",
)
def author_detail(request, author_slug: str):
    return get_object_or_404(Author, name_slug=author_slug)


@router.patch("/{author_slug}/", response=AuthorDetailOut, summary="Update an author")
def update_author(request, author_slug: str, payload: AuthorPatchIn):
    """Light edits only: renames keep the slug (it is the author's identity
    in every book URL)."""
    author = get_object_or_404(Author, name_slug=author_slug)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(author, field, value)
    author.save()
    return author
