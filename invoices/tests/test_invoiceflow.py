import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.core.cache import cache
from django.test import TestCase, override_settings
from pypdf import PdfWriter

from invoices.models import Document, Workspace
from invoices.services import files
from invoices.services.checks import iban_valid, run_checks
from invoices.services.extract import ExtractionError, extract
from invoices.services.schema import INVOICE_SCHEMA, clean, empty

TMP_UPLOADS = Path(tempfile.mkdtemp(prefix="invoiceflow-tests-"))
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PNG = files.SAMPLES_DIR.joinpath("swiss-invoice.png").read_bytes()


def checks_by_key(data):
    return {c.key: c.ok for c in run_checks(data)}


class FakeClient:
    def __init__(self, text="", stop_reason="end_turn"):
        self.kwargs = None
        self.messages = SimpleNamespace(create=self._create)
        self._response = SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self._response


def pdf_bytes(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class CheckTests(TestCase):
    def setUp(self):
        self.samples = files.samples()

    def test_samples_behave_as_documented(self):
        self.assertTrue(all(checks_by_key(self.samples["swiss-invoice"]["values"]).values()))
        self.assertTrue(all(checks_by_key(self.samples["german-invoice"]["values"]).values()))
        receipt = checks_by_key(self.samples["bakery-receipt"]["values"])
        self.assertFalse(receipt["lines_sum"])

    def test_arithmetic_failures_are_caught(self):
        data = clean(self.samples["swiss-invoice"]["values"])
        data["line_items"][0]["amount"] = 2000
        data["total"] = 999
        result = checks_by_key(data)
        self.assertFalse(result["line_math"])
        self.assertFalse(result["lines_sum"])
        self.assertFalse(result["total_math"])

    def test_formats(self):
        self.assertTrue(iban_valid("DE89 3704 0044 0532 0130 00"))
        self.assertFalse(iban_valid("DE89 3704 0044 0532 0130 01"))
        self.assertFalse(iban_valid("not an iban"))
        data = empty()
        data.update(currency="XYZ", issue_date="2026-11-10", due_date="2026-11-01", iban="CH00 1234")
        result = checks_by_key(data)
        self.assertFalse(result["currency"])
        self.assertFalse(result["date_order"])
        self.assertFalse(result["iban"])
        self.assertFalse(result["total_present"])

    def test_uncertain_fields_become_checks(self):
        data = clean(self.samples["swiss-invoice"]["values"])
        data["uncertain_fields"] = ["issue_date"]
        self.assertFalse(checks_by_key(data)["uncertain:issue_date"])


class CleanTests(TestCase):
    def test_clean_coerces_form_input(self):
        raw = {
            "document_type": "nonsense",
            "supplier": {"name": "  ACME  ", "extra": "dropped"},
            "currency": "chf",
            "total": "1'234,50",
            "line_items": [{"description": "x", "quantity": "2", "amount": "abc"}, "not a dict"],
            "unexpected": "dropped",
        }
        data = clean(raw)
        self.assertEqual(data["document_type"], "invoice")
        self.assertEqual(data["supplier"], {"name": "ACME", "address": None, "vat_id": None})
        self.assertEqual(data["currency"], "CHF")
        self.assertEqual(data["total"], 1234.5)
        self.assertEqual(data["line_items"], [{"description": "x", "quantity": 2.0, "unit_price": None, "amount": None, "vat_rate": None}])
        self.assertNotIn("unexpected", data)
        self.assertEqual(set(data), set(INVOICE_SCHEMA["required"]))


class ExtractTests(TestCase):
    def test_request_shape_and_parsing(self):
        values = files.samples()["german-invoice"]["values"]
        client = FakeClient(json.dumps(values))
        result = extract(PNG, "image/png", client=client)
        self.assertEqual(result["invoice_number"], "2026-1182")
        content = client.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["media_type"], "image/png")
        self.assertEqual(client.kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertIs(client.kwargs["output_config"]["format"]["schema"], INVOICE_SCHEMA)
        self.assertNotIn("temperature", client.kwargs)

    def test_pdf_is_sent_as_document(self):
        client = FakeClient(json.dumps(empty()))
        extract(pdf_bytes(), "application/pdf", client=client)
        self.assertEqual(client.kwargs["messages"][0]["content"][0]["type"], "document")

    def test_failures(self):
        with self.assertRaises(ExtractionError):
            extract(PNG, "image/png", client=FakeClient("", stop_reason="refusal"))
        with self.assertRaises(ExtractionError):
            extract(PNG, "image/png", client=FakeClient("{not json"))
        with self.assertRaises(ExtractionError):
            extract(PNG, "image/png", client=FakeClient("[]"))

    def test_schema_objects_forbid_extra_properties(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(INVOICE_SCHEMA)


class FileTests(TestCase):
    def test_type_comes_from_content_not_name(self):
        self.assertEqual(files.sniff(PNG)[0], "image/png")
        self.assertEqual(files.sniff(pdf_bytes())[0], "application/pdf")
        with self.assertRaises(files.UploadError):
            files.sniff(b"MZ\x90\x00 executable")

    def test_pdf_page_limit(self):
        from django.conf import settings

        with self.settings(INVOICEFLOW={**settings.INVOICEFLOW, "MAX_PAGES": 2}):
            with self.assertRaises(files.UploadError):
                files.validate(pdf_bytes(3))


@override_settings(CACHES=LOCMEM, UPLOAD_DIR=TMP_UPLOADS, ANTHROPIC_API_KEY="")
class FlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def _upload(self, data=PNG, name="scan.png"):
        handle = io.BytesIO(data)
        handle.name = name
        return self.client.post("/api/documents", {"file": handle})

    def test_sample_review_approve_export(self):
        created = self.client.post("/api/samples/german-invoice")
        self.assertEqual(created.status_code, 201)
        doc = created.json()
        self.assertEqual(doc["source"], "stored-example")
        self.assertEqual(doc["checks"]["failed"], 0)

        page = self.client.get(f"/documents/{doc['id']}/")
        self.assertContains(page, "Check and approve")
        self.assertEqual(self.client.get(f"/documents/{doc['id']}/file")["Content-Type"], "image/png")

        edited = doc["data"] | {"total": 1.0}
        saved = self.client.post(f"/api/documents/{doc['id']}/save", json.dumps({"data": edited}), content_type="application/json").json()
        self.assertGreater(saved["checks"]["failed"], 0)
        self.assertEqual(Document.objects.get().extracted["total"], 683.87)  # the original read is kept

        self.client.post(f"/api/documents/{doc['id']}/save", json.dumps({"data": doc["data"]}), content_type="application/json")
        self.assertEqual(self.client.post(f"/api/documents/{doc['id']}/approve").json()["status"], "approved")
        blocked = self.client.post(f"/api/documents/{doc['id']}/save", json.dumps({"data": edited}), content_type="application/json")
        self.assertEqual(blocked.status_code, 409)

        csv_body = self.client.get("/export.csv").content.decode("utf-8-sig")
        self.assertIn("Druckerei Weber & Söhne", csv_body)
        self.assertEqual(len(csv_body.strip().splitlines()), 1 + 4)  # header + one row per line item
        exported = json.loads(self.client.get("/export.json").content)
        self.assertEqual(exported[0]["invoice_number"], "2026-1182")

    def test_upload_without_model_offers_manual_entry(self):
        created = self._upload()
        self.assertEqual(created.status_code, 201)
        doc = created.json()
        self.assertEqual(doc["status"], "failed")
        manual = self.client.post(f"/api/documents/{doc['id']}/manual").json()
        self.assertEqual(manual["status"], "extracted")
        self.assertEqual(manual["source"], "manual")

    def test_documents_are_private(self):
        doc = self.client.post("/api/samples/swiss-invoice").json()
        other = self.client_class()
        self.assertEqual(other.get(f"/documents/{doc['id']}/").status_code, 404)
        self.assertEqual(other.get(f"/documents/{doc['id']}/file").status_code, 404)
        self.assertEqual(other.post(f"/api/documents/{doc['id']}/delete").status_code, 404)
        self.assertEqual(json.loads(other.get("/export.json").content), [])

    def test_bad_uploads(self):
        self.assertEqual(self.client.post("/api/documents").status_code, 400)
        self.assertEqual(self._upload(b"just text", "invoice.pdf").status_code, 400)
        self.assertEqual(self.client.post("/api/samples/nope").status_code, 404)

    def test_delete_removes_the_file(self):
        doc = self.client.post("/api/samples/swiss-invoice").json()
        stored = Document.objects.get().stored_name
        self.assertEqual(self.client.post(f"/api/documents/{doc['id']}/delete").status_code, 200)
        from django.conf import settings

        self.assertFalse((settings.UPLOAD_DIR / stored).exists())

    def test_rate_limit_applies_to_uploads(self):
        from django.conf import settings

        with self.settings(INVOICEFLOW={**settings.INVOICEFLOW, "EXTRACTIONS_PER_IP_PER_DAY": 1}):
            self.assertEqual(self._upload().status_code, 201)
            self.assertEqual(self._upload().status_code, 429)

    def test_expired_documents_are_purged_with_their_files(self):
        self.client.post("/api/samples/swiss-invoice")
        stored = Document.objects.get().stored_name
        Workspace.objects.update(created_at="2020-01-01T00:00:00Z")
        files.purge_expired()
        from django.conf import settings

        self.assertEqual(Document.objects.count(), 0)
        self.assertFalse((settings.UPLOAD_DIR / stored).exists())

    def test_pages(self):
        self.assertContains(self.client.get("/"), "InvoiceFlow")
        self.assertEqual(self.client.get("/samples/bakery-receipt.png").status_code, 200)
        self.assertEqual(self.client.get("/healthz").json(), {"ok": True, "ai": False})


@override_settings(CACHES=LOCMEM, UPLOAD_DIR=TMP_UPLOADS, ANTHROPIC_API_KEY="test-key")
class WithModelTests(TestCase):
    def test_extraction_result_is_stored(self):
        from unittest import mock

        values = files.samples()["swiss-invoice"]["values"]
        with mock.patch("invoices.views.extract", return_value=values):
            doc = self.client.post("/api/samples/swiss-invoice").json()
        self.assertEqual(doc["source"], "ai")
        self.assertEqual(doc["data"]["invoice_number"], "AK-2026-0417")

    def test_extraction_error_is_shown(self):
        from unittest import mock

        with mock.patch("invoices.views.extract", side_effect=ExtractionError("The AI service is busy right now.")):
            doc = self.client.post("/api/samples/swiss-invoice").json()
        self.assertEqual(doc["status"], "failed")
        self.assertIn("busy", doc["error"])
