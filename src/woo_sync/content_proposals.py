"""Auditable human-in-the-loop AI content proposal workflow."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from .core import ProductRow, ValidationError

SCHEMA_VERSION = 1
CONTENT_FIELDS = ("description", "short_description", "image_alt")
DECISIONS = ("pending", "approved", "rejected")


def _source_state(row):
    return {
        "managed_optional_fields": sorted(row.extra),
        "sku": row.sku,
        "name": row.name,
        "regular_price": row.regular_price,
        "stock_quantity": row.stock_quantity,
        "status": row.status,
        "description": row.extra.get("description", ""),
        "short_description": row.extra.get("short_description", ""),
        "categories": row.extra.get("categories", []),
        "image_id": row.extra.get("image_id", ""),
        "image_url": row.extra.get("image_url", ""),
        "image_alt": row.extra.get("image_alt", ""),
    }


def source_fingerprint(row):
    payload = json.dumps(
        _source_state(row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def _validate_proposed_content(content):
    if not isinstance(content, dict):
        raise ValidationError("Proponowana treść musi być obiektem")

    unknown = set(content) - set(CONTENT_FIELDS)
    if unknown:
        raise ValidationError(
            "Nieobsługiwane pola AI; dozwolone są wyłącznie pola treści"
        )

    if not content:
        raise ValidationError("Propozycja AI nie zawiera treści")

    for field, value in content.items():
        if not isinstance(value, str):
            raise ValidationError(f"{field}: wartość musi być tekstem")

        if "<" in value or ">" in value:
            raise ValidationError(f"{field}: HTML jest niedozwolony")

        limit = 500 if field == "image_alt" else 30000

        if len(value) > limit:
            raise ValidationError(f"{field}: przekroczony limit {limit}")


def build_proposal(rows, provider, source_label):
    """Generate pending content proposals using a provider callable."""

    items = []

    for row in rows:
        fingerprint = source_fingerprint(row)
        proposed = deepcopy(provider(deepcopy(row)))
        _validate_proposed_content(proposed)

        items.append(
            {
                "sku": row.sku,
                "source_fingerprint": fingerprint,
                "approval": "pending",
                "proposed": proposed,
            }
        )

    return validate_proposal({
        "schema_version": SCHEMA_VERSION,
        "proposal_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_label),
        "items": items,
    })


def validate_proposal(proposal):
    if not isinstance(proposal, dict):
        raise ValidationError("Proposal musi być obiektem JSON")

    if type(proposal.get("schema_version")) is not int or proposal.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("Nieobsługiwana wersja proposal schema")

    if not isinstance(proposal.get("proposal_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", proposal["proposal_id"]):
        raise ValidationError("Proposal: błędny proposal_id")

    items = proposal.get("items")

    if not isinstance(items, list) or not items:
        raise ValidationError("Proposal nie zawiera produktów")

    seen = set()

    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("Element proposal musi być obiektem")

        sku = item.get("sku")

        if not isinstance(sku, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", sku):
            raise ValidationError("Proposal: brak SKU")

        folded = sku.casefold()

        if folded in seen:
            raise ValidationError("Proposal: powtórzone SKU")

        seen.add(folded)

        if item.get("approval") not in DECISIONS:
            raise ValidationError("Proposal: nieznany status approval")

        fingerprint = item.get("source_fingerprint")

        if (
            not isinstance(fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        ):
            raise ValidationError("Proposal: błędny fingerprint")

        _validate_proposed_content(item.get("proposed"))

    return proposal


def review_fingerprint(proposal, item):
    """Bind a review to the exact SKU, source, proposal and proposed content."""
    payload = {key: item[key] for key in ("sku", "source_fingerprint", "proposed")}
    payload["proposal_id"] = proposal["proposal_id"]
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def set_approval(proposal, sku, decision):
    if decision not in ("approved", "rejected"):
        raise ValidationError("Dozwolone decyzje: approved albo rejected")

    updated = deepcopy(validate_proposal(proposal))

    matches = [
        item
        for item in updated["items"]
        if item["sku"].casefold() == sku.casefold()
    ]

    if len(matches) != 1:
        raise ValidationError("Nie znaleziono jednoznacznego SKU w proposal")

    item = matches[0]
    item["approval"] = decision
    item["review"] = {
        "decision": decision,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "content_fingerprint": review_fingerprint(updated, item),
    }
    return updated


def apply_approved(rows, proposal):
    """Apply only approved proposals after verifying source fingerprints."""

    proposal = validate_proposal(proposal)
    by_sku = {item["sku"].casefold(): item for item in proposal["items"]}
    rows = list(rows)
    source_skus = {row.sku.casefold() for row in rows}
    if len(source_skus) != len(rows):
        raise ValidationError("Źródło: powtórzone SKU")
    for item in proposal["items"]:
        if item["approval"] != "approved":
            continue
        if item["sku"].casefold() not in source_skus:
            raise ValidationError("Zatwierdzone SKU nie istnieje w źródle")
        review = item.get("review")
        if (not isinstance(review, dict) or review.get("decision") != "approved"
                or not review.get("reviewed_at")
                or review.get("content_fingerprint") != review_fingerprint(proposal, item)):
            raise ValidationError("Treść nie ma aktualnego zatwierdzenia; wykonaj ponowny review")
    result = []

    for row in rows:
        item = by_sku.get(row.sku.casefold())

        if not item or item["approval"] != "approved":
            result.append(row)
            continue

        if source_fingerprint(row) != item["source_fingerprint"]:
            raise ValidationError(
                f"{row.sku}: źródło zmieniło się od wygenerowania propozycji"
            )

        extra = dict(row.extra)
        extra.update(item["proposed"])

        result.append(
            ProductRow(
                row.line,
                row.sku,
                row.name,
                row.regular_price,
                row.stock_quantity,
                row.status,
                extra,
            )
        )

    return result
