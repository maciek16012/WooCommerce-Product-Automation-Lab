"""Input adapters producing the same validated ProductRow representation."""

from __future__ import annotations

import json
from pathlib import Path

from .core import ValidationError, load_csv, load_records


def load_json_catalog(
    path,
    media_path=Path("data/media.local.json"),
):
    """Load canonical catalog JSON and resolve local asset names to image IDs."""

    path = Path(path)
    media_path = Path(media_path)

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


def load_source(
    path,
    source_type="auto",
    media_path=Path("data/media.local.json"),
):
    """Dispatch an input file to the appropriate source adapter."""

    path = Path(path)

    if source_type == "auto":
        suffix = path.suffix.lower()

        if suffix == ".csv":
            source_type = "csv"
        elif suffix == ".json":
            source_type = "json"
        else:
            raise ValidationError(
                "Nie można rozpoznać typu źródła; użyj CSV albo JSON"
            )

    if source_type == "csv":
        return load_csv(path)

    if source_type == "json":
        return load_json_catalog(
            path,
            media_path=media_path,
        )

    raise ValidationError(
        f"Nieobsługiwany typ źródła: {source_type}"
    )
