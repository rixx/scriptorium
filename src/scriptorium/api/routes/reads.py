from django.shortcuts import get_object_or_404
from ninja import Router

from scriptorium.api.schemas import ReadDetailOut, ReadPatchIn
from scriptorium.main.models import Read

router = Router(tags=["reads"])


@router.patch("/{read_id}/", response=ReadDetailOut, summary="Update a read")
def update_read(request, read_id: int, payload: ReadPatchIn):
    """Partial update. Corrections deliberately don't bump the book's feed
    date -- only genuinely new reads do (when they are logged)."""
    read = get_object_or_404(Read, pk=read_id)
    data = payload.model_dump(exclude_unset=True)
    if "date" in data:
        read.finished_on = data.pop("date")
    for field, value in data.items():
        setattr(read, field, value)
    read.save()
    return read


@router.delete("/{read_id}/", response={204: None}, summary="Delete a read")
def delete_read(request, read_id: int):
    """Removing a read never rewinds the book's feed date; like the web edit
    form, past feed appearances stay as they were."""
    read = get_object_or_404(Read, pk=read_id)
    read.delete()
    return 204, None
