"""Generate the three fictional sample documents in invoices/samples/ (needs Pillow; dev-only).

Run from the project root:  python tools/make_samples.py
Writes the PNG files and samples.json, which holds the values printed on each document. The app shows
those stored values only when no AI model is connected, and labels them as a stored example.
"""
from __future__ import annotations

import json
import string
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "invoices" / "samples"
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(names: list[str], size: int):
    for directory in FONT_DIRS:
        for name in names:
            path = directory / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


REG = lambda s: font(["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"], s)  # noqa: E731
BOLD = lambda s: font(["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"], s)  # noqa: E731


def iban(country: str, bban: str) -> str:
    """Make a checksum-valid IBAN for a fictional account number."""
    numeric = "".join(str(int(c, 36)) for c in bban + country + "00")
    check = 98 - int(numeric) % 97
    raw = f"{country}{check:02d}{bban}"
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def money(value: float, decimal: str = ".", thousands: str = "'") -> str:
    whole, frac = f"{value:,.2f}".split(".")
    return whole.replace(",", thousands) + decimal + frac


class Page:
    def __init__(self, width=1240, height=1754):
        self.img = Image.new("RGB", (width, height), "white")
        self.d = ImageDraw.Draw(self.img)

    def text(self, xy, value, size=26, bold=False, fill="#1d2733", anchor="la"):
        self.d.text(xy, value, font=(BOLD if bold else REG)(size), fill=fill, anchor=anchor)

    def line(self, y, x0=90, x1=1150, fill="#9aa5b1", width=2):
        self.d.line([(x0, y), (x1, y)], fill=fill, width=width)


def swiss_invoice():
    p = Page()
    acct = iban("CH", "0483" + "5012" + "3456" + "7800" + "9")
    p.d.rectangle([(90, 90), (190, 190)], fill="#c0392b")
    p.text((140, 140), "AK", 44, True, "white", "mm")
    p.text((220, 100), "Alpenkraft Software GmbH", 34, True)
    p.text((220, 145), "Bahnhofstrasse 21, 8001 Zürich", 24)
    p.text((220, 180), "MWST/VAT: CHE-123.456.789 MWST", 24)
    p.text((90, 290), "RECHNUNG / INVOICE", 44, True, "#c0392b")
    p.text((90, 370), "Bill to:", 24, True)
    for i, row in enumerate(["Seeblick Hotel AG", "Seestrasse 5", "6006 Luzern"]):
        p.text((90, 405 + i * 34), row, 24)
    for i, (k, v) in enumerate([("Invoice no.", "AK-2026-0417"), ("Invoice date", "03.11.2026"), ("Due date", "03.12.2026"), ("Customer no.", "K-1180")]):
        p.text((760, 370 + i * 36), k, 24, True)
        p.text((1150, 370 + i * 36), v, 24, anchor="ra")
    y = 590
    p.line(y, width=3, fill="#1d2733")
    for x, h, a in [(90, "Description", "la"), (760, "Qty", "ra"), (930, "Unit price", "ra"), (1150, "Amount", "ra")]:
        p.text((x, y + 14), h, 24, True, anchor=a)
    p.line(y + 56)
    lines = [("Booking system licence, annual", 1, 2400.00), ("Implementation and data migration (hours)", 12, 145.00), ("Staff training session", 2, 380.00)]
    y += 70
    for desc, qty, price in lines:
        p.text((90, y), desc, 24)
        p.text((760, y), str(qty), 24, anchor="ra")
        p.text((930, y), money(price), 24, anchor="ra")
        p.text((1150, y), money(qty * price), 24, anchor="ra")
        y += 46
    subtotal = sum(q * pr for _, q, pr in lines)
    vat = round(subtotal * 0.081, 2)
    total = round(subtotal + vat, 2)
    p.line(y + 10)
    y += 30
    for label, value, bold in [("Subtotal", subtotal, False), ("MWST 8.1%", vat, False), ("Total CHF", total, True)]:
        p.text((930, y), label, 26, bold, anchor="ra")
        p.text((1150, y), money(value), 26, bold, anchor="ra")
        y += 44
    p.text((90, y + 60), "Payment within 30 days to:", 24, True)
    p.text((90, y + 96), f"IBAN {acct}  ·  Zürcher Testbank AG", 24)
    p.text((90, y + 132), "Reference: AK-2026-0417", 24)
    p.text((90, 1660), "Fictional sample document for the InvoiceFlow demo. Not a real company or invoice.", 20, fill="#8a96a3")
    data = {
        "document_type": "invoice",
        "supplier": {"name": "Alpenkraft Software GmbH", "address": "Bahnhofstrasse 21, 8001 Zürich", "vat_id": "CHE-123.456.789 MWST"},
        "customer": {"name": "Seeblick Hotel AG", "address": "Seestrasse 5, 6006 Luzern", "vat_id": None},
        "invoice_number": "AK-2026-0417", "issue_date": "2026-11-03", "due_date": "2026-12-03", "currency": "CHF",
        "line_items": [{"description": d, "quantity": q, "unit_price": pr, "amount": round(q * pr, 2), "vat_rate": 8.1} for d, q, pr in lines],
        "subtotal": subtotal, "vat_total": vat, "total": total, "iban": acct, "payment_reference": "AK-2026-0417", "uncertain_fields": [],
    }
    return p, data


def german_invoice():
    p = Page()
    acct = iban("DE", "37040044" + "0532013000")
    p.text((90, 100), "Druckerei Weber & Söhne", 38, True, "#1f4e79")
    p.text((90, 150), "Hafenstraße 8 · 20457 Hamburg · USt-IdNr. DE298765432", 22)
    p.text((90, 260), "Rechnung", 46, True)
    for i, row in enumerate(["An:", "Café Lindenblatt GmbH", "Kastanienallee 12", "10435 Berlin"]):
        p.text((90, 350 + i * 34), row, 24, i == 0)
    for i, (k, v) in enumerate([("Rechnungsnr.", "2026-1182"), ("Datum", "28.10.2026"), ("Fällig am", "11.11.2026")]):
        p.text((760, 350 + i * 36), k, 24, True)
        p.text((1150, 350 + i * 36), v, 24, anchor="ra")
    y = 560
    p.line(y, width=3, fill="#1d2733")
    for x, h, a in [(90, "Leistung", "la"), (640, "Menge", "ra"), (800, "Einzelpreis", "ra"), (920, "USt", "ra"), (1150, "Betrag", "ra")]:
        p.text((x, y + 14), h, 24, True, anchor=a)
    p.line(y + 56)
    lines = [("Speisekarten A4, laminiert", 40, 4.50, 19), ("Flyer A6, 2.500 Stück", 1, 189.00, 19), ("Visitenkarten, 500 Stück", 2, 39.90, 19), ("Broschüre „Unsere Geschichte“", 50, 2.80, 7)]
    y += 70
    for desc, qty, price, rate in lines:
        p.text((90, y), desc, 24)
        p.text((640, y), str(qty), 24, anchor="ra")
        p.text((800, y), money(price, ",", "."), 24, anchor="ra")
        p.text((920, y), f"{rate} %", 24, anchor="ra")
        p.text((1150, y), money(qty * price, ",", "."), 24, anchor="ra")
        y += 46
    subtotal = round(sum(q * pr for _, q, pr, _ in lines), 2)
    vat19 = round(sum(q * pr for _, q, pr, r in lines if r == 19) * 0.19, 2)
    vat7 = round(sum(q * pr for _, q, pr, r in lines if r == 7) * 0.07, 2)
    total = round(subtotal + vat19 + vat7, 2)
    p.line(y + 10)
    y += 30
    for label, value, bold in [("Nettobetrag", subtotal, False), ("USt 19 %", vat19, False), ("USt 7 %", vat7, False), ("Gesamtbetrag EUR", total, True)]:
        p.text((920, y), label, 26, bold, anchor="ra")
        p.text((1150, y), money(value, ",", "."), 26, bold, anchor="ra")
        y += 44
    p.text((90, y + 60), f"Bitte überweisen Sie den Betrag bis zum 11.11.2026 auf: IBAN {acct}", 22)
    p.text((90, y + 96), "Verwendungszweck: RE 2026-1182", 22)
    p.text((90, 1660), "Fictional sample document for the InvoiceFlow demo. Not a real company or invoice.", 20, fill="#8a96a3")
    data = {
        "document_type": "invoice",
        "supplier": {"name": "Druckerei Weber & Söhne", "address": "Hafenstraße 8, 20457 Hamburg", "vat_id": "DE298765432"},
        "customer": {"name": "Café Lindenblatt GmbH", "address": "Kastanienallee 12, 10435 Berlin", "vat_id": None},
        "invoice_number": "2026-1182", "issue_date": "2026-10-28", "due_date": "2026-11-11", "currency": "EUR",
        "line_items": [{"description": d, "quantity": q, "unit_price": pr, "amount": round(q * pr, 2), "vat_rate": r} for d, q, pr, r in lines],
        "subtotal": subtotal, "vat_total": round(vat19 + vat7, 2), "total": total, "iban": acct, "payment_reference": "RE 2026-1182", "uncertain_fields": [],
    }
    return p, data


def receipt_with_error():
    """A till receipt whose printed total is wrong, so the demo can show a failed check."""
    p = Page(720, 1150)
    p.text((360, 70), "BÄCKEREI SONNENHOF", 34, True, anchor="mm")
    p.text((360, 115), "Marktgasse 3, 3011 Bern", 22, anchor="mm")
    p.text((360, 148), "CHE-987.654.321 MWST", 22, anchor="mm")
    p.text((60, 210), "Beleg 4471      12.11.2026  08:42", 24)
    p.line(255, 60, 660)
    lines = [("Gipfeli", 4, 1.80), ("Bürli", 2, 1.40), ("Zopf 500 g", 1, 6.90), ("Café crème", 2, 4.60)]
    y = 285
    for desc, qty, price in lines:
        p.text((60, y), f"{qty} x {desc}", 24)
        p.text((660, y), money(qty * price), 24, anchor="ra")
        y += 42
    correct = round(sum(q * pr for _, q, pr in lines), 2)
    printed_total = round(correct + 1.00, 2)  # deliberate error on the printed receipt
    vat = round(printed_total - printed_total / 1.026, 2)
    p.line(y + 10, 60, 660)
    y += 34
    p.text((60, y), "TOTAL CHF", 30, True)
    p.text((660, y), money(printed_total), 30, True, anchor="ra")
    p.text((60, y + 56), f"inkl. MWST 2.6%: {money(vat)}", 22)
    p.text((60, y + 92), "Bezahlt: TWINT", 22)
    p.text((360, y + 170), "Merci und bis bald!", 24, anchor="mm")
    p.text((360, 1100), "Fictional sample for the InvoiceFlow demo", 18, fill="#8a96a3", anchor="mm")
    data = {
        "document_type": "receipt",
        "supplier": {"name": "Bäckerei Sonnenhof", "address": "Marktgasse 3, 3011 Bern", "vat_id": "CHE-987.654.321 MWST"},
        "customer": {"name": None, "address": None, "vat_id": None},
        "invoice_number": "4471", "issue_date": "2026-11-12", "due_date": None, "currency": "CHF",
        "line_items": [{"description": d, "quantity": q, "unit_price": pr, "amount": round(q * pr, 2), "vat_rate": 2.6} for d, q, pr in lines],
        "subtotal": None, "vat_total": vat, "total": printed_total, "iban": None, "payment_reference": None, "uncertain_fields": [],
    }
    return p, data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalogue = {}
    for key, title, builder in [
        ("swiss-invoice", "Software invoice, Zürich (CHF, 8.1% VAT)", swiss_invoice),
        ("german-invoice", "Print shop invoice, Hamburg (EUR, 19% and 7% VAT)", german_invoice),
        ("bakery-receipt", "Bakery receipt, Bern (total printed wrong)", receipt_with_error),
    ]:
        page, data = builder()
        filename = f"{key}.png"
        page.img.save(OUT / filename, optimize=True)
        catalogue[key] = {"title": title, "file": filename, "values": data}
        print("wrote", filename)
    (OUT / "samples.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=1), encoding="utf-8")
    assert all(ch in string.printable or ord(ch) > 127 for ch in json.dumps(catalogue))


if __name__ == "__main__":
    main()
