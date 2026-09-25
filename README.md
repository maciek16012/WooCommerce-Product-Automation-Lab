# WooCommerce Product Automation Lab

Pierwszy kamień milowy: walidacja CSV i synchronizacja prostych produktów przez WooCommerce REST API v3. SKU jest kluczem dopasowania. Nowy produkt zostaje utworzony, zmieniony otrzymuje aktualizację tylko różniących się pól, a identyczny jest pomijany. Raport każdej operacji zapisuje się w JSONL.

## Uruchomienie

Wymagany Python 3.10+ i sklep WordPress z WooCommerce, adresem HTTPS, włączonymi przyjaznymi odnośnikami oraz kluczem REST API z uprawnieniem **Read/Write**. W katalogu projektu:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
woo-sync validate data/products.example.csv
```

Ustaw dane środowiskowe w terminalu. Plik `.env.example` jest wzorem, program nie wczytuje `.env` samoczynnie. Nie wpisuj kluczy do CSV ani do repozytorium.

PowerShell:

```powershell
$env:WC_URL = "https://twoj-sklep.example"
$env:WC_CONSUMER_KEY = "ck_..."
$env:WC_CONSUMER_SECRET = "cs_..."
woo-sync sync data/products.example.csv
woo-sync sync data/products.example.csv --apply
```

Bash:

```bash
export WC_URL="https://twoj-sklep.example"
export WC_CONSUMER_KEY="ck_..."
export WC_CONSUMER_SECRET="cs_..."
woo-sync sync data/products.example.csv
woo-sync sync data/products.example.csv --apply
```

Pierwsze `sync` jest **planem**: odczytuje istniejące produkty i raportuje CREATE/UPDATE/SKIP, lecz niczego nie zapisuje. `--apply` wykonuje zapis. Najpierw użyj osobnego sklepu testowego lub produktów ze statusem `draft`. Aby produkty stały się widoczne, ustaw `status=publish` w CSV i świadomie uruchom `--apply`. Dla własnego pliku użyj `woo-sync sync moja_lista.csv --log raport.jsonl`.

## Format CSV

Nagłówek dokładnie: `sku,name,regular_price,stock_quantity,status`. UTF-8, przecinek jako separator, kropka dziesiętna, cena z maksymalnie dwiema cyframi po kropce, stan całkowity nieujemny, status `draft`, `publish`, `pending` lub `private`. Każde SKU w pliku musi być unikalne. CSV jest w całości walidowany przed pierwszym wywołaniem API.

Synchronizator zarządza nazwą, regularną ceną, stanem magazynowym (`manage_stock=true`) i statusem prostego produktu. Pozostałych pól istniejącego produktu nie zmienia. Nie obsługuje jeszcze wariantów, kategorii, obrazów, cen promocyjnych i opisów. API może normalizować niektóre pola, dlatego raport `SKIP` oznacza zgodność pól objętych tą wersją, nie całego produktu.

Raport w `logs/sync-*.jsonl` zawiera po jednym wierszu na SKU: `action`, `mode`, zmienione `fields`, identyfikator produktu lub błąd. Przy błędach wyjście ma kod 1; błędny CSV lub konfiguracja daje kod 2. Jeśli POST/PUT zwróci błąd sieci po wysłaniu żądania, sprawdź produkt w WooCommerce przed ponowieniem. Program nie ponawia automatycznie zapisów.

## Testy

```bash
python -m unittest discover -s tests -v
```

## Następne etapy

Kategorie i obrazy z ALT, opisy, źródło Google Sheets, raporty jakości danych, SEO i pomiary wydajności sklepu. Osobny moduł AI powstanie po uruchomieniu podstawowej synchronizacji i będzie wymagał zatwierdzenia treści przez człowieka.

Dokumentacja pól i uwierzytelniania: [WooCommerce Products v3](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/) · [Authentication](https://developer.woocommerce.com/docs/apis/rest-api/authentication/).
