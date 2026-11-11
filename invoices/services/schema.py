"""The shape of an extracted invoice, used both for the model's structured output and for the review form.

Every value that may be missing on a real document is nullable, so the model can say "not on the
page" instead of inventing something. Amounts are numbers; dates are ISO strings.
"""
from __future__ import annotations

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
NULLABLE_DATE = {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]}

LINE_ITEM = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "quantity": NULLABLE_NUMBER,
        "unit_price": NULLABLE_NUMBER,
        "amount": NULLABLE_NUMBER,
        "vat_rate": NULLABLE_NUMBER,
    },
    "required": ["description", "quantity", "unit_price", "amount", "vat_rate"],
    "additionalProperties": False,
}

PARTY = {
    "type": "object",
    "properties": {"name": NULLABLE_STRING, "address": NULLABLE_STRING, "vat_id": NULLABLE_STRING},
    "required": ["name", "address", "vat_id"],
    "additionalProperties": False,
}

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string", "enum": ["invoice", "receipt", "credit_note", "other"]},
        "supplier": PARTY,
        "customer": PARTY,
        "invoice_number": NULLABLE_STRING,
        "issue_date": NULLABLE_DATE,
        "due_date": NULLABLE_DATE,
        "currency": NULLABLE_STRING,
        "line_items": {"type": "array", "items": LINE_ITEM},
        "subtotal": NULLABLE_NUMBER,
        "vat_total": NULLABLE_NUMBER,
        "total": NULLABLE_NUMBER,
        "iban": NULLABLE_STRING,
        "payment_reference": NULLABLE_STRING,
        "uncertain_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "document_type", "supplier", "customer", "invoice_number", "issue_date", "due_date", "currency",
        "line_items", "subtotal", "vat_total", "total", "iban", "payment_reference", "uncertain_fields",
    ],
    "additionalProperties": False,
}

# Field labels for the review screen and the CSV export, in display order.
HEADER_FIELDS = [
    ("supplier.name", "Supplier"),
    ("supplier.vat_id", "Supplier VAT ID"),
    ("supplier.address", "Supplier address"),
    ("customer.name", "Customer"),
    ("invoice_number", "Invoice number"),
    ("issue_date", "Issue date"),
    ("due_date", "Due date"),
    ("currency", "Currency"),
    ("subtotal", "Subtotal"),
    ("vat_total", "VAT"),
    ("total", "Total"),
    ("iban", "IBAN"),
    ("payment_reference", "Payment reference"),
]

NUMBER_FIELDS = {"subtotal", "vat_total", "total"}


def empty() -> dict:
    """A blank record in the schema's shape, used when a reviewer enters a document by hand."""
    return {
        "document_type": "invoice",
        "supplier": {"name": None, "address": None, "vat_id": None},
        "customer": {"name": None, "address": None, "vat_id": None},
        "invoice_number": None,
        "issue_date": None,
        "due_date": None,
        "currency": None,
        "line_items": [],
        "subtotal": None,
        "vat_total": None,
        "total": None,
        "iban": None,
        "payment_reference": None,
        "uncertain_fields": [],
    }


def get(data: dict, dotted: str):
    value = data
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def put(data: dict, dotted: str, value) -> None:
    *parents, last = dotted.split(".")
    target = data
    for part in parents:
        target = target.setdefault(part, {})
    target[last] = value


def _clean_text(value, limit: int = 300):
    if value is None:
        return None
    text = str(value).strip()[:limit]
    return text or None


def _clean_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    try:
        return round(float(str(value).replace("'", "").replace(" ", "").replace(",", ".")), 4)
    except ValueError:
        return None


def clean(raw: dict) -> dict:
    """Normalise data coming from the model or the review form into exactly the schema's shape."""
    raw = raw if isinstance(raw, dict) else {}
    data = empty()
    doc_type = raw.get("document_type")
    data["document_type"] = doc_type if doc_type in {"invoice", "receipt", "credit_note", "other"} else "invoice"
    for party in ("supplier", "customer"):
        source = raw.get(party) if isinstance(raw.get(party), dict) else {}
        data[party] = {key: _clean_text(source.get(key)) for key in ("name", "address", "vat_id")}
    for key in ("invoice_number", "issue_date", "due_date", "iban", "payment_reference"):
        data[key] = _clean_text(raw.get(key), 120)
    currency = _clean_text(raw.get("currency"), 3)
    data["currency"] = currency.upper() if currency else None
    for key in ("subtotal", "vat_total", "total"):
        data[key] = _clean_number(raw.get(key))
    items = raw.get("line_items") if isinstance(raw.get("line_items"), list) else []
    data["line_items"] = [
        {
            "description": _clean_text(item.get("description"), 300) or "",
            "quantity": _clean_number(item.get("quantity")),
            "unit_price": _clean_number(item.get("unit_price")),
            "amount": _clean_number(item.get("amount")),
            "vat_rate": _clean_number(item.get("vat_rate")),
        }
        for item in items[:200]
        if isinstance(item, dict)
    ]
    uncertain = raw.get("uncertain_fields") if isinstance(raw.get("uncertain_fields"), list) else []
    data["uncertain_fields"] = [str(f)[:60] for f in uncertain[:30]]
    return data
