from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from ninja import Router

from scriptorium.api.schemas import KoreaderSyncIn, KoreaderSyncOut, MessageOut
from scriptorium.main.models import Book, Read, Series
from scriptorium.main.utils import slugify

router = Router(tags=["koreader"])

# Below this plugin version the payload contract is not guaranteed; the
# device gets a 426 and should update (KoInsight's pattern).
MIN_PLUGIN_VERSION = (1, 0, 0)


def _parse_version(version):
    """Lenient semver-ish parse; unparseable versions count as too old."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def _extract_isbns(identifiers):
    """Pull normalized ISBN-10/13 strings out of the EPUB's identifier soup
    (``ISBN:...``, ``urn:isbn:...``, raw digit strings; hyphens/spaces
    removed). Anything else (uuid:, calibre:, ...) is ignored."""
    isbns = []
    for identifier in identifiers:
        value = identifier.strip()
        lowered = value.lower()
        for prefix in ("urn:isbn:", "isbn:"):
            if lowered.startswith(prefix):
                value = value[len(prefix) :]
                break
        candidate = value.replace("-", "").replace(" ", "").upper()
        is_isbn13 = len(candidate) == 13 and candidate.isdigit()
        is_isbn10 = (
            len(candidate) == 10
            and candidate[:9].isdigit()
            and (candidate[9].isdigit() or candidate[9] == "X")
        )
        if is_isbn13 or is_isbn10:
            isbns.append(candidate)
    return isbns


def _series_position(series_index):
    """Calibre series indexes arrive as int, float, or string; Book stores a
    short string. Integral floats lose their pointless '.0'."""
    if series_index in (None, ""):
        return None
    if isinstance(series_index, float) and series_index.is_integer():
        series_index = int(series_index)
    return str(series_index)[:10]


def _device_notes(payload):
    """The device's free-text note plus its star rating, destined for
    Read.notes -- input for the eventual review, never for Book.rating."""
    parts = []
    if payload.summary_note and payload.summary_note.strip():
        parts.append(payload.summary_note.strip())
    if payload.rating:
        parts.append(f"KOReader rating: {payload.rating}/5")
    return "\n\n".join(parts) or None


def _match_book(payload, warnings):
    """The matching chain: known device file (md5) -> ISBN -> slug match or
    auto-create via queue_for_review. Returns (book, created)."""
    known_read = (
        Read.objects.filter(koreader_md5=payload.md5).select_related("book").first()
    )
    if known_read:
        return known_read.book, False
    isbns = _extract_isbns(payload.identifiers)
    if isbns:
        book = Book.all_objects.filter(
            Q(isbn13__in=isbns) | Q(isbn10__in=isbns)
        ).first()
        if book:
            return book, False
        warnings.append("ISBN not in library; matched by title/author")
    else:
        warnings.append("no ISBN found; matched by title/author")
    if not slugify(payload.title):
        # Books are keyed on their slug; a title that slugifies to nothing
        # (all punctuation, non-Latin scripts) would collide with every
        # other such book. Better an explicit per-book error.
        raise DjangoValidationError(
            f"Cannot derive a catalogue slug from title {payload.title!r}."
        )
    author_name = next((author for author in payload.authors if author.strip()), None)
    if author_name is None:
        warnings.append("no author in metadata; filed under 'Unknown'")
        author_name = "Unknown"
    series = (
        Series.objects.get_or_create_by_name(payload.series)[0]
        if payload.series
        else None
    )
    book, created = Book.all_objects.queue_for_review(
        title=payload.title,
        author_name=author_name,
        series=series,
        series_position=_series_position(payload.series_index),
    )
    if created:
        # Device metadata only ever fills in a *new* book; matched books are
        # never mutated beyond queue_for_review's to_read -> to_review bump.
        book.source = "koreader"
        book.isbn13 = next((isbn for isbn in isbns if len(isbn) == 13), None)
        book.isbn10 = next((isbn for isbn in isbns if len(isbn) == 10), None)
        book.pages = payload.pages
        book.save(update_fields=["source", "isbn13", "isbn10", "pages"])
    return book, created


def _upsert_read(book, payload):
    """Idempotent read upsert keyed on (koreader_md5, finished_on): re-pushes
    update in place (highlights are reviewed after finishing), a manually
    logged read on the same date gets adopted, otherwise a new Read is
    created -- Read.save() handles reread feed-date semantics."""
    highlights = [h.model_dump() for h in payload.highlights] or None
    notes = _device_notes(payload)
    did_not_finish = payload.status == "abandoned"

    read = book.reads.filter(
        koreader_md5=payload.md5, finished_on=payload.finished_on
    ).first()
    if read:
        read.highlights = highlights
        read.started_on = payload.started_on
        read.total_time_seconds = payload.total_time_seconds
        read.did_not_finish = did_not_finish
        if notes:
            # A device without a note never wipes existing notes.
            read.notes = notes
        read.save()
        return read, True

    read = book.reads.filter(
        koreader_md5__isnull=True, finished_on=payload.finished_on
    ).first()
    if read:
        # A read logged manually before the device pushed: adopt it instead
        # of creating a same-day duplicate. Manually entered notes win.
        read.koreader_md5 = payload.md5
        read.highlights = highlights
        read.started_on = read.started_on or payload.started_on
        read.total_time_seconds = payload.total_time_seconds
        read.format = read.format or Read.Format.EBOOK
        read.notes = read.notes or notes
        read.save()
        return read, True

    read = Read(
        book=book,
        finished_on=payload.finished_on,
        started_on=payload.started_on,
        did_not_finish=did_not_finish,
        format=Read.Format.EBOOK,
        source="koreader",
        total_time_seconds=payload.total_time_seconds,
        koreader_md5=payload.md5,
        highlights=highlights,
        notes=notes,
    )
    read.full_clean()
    read.save()
    return read, False


def _sync_book(payload):
    warnings = []
    book, created = _match_book(payload, warnings)
    read, updated = _upsert_read(book, payload)
    if created:
        action = "created_book"
    elif updated:
        action = "updated_read"
    else:
        action = "matched"
    return {
        "md5": payload.md5,
        "action": action,
        "book": book.slug,
        "read_id": read.pk,
        "highlights_stored": len(payload.highlights),
        "warnings": warnings,
    }


@router.post(
    "/sync/",
    response={200: KoreaderSyncOut, 426: MessageOut},
    summary="Push finished books from KOReader",
)
def sync(request, payload: KoreaderSyncIn):
    """Ingest finished (or abandoned) books pushed by the KOReader plugin:
    each book is matched (device-file md5 -> ISBN -> title/author slug) or
    auto-created into the review queue, and its read -- finish date,
    aggregate stats, and the full highlight blob -- is idempotently upserted.
    Books are processed independently: one bad book becomes an ``error``
    result instead of failing the batch."""
    if _parse_version(payload.plugin_version) < MIN_PLUGIN_VERSION:
        minimum = ".".join(str(part) for part in MIN_PLUGIN_VERSION)
        return 426, {
            "detail": f"Plugin version {payload.plugin_version} is not "
            f"supported anymore; please update to at least {minimum}."
        }
    results = []
    for book_payload in payload.books:
        try:
            with transaction.atomic():
                results.append(_sync_book(book_payload))
        except Exception as exc:  # noqa: BLE001 -- one bad book must not poison the batch
            detail = (
                "; ".join(exc.messages)
                if isinstance(exc, DjangoValidationError)
                else str(exc) or exc.__class__.__name__
            )
            results.append(
                {"md5": book_payload.md5, "action": "error", "detail": detail}
            )
    return 200, {"results": results}
