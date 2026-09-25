# Windows setup — standard Python and a local demo store

Run commands from the repository root in PowerShell. Any checkout directory works; no `C:\AI`, Codex, ComfyUI or shared llama installation is required. Use Python 3.10+ with pip/venv, Git and (for the store only) Docker Desktop with Compose.

## Python and offline validation

```powershell
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e .
& .\.venv\Scripts\python.exe scripts/run-tests.py
& .\.venv\Scripts\woo-sync.exe validate data/catalog.json
```

Using full executable paths avoids activation-policy changes. If desired, activate with `.\.venv\Scripts\Activate.ps1` and use `python`, `woo-sync` and `woo-ai`. Runtime uses the standard library; pip may download setuptools during package build. No global package installation is needed.

## Fresh WordPress / WooCommerce setup

Existing local installations should keep `.env`, credentials and Docker volumes; do not rerun first-time configuration unnecessarily. For a new clone:

1. Copy `.env.example` to `.env`. Replace both placeholder database passwords with different, locally generated random values; never commit `.env`.
2. Run `docker compose up -d`. Open `http://localhost:8090` and complete WordPress installation using a local test administrator and fictional contact data.
3. Install and activate WooCommerce through WordPress. Skip optional payments, advertising and integration plugins. Core plugin download requires internet; the repository does not bundle WordPress/WooCommerce or a database dump.
4. Run the demo deployment below. It configures PLN/Poland, theme, pages, categories, images and offline checkout. It changes this local demo store's settings and does not create the catalog products until explicit synchronization.

```powershell
.\scripts\deploy-local.ps1 -ConfigureDemo
& .\.venv\Scripts\python.exe scripts/build-demo-csv.py
```

The setup regenerates `data/media.local.json` for this database. The manifest and generated CSV can differ from the example IDs committed in the repository. Port 8090 is bound to `127.0.0.1`. Volumes persist the database and WordPress files; `docker compose stop` preserves them. Do not use `docker compose down -v` on a store whose data you want to keep.

## Local REST credentials without displaying keys

On a newly configured local store, this helper creates the fictional `lab_sync` shop-manager account and one Read/Write REST key. It refuses to silently rotate an existing key. Never use it on a public store.

```powershell
New-Item -ItemType Directory -Force .secrets | Out-Null
docker compose cp scripts/create-local-key.php wordpress:/tmp/lab-create-key.php
docker compose exec -T wordpress php /tmp/lab-create-key.php
docker compose cp wordpress:/tmp/lab-credentials.json .secrets/woocommerce.json
docker compose exec -T wordpress rm -f /tmp/lab-credentials.json /tmp/lab-create-key.php
```

Run each command only if the preceding command succeeds. If the helper reports an existing key, keep the existing private credential file; it cannot recover the original consumer key from the database. Revoke/regenerate deliberately through WooCommerce if credentials were lost. Do not print the JSON, put it in product data or include it in screenshots. Local account/filesystem permissions should restrict access to it.

The CLI also accepts `WC_URL`, `WC_CONSUMER_KEY`, `WC_CONSUMER_SECRET`, or `--credentials` pointing at another local private JSON file. It does not load `.env` automatically. Loopback HTTP uses OAuth 1.0a; public endpoints must use HTTPS.

## Review and create the fictional catalog

```powershell
& .\.venv\Scripts\woo-sync.exe validate data/catalog.json
& .\.venv\Scripts\woo-sync.exe sync data/catalog.json --stock-authority woocommerce
# Review the plan before this explicit write:
& .\.venv\Scripts\woo-sync.exe sync data/catalog.json --stock-authority woocommerce --apply
# Repeat to verify SKIP when nothing has changed:
& .\.venv\Scripts\woo-sync.exe sync data/catalog.json --stock-authority woocommerce
```

Inspect `/sklep/`, product pages, `/koszyk/` and `/zamowienie/`. Use fictional contact details only. Demo checkout records a local order with an offline payment method and blocks email delivery. It is not a real sale. Stock may decrease after checkout; WooCommerce stock ownership prevents catalog refreshes from restoring it.

## AI and historical environment

Start with the [offline demo workflow](../README.md#ai-workflow). Optional local inference needs your own compatible llama.cpp server on loopback; configure `LLAMACPP_BASE_URL` and `LLAMACPP_MODEL`. Models and the shared server are outside this Compose project. OpenAI requires a separately supplied local environment key and is optional.

The [Stage 3 guide](stage3-ai-content.md) preserves the embedded-Python commands used during the original local acceptance test. They are historical alternatives, not installation dependencies. [llama.cpp security review](llamacpp-security-review.md) records the shared host's actual configuration; do not copy its broad port binding into a new setup.

`scripts/verify-live.py` and `scripts/verify-api-failure.py` are stateful acceptance helpers from Stage 1. They write to the configured store and assume particular initial data; they are not general health checks or offline tests.
