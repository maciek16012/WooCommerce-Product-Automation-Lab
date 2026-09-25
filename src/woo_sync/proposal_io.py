"""File-backed AI proposal workflow and approved-content materialization."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

from .content_proposals import validate_proposal
from .core import ProductRow, ValidationError

REQUIRED_CSV_FIELDS = (
    "sku",
    "name",
    "regular_price",
    "stock_quantity",
    "status",
)

OPTIONAL_CSV_FIELDS = (
    "description",
    "short_description",
    "categories",
    "image_id",
    "image_url",
    "image_alt",
)


def load_proposal(path):
    path = Path(path)

    try:
        proposal = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Nie można odczytać proposal JSON") from exc

    return validate_proposal(proposal)


def write_new_proposal(path, proposal):
    """Create a proposal without overwriting an existing review artifact."""

    path = Path(path)
    validate_proposal(proposal)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                proposal,
                stream,
                ensure_ascii=False,
                indent=2,
            )
            stream.write("\n")
    except FileExistsError:
        raise ValidationError(
            "Proposal już istnieje; nie zostanie nadpisany"
        ) from None


def replace_proposal(path, proposal):
    """Atomically replace an existing proposal after a human decision."""

    path = Path(path)
    validate_proposal(proposal)

    if not path.exists():
        raise ValidationError("Proposal nie istnieje")

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                proposal,
                stream,
                ensure_ascii=False,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def row_to_csv_record(row):
    if not isinstance(row, ProductRow):
        raise ValidationError("Oczekiwano ProductRow")

    categories = row.extra.get("categories", "")

    if isinstance(categories, list):
        categories = "|".join(categories)

    return {
        "sku": row.sku,
        "name": row.name,
        "regular_price": row.regular_price,
        "stock_quantity": row.stock_quantity,
        "status": row.status,
        "description": row.extra.get("description", ""),
        "short_description": row.extra.get("short_description", ""),
        "categories": categories,
        "image_id": row.extra.get("image_id", ""),
        "image_url": row.extra.get("image_url", ""),
        "image_alt": row.extra.get("image_alt", ""),
    }


def write_materialized_csv(path, rows):
    """Write ProductRows without inventing unmanaged optional fields."""

    path = Path(path)
    rows = list(rows)

    if not rows:
        raise ValidationError("Brak produktów do materializacji")

    managed_optional = [
        field
        for field in OPTIONAL_CSV_FIELDS
        if any(field in row.extra for row in rows)
    ]

    fields = list(REQUIRED_CSV_FIELDS) + managed_optional

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fields,
                extrasaction="ignore",
            )
            writer.writeheader()

            for row in rows:
                writer.writerow(row_to_csv_record(row))
    except FileExistsError:
        raise ValidationError(
            "Plik wynikowy już istnieje; nie zostanie nadpisany"
        ) from None
