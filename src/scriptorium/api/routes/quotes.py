from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from scriptorium.api.schemas import QuoteOut, QuotePatchIn
from scriptorium.main.models import Author, Quote

router = Router(tags=["quotes"])


@router.patch("/{quote_id}/", response=QuoteOut, summary="Update a quote")
def update_quote(request, quote_id: int, payload: QuotePatchIn):
    quote = get_object_or_404(Quote, pk=quote_id)
    data = payload.model_dump(exclude_unset=True)
    if "source_author" in data:
        slug = data.pop("source_author")
        if slug is None:
            quote.source_author = None
        else:
            author = Author.objects.filter(name_slug=slug).first()
            if author is None:
                raise HttpError(400, f"Unknown author '{slug}'.")
            quote.source_author = author
    for field, value in data.items():
        setattr(quote, field, value)
    quote.full_clean()
    quote.save()
    return quote


@router.delete("/{quote_id}/", response={204: None}, summary="Delete a quote")
def delete_quote(request, quote_id: int):
    quote = get_object_or_404(Quote, pk=quote_id)
    quote.delete()
    return 204, None
