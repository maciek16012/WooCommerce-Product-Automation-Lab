# WooCommerce Product Automation Lab — portfolio case study

## Problem

Catalog automation has to reconcile source data with a running shop: avoid duplicate products, preserve stock reduced by checkout and prevent unreviewed generated claims from reaching product pages. This personal engineering lab explores those boundaries using a fictional Polish desk-accessory store, not a client engagement.

## Architecture

WordPress, WooCommerce and MariaDB run locally in Docker. A custom theme presents six products in three categories. CSV, canonical JSON and public Google Sheets CSV adapters feed one validated `ProductRow` model and a SKU-based WooCommerce REST v3 planner. An optional AI branch creates reviewable proposals and materializes approved content into the same input pipeline. See the [complete flow](../README.md#architecture).

## Engineering decisions

- Match by SKU and send only changed fields. A second unchanged run is SKIP and produces no writes.
- Default to a dry-run PLAN; writes require explicit APPLY. The write invocation replans against current data.
- Make stock ownership explicit: source or WooCommerce. Store ownership preserves stock after orders while allowing initial stock for new products.
- Validate all input and preflight the full plan before writes. Retry transient GET failures, never automatically retry writes with an uncertain outcome.
- Use the standard Python library for runtime adapters, authentication and providers. JSONL reports retain operations, differences, run IDs, timing and request counts.

## Safety

Local HTTP uses loopback OAuth 1.0a signatures; public endpoints require verified HTTPS. Secrets are loaded from local ignored files or environment variables. AI runs do not write to WooCommerce. Proposals start pending, stale source fingerprints invalidate approval, and approval binds the exact proposed text. New proposal/CSV files are published atomically and CSV is validated before publication.

These controls do not provide multi-product rollback or defend against a malicious local filesystem owner. An API error during APPLY may occur after another product has been saved.

## AI integration

Providers include deterministic offline demo, optional OpenAI Responses and local llama.cpp structured output. AI may propose only description, short description and image ALT, never price, stock, SKU or status. The verified local setup used the configurable alias `jarvis-qwen35-9b` through a llama.cpp-compatible server. The repository does not ship a model or infer a checkpoint from that alias.

Schema checks reject malformed output, not unsupported factual claims. Review remains necessary. In the recorded acceptance test, Codex performed review under the owner's delegated instruction; this is not evidence of independent human approval.

## Testing

The current functional baseline has **141 offline regression tests** covering source validation, diff planning, stock ownership, authentication/transport behavior, provider failures, review integrity and atomic materialization. The runner blocks real socket networking. CI is configured for Windows/Ubuntu and Python 3.10/3.13; hosted results will exist only after a future authorized publication.

Separate historical live tests exercised WooCommerce, guest checkout, public Sheets and the local model. No live services or credentials are required by CI. [Recorded local AI verification](stage3-local-ai-results.json).

## Verified E2E results

| Scenario | Recorded result |
|---|---|
| [WooCommerce update](api-test-results.json) | Price/stock updated; invalid CSV and HTTP 401 preserved all six products |
| [Offline checkout](checkout-test-results.json) | 179.00 PLN product + 12.90 PLN shipping = 191.90 PLN; no real payment or email |
| [Sheets PLAN](google-sheets-integration-results.json) | CREATE 0 / UPDATE 0 / SKIP 6 / ERROR 0; GET 7 / POST 0 / PUT 0 |
| [Local AI PLAN](stage3-local-ai-results.json) | CREATE 0 / UPDATE 1 / SKIP 5 / ERROR 0; GET 7 / POST 0 / PUT 0 |

The local AI run planned changes to two description fields for one SKU; product snapshots before and after matched. Pending proposals, changed source data and post-approval text edits were blocked. These are acceptance observations, not performance benchmarks.

## What this demonstrates

Integration across a real storefront, source adapters and REST API; explicit ownership of mutable business data; idempotent updates; observable runs; controlled failure handling; and separating AI generation, review, materialization and write permission. The value lies in the boundaries and evidence as well as the visible storefront.

## Limitations

Simple products only; existing categories required; no scheduling, cross-product transaction or production operations layer. Review hashes are local integrity checks, not authenticated human signatures. OpenAI is mock-tested, not part of the live local-model acceptance run. Filesystem hard-link support is required for atomic creation. Shared llama.cpp port exposure remains a separately documented environment issue; see [security review](llamacpp-security-review.md). Public source readiness does not make the shop production-ready.
