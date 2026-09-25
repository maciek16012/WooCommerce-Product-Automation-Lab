"""Build demo CSV from canonical catalog.json and local media manifest."""

import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]

catalog = json.loads(
    (root / "data/catalog.json").read_text(encoding="utf-8")
)

media = json.loads(
    (root / "data/media.local.json").read_text(encoding="utf-8")
)

fields = [
    "sku",
    "name",
    "regular_price",
    "stock_quantity",
    "status",
    "description",
    "short_description",
    "categories",
    "image_id",
    "image_alt",
]

required = {
    "sku",
    "name",
    "regular_price",
    "stock_quantity",
    "status",
    "description",
    "short_description",
    "categories",
    "asset",
    "image_alt",
}

seen = set()

with (root / "data/products.csv").open(
    "w",
    encoding="utf-8",
    newline="",
) as stream:

    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()

    for index, product in enumerate(catalog, start=1):

        missing = required - set(product)
        if missing:
            raise ValueError(
                f"Catalog row {index}: missing fields: "
                + ", ".join(sorted(missing))
            )

        sku = str(product["sku"])

        if sku.casefold() in seen:
            raise ValueError(f"Duplicate SKU in catalog: {sku}")

        seen.add(sku.casefold())

        asset = str(product["asset"])

        if asset not in media:
            raise ValueError(
                f"Unknown media asset '{asset}' for SKU {sku}"
            )

        writer.writerow(
            {
                "sku": sku,
                "name": product["name"],
                "regular_price": product["regular_price"],
                "stock_quantity": product["stock_quantity"],
                "status": product["status"],
                "description": product["description"],
                "short_description": product["short_description"],
                "categories": product["categories"],
                "image_id": media[asset],
                "image_alt": product["image_alt"],
            }
        )

print(
    f"Demo CSV: {len(catalog)} products / "
    f"{len({p['categories'] for p in catalog})} categories"
)
