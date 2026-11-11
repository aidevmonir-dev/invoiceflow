# InvoiceFlow

Turn invoices and receipts into checked, approved data.

Upload a PDF or a photo. InvoiceFlow reads the supplier, dates, line items, VAT and totals, checks
that the numbers add up, and waits for a person to approve before anything is exported to CSV or
JSON.

Built by [Devomio](https://devomio.com/) as an open example of AI document extraction done the way
finance teams can trust: the model reads, the software checks, a person decides.

## What it does

- **Reads the document as it looks.** The PDF or image goes to Claude directly, so tables, layouts
  and stamps are read in context, not from a flattened text dump.
- **Returns data in a fixed shape.** Structured output guarantees valid JSON in one schema: supplier,
  customer, invoice number, dates, currency, line items with VAT rates, subtotal, VAT, total, IBAN
  and payment reference. Anything not on the document comes back empty instead of invented.
- **Checks the maths.** Quantity x price per line, lines against the subtotal, subtotal plus VAT
  against the total, VAT against the line rates, date order, currency code and the IBAN checksum.
  Fields the model was unsure about are flagged too.
- **A person approves.** The review screen shows the original next to the extracted values. Failed
  checks highlight the field concerned and update as you correct values. The original reading is
  kept, so corrections can be compared with it.
- **Exports what was approved.** CSV with one row per line item (the shape accounting imports
  expect, UTF-8 with BOM so Excel opens it correctly) and JSON.
- **Works without an API key.** Three fictional samples are built in, one with a deliberate error
  printed on it. Without a key they load the values printed on them, labelled as a stored example,
  and uploads can be entered by hand.
- **Safe to expose publicly.** File type detected from content, size and page limits, per-visitor
  and site-wide daily limits, documents private to the browser session and deleted after 24 hours.

## How it works

```
PDF / photo  ->  type check, size and page limits  ->  stored privately for the review screen
             ->  Claude reads it with a JSON schema  ->  normalised into the schema's shape
             ->  checks run  ->  a person corrects and approves  ->  CSV / JSON export
```

| File | Role |
|---|---|
| `invoices/services/schema.py` | The JSON schema sent to the model, and the normaliser for model and form input |
| `invoices/services/extract.py` | The Claude call: document or image block, instructions, structured output |
| `invoices/services/checks.py` | Arithmetic and format checks, including the IBAN mod-97 checksum |
| `invoices/services/files.py` | Upload validation (magic bytes, size, PDF pages), storage and expiry |
| `invoices/views.py` | Pages, the JSON API used by the review screen, and the exports |
| `tools/make_samples.py` | Generates the three fictional sample documents (needs Pillow) |

## Run it locally

Requires Python 3.12 or newer.

```bash
git clone https://github.com/aidevmonir-dev/invoiceflow.git
cd invoiceflow
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
cp .env.example .env                             # set DEBUG=1 and your ANTHROPIC_API_KEY
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000/ and pick a sample, or upload your own document.

### With Docker

```bash
cp .env.example .env      # set SECRET_KEY, ANTHROPIC_API_KEY, ALLOWED_HOSTS=localhost
docker compose up --build
```

## Configuration

All settings come from environment variables or a `.env` file. See [.env.example](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Claude API key. Empty means samples show stored values and uploads are entered by hand. |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Any current Claude model with structured output support. |
| `ANTHROPIC_EFFORT` | `medium` | How much reasoning the model spends per document. |
| `MAX_FILE_BYTES` / `MAX_PAGES` | 8 MB / 10 | Upload limits (images up to 5 MB). |
| `EXTRACTIONS_PER_IP_PER_DAY` | `15` | Daily limit per visitor. |
| `EXTRACTIONS_PER_DAY_TOTAL` | `200` | Daily limit for the whole site. |
| `RETENTION_HOURS` | `24` | How long uploaded documents are kept. |

## Tests

```bash
DEBUG=1 python manage.py test
```

The tests cover every check (including the deliberate error in the sample receipt), the IBAN
checksum, input normalisation, the request sent to the model, failure handling, file type detection,
session privacy, approval locking, the exports, rate limits and expiry. The Claude API is replaced
by a fake client, so they run offline and cost nothing.

## Data handling

- Uploaded files are stored privately on the server so the reviewer can see them, and are deleted
  with their data after `RETENTION_HOURS`. Run `python manage.py purge_expired` from cron.
- Documents belong to one browser session. Other visitors cannot open, export or delete them.
- The document is sent to the Claude API to be read. For data that must stay on your own servers,
  replace the client in `invoices/services/extract.py` with a local vision model.

## Limits of this demo

- One document per upload. Batch processing and email inboxes are the usual next step.
- Multi-page PDFs are read in one pass, which suits invoices, not 50-page statements.
- The checks catch inconsistent numbers, not a wrong number that is consistently wrong everywhere.
  That is what the human review is for.

## Need this for your business?

Devomio builds production versions: your document types and fields, posting to your accounting or
ERP system, approval rules, Swiss QR-bill and e-invoice formats, and hosting in Switzerland or the
EU. See [devomio.com](https://devomio.com/) or write to hello@devomio.com.

## Licence

MIT. See [LICENSE](LICENSE). The sample documents are fictional.
