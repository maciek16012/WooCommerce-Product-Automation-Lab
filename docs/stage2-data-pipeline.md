# Stage 2 — Multi-source Product Data Pipeline

## Supported sources

- Local CSV
- Canonical JSON catalog
- Public read-only Google Sheets CSV endpoint

All sources are normalized to the same internal `ProductRow` representation and use the same validation and WooCommerce planning logic.

## Pipeline

```text
CSV -----------\
JSON -----------+--> source adapter --> shared validation --> ProductRow[] --> ownership policy --> planner --> WooCommerce REST API
Google Sheets --/
```

## Canonical catalog

`data/catalog.json` is the canonical local demo catalog.

`scripts/build-demo-csv.py` generates `data/products.csv` from the canonical catalog and `data/media.local.json`.

## Google Sheets

The Google Sheets adapter:

- accepts HTTPS only
- restricts remote sources to Google Sheets
- validates redirects
- limits responses to 5 MiB
- uses the same product validator as CSV and JSON
- requires no third-party Python packages

The demonstration sheet contains fictional product data only.

## Stock ownership

Two explicit stock policies are supported:

- `source` — the external source owns `stock_quantity`
- `woocommerce` — WooCommerce owns stock for existing products

With `woocommerce`, checkout and order processing can reduce stock without a later catalog synchronization restoring the previous quantity.

Verified case:

```text
Canonical stock:   21
WooCommerce stock: 19
Test orders:         2

stock-authority=source       -> UPDATE 19 -> 21
stock-authority=woocommerce  -> SKIP
```

## Safety

- PLAN mode by default
- writes require explicit `--apply`
- complete validation before writes
- SKU-based matching
- CREATE / UPDATE / SKIP planning
- no automatic write retries
- secrets excluded from logs
- synchronization locking
- JSONL execution reports

## Run reporting

Each run records:

- `run_id`
- source and source type
- PLAN or APPLIED mode
- stock ownership policy
- execution duration
- CREATE / UPDATE / SKIP / ERROR counts
- GET / POST / PUT request counts

The final JSONL record is `RUN_SUMMARY`.

## Verified Stage 2 result

Regression suite:

```text
29 tests
OK
```

Real Google Sheets -> WooCommerce integration:

```text
mode: PLAN
stock_authority: woocommerce
products: 6

CREATE: 0
UPDATE: 0
SKIP:   6
ERROR:  0

GET:  7
POST: 0
PUT:  0
```

No WooCommerce writes were performed during the final integration test.

Additional evidence: `docs/google-sheets-integration-results.json`.
