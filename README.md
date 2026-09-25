# WooCommerce Product Automation Lab

Lokalny projekt portfolio łączący sklep **Biurko / Lab**, deterministyczną synchronizację produktów i **propozycje treści AI wymagające review**. Nic nie jest publikowane automatycznie.

- **Stage 1 / v1.0.0:** WordPress, WooCommerce i MariaDB w Dockerze; autorski sklep, katalog, koszyk i fikcyjny checkout. CSV → CREATE / UPDATE / SKIP, REST v3 po SKU, OAuth dla lokalnego HTTP.
- **Stage 2 / v1.1.0:** canonical `data/catalog.json`, adaptery CSV / JSON / publiczny Google Sheets CSV, wspólna walidacja, polityka właściciela stanu i raporty RUN_SUMMARY.
- **Stage 3 / gałąź do review:** demo, OpenAI Responses oraz rzeczywisty lokalny llama.cpp; pending → review → approved/rejected → fingerprint → walidowany CSV → zwykły WooCommerce PLAN.

## Uruchomienie sklepu

```powershell
Set-Location C:\AI\WooCommerceProductAutomationLab
docker compose up -d
```

Sklep: http://localhost:8090; panel: http://localhost:8090/wp-admin/. Port WordPressa jest przypięty do `127.0.0.1`. Wolumeny przechowują dane; nie używaj `docker compose down -v`.

## Synchronizacja

W standardowym Pythonie 3.10+ można utworzyć `.venv` i wykonać `python -m pip install -e .`. Runtime synchronizatora i providerów korzysta wyłącznie z biblioteki standardowej.

```powershell
woo-sync validate data/catalog.json
woo-sync sync data/catalog.json --stock-authority woocommerce
# Zapis wymaga osobnej świadomej decyzji:
woo-sync sync data/catalog.json --stock-authority woocommerce --apply
```

Domyślnie `sync` wykonuje PLAN: wszystkie produkty są walidowane i planowane przed pierwszym ewentualnym zapisem. PUT zawiera tylko różniące się pola; SKIP nie zapisuje. JSONL zawiera różnice przed/po, ID, operacje, błędy oraz podsumowanie run_id/duration_ms/liczników żądań. Kody wyjścia: 0 sukces, 1 błąd API, 2 walidacja/konfiguracja.

Wymagane pola: `sku,name,regular_price,stock_quantity,status`. Obsługiwane opcjonalne: `description,short_description,categories,image_id,image_url,image_alt`. UTF-8, CSV oddzielany przecinkiem, kwoty z kropką. Kategorie wskazują istniejące slugi rozdzielone `|`; JSON może mapować `asset` przez `data/media.local.json`. Brak opcjonalnego pola oznacza brak zarządzania nim, co jest różne od pustej wartości. Tylko produkty simple; warianty i promocje poza zakresem.

Domyślny `--stock-authority source` traktuje stan z pliku jako nadrzędny. `woocommerce` zachowuje stan istniejących produktów po sprzedaży (nowy produkt otrzymuje stan początkowy ze źródła). Jest to istotne przy planowaniu aktualizacji treści.

## Lokalne AI

```powershell
woo-ai propose tmp/one-product.json --media data/media.local.json --provider llamacpp --out tmp/proposal.json
# Przejrzyj treść, następnie jawnie approve albo reject:
woo-ai approve tmp/proposal.json BL-KEY-01
woo-ai apply-proposal data/catalog.json tmp/proposal.json --out tmp/reviewed.csv
woo-sync sync tmp/reviewed.csv --stock-authority woocommerce
```

`apply-proposal` oznacza wyłącznie lokalną materializację CSV, nie zapis do WooCommerce. Domyślny lokalny endpoint to `http://127.0.0.1:8080`, model alias `jarvis-qwen35-9b`. Konfiguracja przez `LLAMACPP_BASE_URL` / `LLAMACPP_MODEL`, bez klucza API. Provider wymusza loopback, blokuje przekierowania/proxy i ogranicza odpowiedź. AI nie może zmieniać nazwy, ceny, stanu ani statusu. Prompt nie zastępuje rzeczowego review.

OpenAI jest opcjonalny (`--provider openai`, `OPENAI_API_KEY`, opcjonalne `OPENAI_MODEL`) i ma testy mockowane; lokalny E2E nie potrzebuje credits.

## Testy bez instalacji do embedded Pythona

```powershell
& 'C:\AI\ComfyUI_windows_portable\python_embeded\python.exe' -X utf8 scripts/run-tests.py
```

Runner sam dodaje `src/` do ścieżki importu. Nie wymaga pip ani zmiany embedded runtime. Aktualny wynik: **89 testów OK**. Szczegółowe polecenia CLI dla embedded Pythona są w dokumentacji Stage 3.

Rzeczywisty lokalny E2E: **CREATE 0 / UPDATE 1 / SKIP 5 / ERROR 0; GET 7 / POST 0 / PUT 0**. Zmieniają się tylko dwa opisy BL-KEY-01 w planie; sklep nie został zapisany. Dowód zawiera też blokady pending, stale source i edycji treści po approval.

## Sekrety i granice demonstracji

Dane WooCommerce są pobierane z ignorowanego `.secrets/woocommerce.json` lub zmiennych `WC_URL`, `WC_CONSUMER_KEY`, `WC_CONSUMER_SECRET`. `.env` służy Compose; Python nie wczytuje go automatycznie. Nie wpisuj kluczy do źródeł produktów, dokumentacji i Git. Publiczne sklepy wymagają HTTPS; lokalny HTTP korzysta z OAuth 1.0a bez przesyłania sekretu.

Sklep używa fikcyjnych danych, metody offline, nie pobiera pieniędzy ani nie wysyła e-maili. Shared llama.cpp pozostaje skonfigurowany poza tym repo; jego szeroka ekspozycja portu została opisana z rekomendacją osobnej migracji, bez przerywania innych usług.

## Dokumentacja i dowody

- [Architektura](docs/architecture.md)
- [Stage 2 — źródła i polityka stanu](docs/stage2-data-pipeline.md)
- [Stage 3 — workflow, Windows, grounding i ograniczenia](docs/stage3-ai-content.md)
- [Wynik prawdziwego lokalnego AI E2E](docs/stage3-local-ai-results.json)
- [Audyt bezpieczeństwa llama.cpp](docs/llamacpp-security-review.md)
- [Historyczny test Stage 3 demo](docs/stage3-ai-workflow-results.json)
- [Test API Stage 1](docs/api-test-results.json) i [checkout](docs/checkout-test-results.json)
