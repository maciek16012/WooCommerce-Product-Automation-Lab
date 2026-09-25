import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from woo_sync.ai_cli import main
from woo_sync.core import load_csv
from woo_sync.proposal_io import load_proposal


class AiCliTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "products.csv"

        with self.source.open(
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
                    "description",
                    "short_description",
                    "image_alt",
                ]
            )
            writer.writerow(
                [
                    "A-1",
                    "Klawiatura",
                    "199.00",
                    "10",
                    "publish",
                    "Opis bazowy",
                    "Krótki opis",
                    "Klawiatura testowa",
                ]
            )

    def create_proposal(self):
        path = self.root / "proposal.json"

        result = main(
            [
                "propose",
                str(self.source),
                "--out",
                str(path),
            ]
        )

        self.assertEqual(result, 0)
        return path

    def test_propose_creates_pending_artifact(self):
        path = self.create_proposal()
        proposal = load_proposal(path)

        self.assertEqual(len(proposal["items"]), 1)
        self.assertEqual(
            proposal["items"][0]["approval"],
            "pending",
        )

    def test_approve_persists_human_decision(self):
        path = self.create_proposal()

        result = main(
            [
                "approve",
                str(path),
                "A-1",
            ]
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            load_proposal(path)["items"][0]["approval"],
            "approved",
        )

    def test_reject_persists_human_decision(self):
        path = self.create_proposal()

        result = main(
            [
                "reject",
                str(path),
                "A-1",
            ]
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            load_proposal(path)["items"][0]["approval"],
            "rejected",
        )

    def test_apply_proposal_materializes_approved_csv(self):
        proposal = self.create_proposal()

        self.assertEqual(
            main(["approve", str(proposal), "A-1"]),
            0,
        )

        output = self.root / "approved.csv"

        result = main(
            [
                "apply-proposal",
                str(self.source),
                str(proposal),
                "--out",
                str(output),
            ]
        )

        self.assertEqual(result, 0)

        row = load_csv(output)[0]

        self.assertIn(
            "Propozycja demonstracyjna",
            row.extra["description"],
        )
        self.assertEqual(row.name, "Klawiatura")
        self.assertEqual(row.regular_price, "199.00")
        self.assertEqual(row.stock_quantity, 10)

    def test_apply_proposal_requires_human_approval(self):
        proposal = self.create_proposal()
        output = self.root / "approved.csv"

        with patch(
            "sys.stderr",
            new_callable=io.StringIO,
        ):
            result = main(
                [
                    "apply-proposal",
                    str(self.source),
                    str(proposal),
                    "--out",
                    str(output),
                ]
            )

        self.assertEqual(result, 2)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
