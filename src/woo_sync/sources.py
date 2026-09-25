"""Input adapters producing the same validated ProductRow representation."""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .core import ValidationError, load_csv, load_records


def load_json_catalog(
    path,
    media_path=None,
):
    """Load canonical catalog JSON and resolve local asset names to image IDs."""

    path = Path(path)
    media_path = (
        Path(media_path)
        if media_path is not None
        else path.with_name("media.local.json")
    )

    try:
        catalog = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "Nieprawidłowy katalog JSON"
        ) from exc

    if not isinstance(catalog, list):
        raise ValidationError(
            "Katalog JSON musi być tablicą produktów"
        )

    uses_assets = any(
        isinstance(product, dict) and product.get("asset")
        for product in catalog
    )

    media = {}

    if uses_assets:
        try:
            media = json.loads(
                media_path.read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError(
                "Nie można odczytać manifestu mediów"
            ) from exc

        if not isinstance(media, dict):
            raise ValidationError(
                "Manifest mediów musi być obiektem JSON"
            )

    records = []

    for number, product in enumerate(catalog, start=1):

        if not isinstance(product, dict):
            raise ValidationError(
                f"Wiersz {number}: produkt JSON musi być obiektem"
            )

        data = dict(product)

        asset = data.pop("asset", None)

        if asset:
            if data.get("image_id") or data.get("image_url"):
                raise ValidationError(
                    f"Wiersz {number}: asset nie może być łączony "
                    "z image_id ani image_url"
                )

            asset = str(asset)

            if asset not in media:
                raise ValidationError(
                    f"Wiersz {number}: nieznany asset: {asset}"
                )

            data["image_id"] = str(media[asset])

        records.append((number, data))

    return load_records(records)


MAX_SHEET_BYTES = 5 * 1024 * 1024


def _validate_google_sheet_url(url, allow_content_host=False):
    parsed = urllib.parse.urlsplit(str(url))

    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ValidationError(
            "Google Sheets wymaga bezpiecznego adresu HTTPS"
        )

    host = parsed.hostname.lower()

    allowed = host == "docs.google.com"

    if allow_content_host:
        allowed = (
            allowed
            or host == "googleusercontent.com"
            or host.endswith(".googleusercontent.com")
        )

    if not allowed:
        raise ValidationError(
            "Dozwolone są wyłącznie adresy Google Sheets"
        )

    if host == "docs.google.com" and not parsed.path.startswith(
        "/spreadsheets/"
    ):
        raise ValidationError(
            "Nieprawidłowy adres Google Sheets"
        )

    return parsed


class _GoogleRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        _validate_google_sheet_url(
            newurl,
            allow_content_host=True,
        )

        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


def load_google_sheet(url, timeout=20):
    """Download a public Google Sheet as CSV and validate its rows."""

    _validate_google_sheet_url(url)

    request = urllib.request.Request(
        str(url),
        headers={
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": "WooCommerceProductAutomationLab/1.0",
        },
    )

    opener = urllib.request.build_opener(
        _GoogleRedirectHandler()
    )

    try:
        with opener.open(
            request,
            timeout=timeout,
        ) as response:
            payload = response.read(
                MAX_SHEET_BYTES + 1
            )

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise ValidationError(
            "Nie można pobrać Google Sheets"
        ) from exc

    if len(payload) > MAX_SHEET_BYTES:
        raise ValidationError(
            "Google Sheets przekracza limit 5 MiB"
        )

    try:
        content = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValidationError(
            "Google Sheets nie zwrócił poprawnego UTF-8"
        ) from exc

    try:
        reader = csv.DictReader(
            io.StringIO(content),
            strict=True,
        )

        names = reader.fieldnames or []

        records = [
            (reader.line_num, row)
            for row in reader
        ]

    except csv.Error as exc:
        raise ValidationError(
            "Nieprawidłowy CSV z Google Sheets"
        ) from exc

    return load_records(
        records,
        names,
    )

def load_source(
    path,
    source_type="auto",
    media_path=None,
):
    """Dispatch an input file to the appropriate source adapter."""

    raw = str(path)

    if source_type == "auto":
        if raw.startswith(("https://", "http://")):
            source_type = "sheets"
        else:
            suffix = Path(raw).suffix.lower()

            if suffix == ".csv":
                source_type = "csv"
            elif suffix == ".json":
                source_type = "json"
            else:
                raise ValidationError(
                    "Nie można rozpoznać typu źródła; "
                    "użyj CSV, JSON albo Google Sheets"
                )

    if source_type == "csv":
        return load_csv(Path(raw))

    if source_type == "json":
        return load_json_catalog(
            Path(raw),
            media_path=media_path,
        )

    if source_type == "sheets":
        return load_google_sheet(raw)

    raise ValidationError(
        f"Nieobsługiwany typ źródła: {source_type}"
    )
