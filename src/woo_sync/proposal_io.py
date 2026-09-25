"""Atomic proposal persistence and lossless, validated CSV materialization."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

from .content_proposals import source_fingerprint, validate_proposal, set_approval
from .core import ProductRow, ValidationError, load_csv
from .locking import sync_lock

MAX_PROPOSAL_BYTES = 5 * 1024 * 1024
REQUIRED_CSV_FIELDS = ("sku", "name", "regular_price", "stock_quantity", "status")
OPTIONAL_CSV_FIELDS = ("description", "short_description", "categories", "image_id", "image_url", "image_alt")


def load_proposal(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_PROPOSAL_BYTES + 1)
        if len(raw) > MAX_PROPOSAL_BYTES:
            raise ValidationError("Proposal przekracza limit 5 MiB")
        proposal = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValidationError("Nie można odczytać proposal JSON") from None
    return validate_proposal(proposal)


def _atomic_write(path, writer, *, replace=False, validate=None):
    """Publish complete bytes only. Hard link is atomic create-if-absent on NTFS."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if validate is not None:
            validate(Path(temporary))
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ValidationError("Plik już istnieje; nie zostanie nadpisany") from None
    finally:
        # Cleanup is constrained to the unique temporary file we created.
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _write_json(stream, proposal):
    json.dump(proposal, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def write_new_proposal(path, proposal):
    validate_proposal(proposal)
    _atomic_write(path, lambda stream: _write_json(stream, proposal))


def replace_proposal(path, proposal):
    """Atomic replacement; callers must serialize read-modify-write decisions."""
    validate_proposal(proposal)
    if not Path(path).is_file():
        raise ValidationError("Proposal nie istnieje")
    _atomic_write(path, lambda stream: _write_json(stream, proposal), replace=True)


def review_proposal(path, sku, decision):
    """Serialize CLI decisions so concurrent approvals do not overwrite each other."""
    path = Path(path).resolve()
    with sync_lock(path.with_name(path.name + ".lock")):
        updated = set_approval(load_proposal(path), sku, decision)
        replace_proposal(path, updated)
    return updated


def row_to_csv_record(row):
    if not isinstance(row, ProductRow):
        raise ValidationError("Oczekiwano ProductRow")
    record = {field: getattr(row, field) for field in REQUIRED_CSV_FIELDS}
    for key, value in row.extra.items():
        if key not in OPTIONAL_CSV_FIELDS:
            raise ValidationError("Nieobsługiwane pole opcjonalne")
        record[key] = "|".join(value) if key == "categories" and isinstance(value, list) else value
    return record


def write_materialized_csv(path, rows):
    rows = list(rows)
    if not rows:
        raise ValidationError("Brak produktów do materializacji")
    records = [row_to_csv_record(row) for row in rows]
    masks = [set(row.extra) for row in rows]
    if any(mask != masks[0] for mask in masks):
        # A rectangular CSV cannot encode per-row absence versus an empty cell.
        raise ValidationError("CSV nie zachowa mieszanych pól opcjonalnych; podziel źródło według zarządzanych pól")
    fields = list(REQUIRED_CSV_FIELDS) + [f for f in OPTIONAL_CSV_FIELDS if f in masks[0]]

    def write(stream):
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    def validate(temporary):
        loaded = load_csv(temporary)
        if [source_fingerprint(row) for row in loaded] != [source_fingerprint(row) for row in rows]:
            raise ValidationError("Normalizacja CSV zmienia zatwierdzoną treść; popraw źródło lub propozycję")

    _atomic_write(path, write, validate=validate)
