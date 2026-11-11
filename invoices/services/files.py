"""Accept an upload, check what it really is, and keep it privately for the review screen."""
from __future__ import annotations

import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..models import Document, Workspace

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# Detect the type from the file's first bytes, never from its name or the browser's claim.
SIGNATURES = [
    (b"%PDF", "application/pdf", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
]


class UploadError(Exception):
    """Raised with a message that is safe to show the visitor."""


def sniff(data: bytes) -> tuple[str, str]:
    for magic, media_type, ext in SIGNATURES:
        if data.startswith(magic):
            return media_type, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise UploadError("Upload a PDF, JPG, PNG or WebP file.")


def validate(data: bytes) -> tuple[str, str]:
    cfg = settings.INVOICEFLOW
    if len(data) > cfg["MAX_FILE_BYTES"]:
        raise UploadError(f"This file is larger than {cfg['MAX_FILE_BYTES'] // (1024 * 1024)} MB.")
    media_type, ext = sniff(data)
    if media_type.startswith("image/") and len(data) > cfg["MAX_IMAGE_BYTES"]:
        raise UploadError(f"Images can be up to {cfg['MAX_IMAGE_BYTES'] // (1024 * 1024)} MB. Try a smaller photo or a PDF.")
    if media_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise UploadError("This PDF is password protected. Remove the password and upload it again.")
            if len(reader.pages) > cfg["MAX_PAGES"]:
                raise UploadError(f"This PDF has {len(reader.pages)} pages. The limit is {cfg['MAX_PAGES']}.")
        except UploadError:
            raise
        except (PdfReadError, ValueError, KeyError, OSError) as exc:
            raise UploadError("This PDF could not be read. It may be damaged.") from exc
    return media_type, ext


def store(workspace: Workspace, filename: str, data: bytes, sample_key: str = "") -> Document:
    cfg = settings.INVOICEFLOW
    if workspace.documents.count() >= cfg["MAX_DOCS_PER_WORKSPACE"]:
        raise UploadError(f"You can keep {cfg['MAX_DOCS_PER_WORKSPACE']} documents at a time. Remove one first.")
    media_type, ext = validate(data)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    (settings.UPLOAD_DIR / stored_name).write_bytes(data)
    return Document.objects.create(
        workspace=workspace,
        filename=Path(filename).name[:200] or f"document.{ext}",
        media_type=media_type,
        stored_name=stored_name,
        size=len(data),
        sample_key=sample_key,
    )


def read(document: Document) -> bytes:
    return (settings.UPLOAD_DIR / document.stored_name).read_bytes()


def delete(document: Document) -> None:
    (settings.UPLOAD_DIR / document.stored_name).unlink(missing_ok=True)
    document.delete()


def samples() -> dict:
    """Built-in fictional documents, with the values printed on them for when no model is connected."""
    return json.loads((SAMPLES_DIR / "samples.json").read_text(encoding="utf-8"))


def purge_expired() -> int:
    cutoff = timezone.now() - timedelta(hours=settings.INVOICEFLOW["RETENTION_HOURS"])
    removed = 0
    for document in Document.objects.filter(workspace__created_at__lt=cutoff):
        delete(document)
        removed += 1
    Workspace.objects.filter(created_at__lt=cutoff).delete()
    return removed
