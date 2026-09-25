import csv
import json
import tempfile
import unittest
from pathlib import Path

from woo_sync.core import ValidationError
from woo_sync.sources import load_source


class SourceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_csv_source_uses_existing_validation(self):
        source = self.root / "products.csv"

        with source.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "sku",
                    "name",
                    "regular_price",
                    "stock_quantity",
                    "status",
                ]
            )
            writer.writerow(
                [
                    "A-1",
                    "Produkt",
                    "19.90",
                    "4",
                    "publish",
                ]
            )

        rows = load_source(source)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sku, "A-1")
        self.assertEqual(rows[0].regular_price, "19.90")
        self.assertEqual(rows[0].stock_quantity, 4)

    def test_json_catalog_resolves_media_asset(self):
        source = self.root / "catalog.json"
        media = self.root / "media.json"

        source.write_text(
            json.dumps(
                [
                    {
                        "sku": "A-1",
                        "name": "Produkt",
                        "regular_price": "19.90",
                        "stock_quantity": 4,
                        "status": "publish",
                        "asset": "keyboard",
                        "image_alt": "Klawiatura testowa",
                    }
                ]
            ),
            encoding="utf-8",
        )

        media.write_text(
            json.dumps(
                {
                    "keyboard": 22,
                }
            ),
            encoding="utf-8",
        )

        rows = load_source(
            source,
            media_path=media,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sku, "A-1")
        self.assertEqual(
            rows[0].extra["image_id"],
            "22",
        )
        self.assertEqual(
            rows[0].extra["image_alt"],
            "Klawiatura testowa",
        )

    def test_json_unknown_asset_is_rejected(self):
        source = self.root / "catalog.json"
        media = self.root / "media.json"

        source.write_text(
            json.dumps(
                [
                    {
                        "sku": "A-1",
                        "name": "Produkt",
                        "regular_price": "19.90",
                        "stock_quantity": 4,
                        "status": "publish",
                        "asset": "missing",
                        "image_alt": "Obraz",
                    }
                ]
            ),
            encoding="utf-8",
        )

        media.write_text(
            "{}",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValidationError,
            "nieznany asset",
        ):
            load_source(
                source,
                media_path=media,
            )


if __name__ == "__main__":
    unittest.main()
