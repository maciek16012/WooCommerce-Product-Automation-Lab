import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_google_sheet_csv_uses_shared_validation(self):
        payload = (
            "sku,name,regular_price,stock_quantity,status\n"
            "A-1,Produkt,19.90,4,publish\n"
        ).encode("utf-8")

        url = (
            "https://docs.google.com/spreadsheets/d/"
            "demo/export?format=csv&gid=0"
        )

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=io.BytesIO(payload),
        ):
            rows = load_source(url)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sku, "A-1")
        self.assertEqual(rows[0].regular_price, "19.90")
        self.assertEqual(rows[0].stock_quantity, 4)

    def test_google_sheet_rejects_non_google_urls(self):
        for url in (
            "http://docs.google.com/spreadsheets/d/demo/export",
            "https://example.com/products.csv",
            "https://evil.example/docs.google.com/products.csv",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    load_source(
                        url,
                        source_type="sheets",
                    )

    def test_google_sheet_size_limit(self):
        url = (
            "https://docs.google.com/spreadsheets/d/"
            "demo/export?format=csv&gid=0"
        )

        payload = b"x" * (5 * 1024 * 1024 + 1)

        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=io.BytesIO(payload),
        ):
            with self.assertRaisesRegex(
                ValidationError,
                "5 MiB",
            ):
                load_source(url)
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
