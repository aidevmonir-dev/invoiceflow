"""Arithmetic and format checks on an extracted invoice.

The model reads the document; these checks decide whether the numbers hang together. A reviewer sees
every failed check next to the field it concerns before approving. The review screen saves each
edit and gets the checks back, so the list updates while someone corrects a value.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

TOLERANCE = 0.02  # rounding on printed invoices is usually to the cent

ISO_CURRENCIES = {
    "CHF", "EUR", "USD", "GBP", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "JPY", "CAD", "AUD",
    "NZD", "SGD", "HKD", "CNY", "INR", "BDT", "AED", "SAR", "ZAR", "BRL", "MXN", "TRY", "ILS",
}


@dataclass
class Check:
    key: str
    ok: bool
    message: str
    field: str = ""  # which field to highlight on the review screen

    def as_dict(self) -> dict:
        return asdict(self)


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def _money(value: float) -> str:
    return f"{value:,.2f}"


def iban_valid(iban: str) -> bool:
    """ISO 13616 mod-97 check. Spaces are ignored."""
    compact = re.sub(r"\s+", "", iban or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def _parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def run_checks(data: dict) -> list[Check]:
    checks: list[Check] = []
    items = data.get("line_items") or []
    subtotal, vat, total = _num(data.get("subtotal")), _num(data.get("vat_total")), _num(data.get("total"))

    # Each line: quantity x unit price = amount.
    bad_lines = []
    for index, item in enumerate(items, start=1):
        qty, price, amount = _num(item.get("quantity")), _num(item.get("unit_price")), _num(item.get("amount"))
        if qty is not None and price is not None and amount is not None and not _close(qty * price, amount):
            bad_lines.append(index)
    if items:
        checks.append(Check(
            "line_math",
            not bad_lines,
            "Every line: quantity x unit price = amount." if not bad_lines
            else f"Quantity x unit price does not match the amount on line {', '.join(map(str, bad_lines))}.",
            "line_items",
        ))

    # Lines add up to the subtotal. Till receipts often print no subtotal and list prices
    # including VAT, so there the lines are compared with the total instead.
    amounts = [_num(i.get("amount")) for i in items]
    target, target_name, target_field = subtotal, "subtotal", "subtotal"
    if subtotal is None and data.get("document_type") == "receipt":
        target, target_name, target_field = total, "total", "total"
    if items and target is not None and all(a is not None for a in amounts):
        line_sum = sum(amounts)
        ok = _close(line_sum, target)
        checks.append(Check(
            "lines_sum",
            ok,
            f"Line items add up to the {target_name} ({_money(target)})." if ok
            else f"Line items add up to {_money(line_sum)}, but the {target_name} says {_money(target)}.",
            target_field,
        ))

    # Subtotal + VAT = total.
    if subtotal is not None and vat is not None and total is not None:
        ok = _close(subtotal + vat, total)
        checks.append(Check(
            "total_math",
            ok,
            "Subtotal plus VAT equals the total." if ok
            else f"Subtotal plus VAT is {_money(subtotal + vat)}, but the total says {_money(total)}.",
            "total",
        ))

    # VAT on each line matches the VAT total, when rates are printed per line.
    rated = [(_num(i.get("amount")), _num(i.get("vat_rate"))) for i in items]
    if items and vat is not None and subtotal is not None and all(a is not None and r is not None for a, r in rated):
        expected = round(sum(a * r / 100 for a, r in rated), 2)
        ok = abs(expected - vat) <= max(TOLERANCE, 0.01 * len(items))
        checks.append(Check(
            "vat_math",
            ok,
            "VAT matches the rates on the lines." if ok
            else f"The line VAT rates give {_money(expected)} VAT, but the document says {_money(vat)}.",
            "vat_total",
        ))

    if total is None:
        checks.append(Check("total_present", False, "No total amount was found.", "total"))

    currency = data.get("currency")
    if currency is not None:
        ok = isinstance(currency, str) and currency.upper() in ISO_CURRENCIES
        checks.append(Check("currency", ok, f"Currency {currency} is a known ISO code." if ok else f"'{currency}' is not a recognised currency code.", "currency"))
    else:
        checks.append(Check("currency", False, "No currency was found.", "currency"))

    issue, due = _parse_date(data.get("issue_date")), _parse_date(data.get("due_date"))
    if data.get("issue_date") and issue is None:
        checks.append(Check("issue_date", False, "The issue date is not a valid date.", "issue_date"))
    if data.get("due_date") and due is None:
        checks.append(Check("due_date", False, "The due date is not a valid date.", "due_date"))
    if issue and due:
        checks.append(Check("date_order", due >= issue, "The due date is on or after the issue date." if due >= issue else "The due date is before the issue date.", "due_date"))

    iban = data.get("iban")
    if iban:
        ok = iban_valid(iban)
        checks.append(Check("iban", ok, "The IBAN checksum is valid." if ok else "The IBAN checksum is not valid. Check it against the document.", "iban"))

    for field in data.get("uncertain_fields") or []:
        checks.append(Check(f"uncertain:{field}", False, f"The model was unsure about '{field}'. Check it against the document.", field))

    return checks


def summary(checks: list[Check]) -> dict:
    failed = [c for c in checks if not c.ok]
    return {"passed": len(checks) - len(failed), "failed": len(failed), "checks": [c.as_dict() for c in checks]}
