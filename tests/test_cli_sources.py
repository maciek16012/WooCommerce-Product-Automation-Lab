import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from woo_sync.cli import main


class CliSourceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_valid_catalog(self):
        catalog = self.root / "catalog.json"
        media = self.root / "media.local.json"

        catalog.write_text(
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

        return catalog

    def test_validate_json_uses_default_sibling_media(self):
        catalog = self.write_valid_catalog()
        log = self.root / "validate.jsonl"

        result = main(
            [
                "validate",
                str(catalog),
                "--log",
                str(log),
            ]
        )

        self.assertEqual(result, 0)

        record = json.loads(
            log.read_text(encoding="utf-8")
        )

        self.assertTrue(record["valid"])
        self.assertEqual(record["rows"], 1)

    def test_json_validation_happens_before_network(self):
        catalog = self.root / "catalog.json"
        log = self.root / "bad.jsonl"

        catalog.write_text(
            json.dumps(
                [
                    {
                        "sku": "A-1",
                        "name": "Produkt",
                        "regular_price": "BAD",
                        "stock_quantity": 4,
                        "status": "publish",
                    }
                ]
            ),
            encoding="utf-8",
        )

        with patch(
            "woo_sync.cli.WooClient"
        ) as client:
            result = main(
                [
                    "sync",
                    str(catalog),
                    "--log",
                    str(log),
                ]
            )

        self.assertEqual(result, 2)
        client.assert_not_called()

    def test_validate_google_sheet_source(self):
        log = self.root / "sheet.jsonl"

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
            result = main(
                [
                    "validate",
                    url,
                    "--log",
                    str(log),
                ]
            )

        self.assertEqual(result, 0)

        record = json.loads(
            log.read_text(encoding="utf-8")
        )

        self.assertTrue(record["valid"])
        self.assertEqual(record["rows"], 1)
    def test_validation_report_contains_run_metadata(self):
        catalog = self.write_valid_catalog()
        log = self.root / "metadata.jsonl"

        result = main(
            [
                "validate",
                str(catalog),
                "--source-type",
                "json",
                "--log",
                str(log),
            ]
        )

        self.assertEqual(result, 0)

        record = json.loads(
            log.read_text(encoding="utf-8")
        )

        self.assertEqual(
            record["event"],
            "VALIDATION",
        )

        self.assertTrue(
            record["run_id"]
        )

        self.assertEqual(
            record["source"],
            str(catalog),
        )

        self.assertEqual(
            record["source_type"],
            "json",
        )

        self.assertGreaterEqual(
            record["duration_ms"],
            0,
        )
    def test_explicit_source_type_json(self):
        catalog = self.write_valid_catalog()
        log = self.root / "explicit.jsonl"

        result = main(
            [
                "validate",
                str(catalog),
                "--source-type",
                "json",
                "--log",
                str(log),
            ]
        )

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
