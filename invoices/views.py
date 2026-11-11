from __future__ import annotations

import csv
import io
import json
import logging

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import limits
from .models import Document, Workspace
from .services import files
from .services.checks import run_checks, summary
from .services.extract import ExtractionError, extract
from .services.schema import HEADER_FIELDS, clean, empty, get

log = logging.getLogger(__name__)


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _workspace(request: HttpRequest, create: bool = False) -> Workspace | None:
    workspace_id = request.session.get("workspace")
    if workspace_id:
        workspace = Workspace.objects.filter(pk=workspace_id).first()
        if workspace:
            return workspace
    if not create:
        return None
    workspace = Workspace.objects.create()
    request.session["workspace"] = str(workspace.pk)
    return workspace


def _document(request: HttpRequest, pk) -> Document:
    """Only documents in the visitor's own workspace are reachable."""
    workspace = _workspace(request)
    document = workspace.documents.filter(pk=pk).first() if workspace else None
    if document is None:
        raise Http404("Document not found")
    return document


def _serialize(document: Document) -> dict:
    data = document.data or empty()
    return {
        "id": str(document.pk),
        "filename": document.filename,
        "media_type": document.media_type,
        "status": document.status,
        "status_label": document.get_status_display(),
        "source": document.extraction_source,
        "error": document.error,
        "supplier": get(data, "supplier.name"),
        "total": data.get("total"),
        "currency": data.get("currency"),
        "data": data,
        "checks": summary(run_checks(data)) if document.data else None,
    }


def _allow_extraction(request: HttpRequest) -> str | None:
    cfg = settings.INVOICEFLOW
    if not limits.allow("extract", limits.client_ip(request), cfg["EXTRACTIONS_PER_IP_PER_DAY"]):
        return "You have reached today's limit for this demo. Try again tomorrow."
    if not limits.allow("extract-total", "everyone", cfg["EXTRACTIONS_PER_DAY_TOTAL"]):
        return "This demo has reached its daily limit. Try again tomorrow."
    return None


def _run_extraction(document: Document, data: bytes) -> None:
    try:
        result = extract(data, document.media_type)
    except ExtractionError as exc:
        if document.sample_key and not settings.ANTHROPIC_API_KEY:
            # Samples still work without a model: show the values printed on them, labelled as stored.
            stored = files.samples()[document.sample_key]["values"]
            document.extracted = clean(stored)
            document.data = clean(stored)
            document.extraction_source = "stored-example"
            document.status = Document.Status.EXTRACTED
            document.error = ""
        else:
            document.status = Document.Status.FAILED
            document.error = str(exc)
    else:
        document.extracted = clean(result)
        document.data = clean(result)
        document.extraction_source = "ai"
        document.status = Document.Status.EXTRACTED
        document.error = ""
    document.save()


# ---- pages -------------------------------------------------------------------------------
@ensure_csrf_cookie
@require_GET
def index(request: HttpRequest):
    workspace = _workspace(request)
    cfg = settings.INVOICEFLOW
    return render(request, "invoices/index.html", {
        "documents": list(workspace.documents.all()) if workspace else [],
        "samples": files.samples(),
        "ai_enabled": bool(settings.ANTHROPIC_API_KEY),
        "max_mb": cfg["MAX_FILE_BYTES"] // (1024 * 1024),
        "max_pages": cfg["MAX_PAGES"],
        "retention_hours": cfg["RETENTION_HOURS"],
        "repo_url": cfg["REPO_URL"],
    })


@ensure_csrf_cookie
@require_GET
def review(request: HttpRequest, pk):
    document = _document(request, pk)
    return render(request, "invoices/review.html", {
        "document": document,
        "payload": _serialize(document),
        "header_fields": HEADER_FIELDS,
        "repo_url": settings.INVOICEFLOW["REPO_URL"],
    })


@require_GET
def document_file(request: HttpRequest, pk):
    document = _document(request, pk)
    try:
        handle = open(settings.UPLOAD_DIR / document.stored_name, "rb")
    except FileNotFoundError as exc:
        raise Http404("File not found") from exc
    response = FileResponse(handle, content_type=document.media_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["X-Frame-Options"] = "SAMEORIGIN"  # the review page shows PDFs in a frame
    return response


@require_GET
def sample_image(request: HttpRequest, key: str):
    catalogue = files.samples()
    if key not in catalogue:
        raise Http404("Sample not found")
    return FileResponse(open(files.SAMPLES_DIR / catalogue[key]["file"], "rb"), content_type="image/png")


# ---- API ---------------------------------------------------------------------------------
@require_POST
def upload(request: HttpRequest):
    upload_file = request.FILES.get("file")
    if upload_file is None:
        return _error("Choose a file to upload.")
    if upload_file.size > settings.INVOICEFLOW["MAX_FILE_BYTES"]:
        return _error(f"This file is larger than {settings.INVOICEFLOW['MAX_FILE_BYTES'] // (1024 * 1024)} MB.")
    blocked = _allow_extraction(request)
    if blocked:
        return _error(blocked, 429)
    files.purge_expired()
    workspace = _workspace(request, create=True)
    data = upload_file.read()
    try:
        document = files.store(workspace, upload_file.name, data)
    except files.UploadError as exc:
        return _error(str(exc))
    _run_extraction(document, data)
    return JsonResponse(_serialize(document), status=201)


@require_POST
def use_sample(request: HttpRequest, key: str):
    catalogue = files.samples()
    if key not in catalogue:
        return _error("That sample does not exist.", 404)
    if settings.ANTHROPIC_API_KEY:
        blocked = _allow_extraction(request)
        if blocked:
            return _error(blocked, 429)
    workspace = _workspace(request, create=True)
    data = (files.SAMPLES_DIR / catalogue[key]["file"]).read_bytes()
    try:
        document = files.store(workspace, catalogue[key]["file"], data, sample_key=key)
    except files.UploadError as exc:
        return _error(str(exc))
    _run_extraction(document, data)
    return JsonResponse(_serialize(document), status=201)


@require_POST
def save(request: HttpRequest, pk):
    document = _document(request, pk)
    if document.status == Document.Status.APPROVED:
        return _error("This document is approved. Reopen it to make changes.", 409)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _error("Send the values as JSON.")
    document.data = clean(payload.get("data"))
    if document.status == Document.Status.FAILED:
        document.status = Document.Status.EXTRACTED  # entered by hand after a failed read
    document.save()
    return JsonResponse(_serialize(document))


@require_POST
def approve(request: HttpRequest, pk):
    document = _document(request, pk)
    if not document.data:
        return _error("There is nothing to approve yet.")
    document.status = Document.Status.APPROVED
    document.approved_at = timezone.now()
    document.save()
    return JsonResponse(_serialize(document))


@require_POST
def reopen(request: HttpRequest, pk):
    document = _document(request, pk)
    document.status = Document.Status.EXTRACTED
    document.approved_at = None
    document.save()
    return JsonResponse(_serialize(document))


@require_POST
def manual(request: HttpRequest, pk):
    document = _document(request, pk)
    if not document.data:
        document.data = empty()
        document.extraction_source = "manual"
        document.status = Document.Status.EXTRACTED
        document.save()
    return JsonResponse(_serialize(document))


@require_POST
def remove(request: HttpRequest, pk):
    files.delete(_document(request, pk))
    return JsonResponse({"ok": True})


@require_GET
def export(request: HttpRequest, fmt: str):
    workspace = _workspace(request)
    approved = list(workspace.documents.filter(status=Document.Status.APPROVED).order_by("approved_at")) if workspace else []
    if fmt == "json":
        body = json.dumps([{"file": d.filename, **d.data} for d in approved], ensure_ascii=False, indent=2)
        response = HttpResponse(body, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="invoices.json"'
        return response
    if fmt != "csv":
        raise Http404("Unknown format")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # One row per line item, with the header values repeated: the shape accounting imports expect.
    writer.writerow(["File", "Type", *[label for _, label in HEADER_FIELDS], "Line description", "Quantity", "Unit price", "Line amount", "VAT rate"])
    for d in approved:
        head = [d.filename, d.data.get("document_type"), *[get(d.data, key) for key, _ in HEADER_FIELDS]]
        for item in d.data.get("line_items") or [{}]:
            writer.writerow(head + [item.get("description"), item.get("quantity"), item.get("unit_price"), item.get("amount"), item.get("vat_rate")])
    response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")  # BOM so Excel reads UTF-8
    response["Content-Disposition"] = 'attachment; filename="invoices.csv"'
    return response


@require_GET
def healthz(request: HttpRequest):
    return JsonResponse({"ok": True, "ai": bool(settings.ANTHROPIC_API_KEY)})
