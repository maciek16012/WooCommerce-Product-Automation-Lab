import json
import tempfile
import unittest
from pathlib import Path

from woo_sync.content_proposals import (
    apply_approved,
    build_proposal,
    set_approval,
)
from woo_sync.core import ProductRow, ValidationError, load_csv
from woo_sync.proposal_io import (
    load_proposal,
    replace_proposal,
    write_materialized_csv,
    write_new_proposal,
)


class ProposalIOTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def row(self):
        return ProductRow(
            2,
            "A-1",
            "Klawiatura",
            "199.00",
            10,
            "publish",
            {
                "description": "Opis bazowy",
                "short_description": "Krótki opis",
                "categories": ["peryferia"],
                "image_id": "22",
                "image_alt": "Stary ALT",
            },
        )

    def provider(self, row):
        return {
            "description": "Opis zatwierdzony przez człowieka",
            "short_description": "Nowy krótki opis",
            "image_alt": "Klawiatura na jasnym biurku",
        }

    def test_proposal_round_trip(self):
        proposal = build_proposal(
            [self.row()],
            self.provider,
            "catalog.json",
        )

        path = self.root / "proposal.json"
        write_new_proposal(path, proposal)
        loaded = load_proposal(path)

        self.assertEqual(
            loaded["proposal_id"],
            proposal["proposal_id"],
        )
        self.assertEqual(
            loaded["items"][0]["approval"],
            "pending",
        )

    def test_new_proposal_never_overwrites_existing_file(self):
        proposal = build_proposal(
            [self.row()],
            self.provider,
            "catalog.json",
        )

        path = self.root / "proposal.json"
        write_new_proposal(path, proposal)

        original = path.read_text(encoding="utf-8")

        with self.assertRaisesRegex(
            ValidationError,
            "nie zostanie nadpisany",
        ):
            write_new_proposal(path, proposal)

        self.assertEqual(
            path.read_text(encoding="utf-8"),
            original,
        )

    def test_human_decision_can_be_atomically_persisted(self):
        proposal = build_proposal(
            [self.row()],
            self.provider,
            "catalog.json",
        )

        path = self.root / "proposal.json"
        write_new_proposal(path, proposal)

        approved = set_approval(
            load_proposal(path),
            "A-1",
            "approved",
        )

        replace_proposal(path, approved)

        self.assertEqual(
            load_proposal(path)["items"][0]["approval"],
            "approved",
        )

    def test_materialized_csv_is_accepted_by_existing_loader(self):
        row = self.row()
        proposal = build_proposal(
            [row],
            self.provider,
            "catalog.json",
        )
        proposal = set_approval(
            proposal,
            "A-1",
            "approved",
        )

        approved_rows = apply_approved(
            [row],
            proposal,
        )

        output = self.root / "approved.csv"
        write_materialized_csv(output, approved_rows)

        loaded = load_csv(output)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].sku, "A-1")
        self.assertEqual(
            loaded[0].extra["description"],
            "Opis zatwierdzony przez człowieka",
        )
        self.assertEqual(
            loaded[0].extra["image_alt"],
            "Klawiatura na jasnym biurku",
        )

    def test_materialized_csv_does_not_change_master_fields(self):
        row = self.row()
        proposal = build_proposal(
            [row],
            self.provider,
            "catalog.json",
        )
        proposal = set_approval(
            proposal,
            "A-1",
            "approved",
        )

        approved_rows = apply_approved([row], proposal)
        output = self.root / "approved.csv"
        write_materialized_csv(output, approved_rows)
        loaded = load_csv(output)[0]

        self.assertEqual(loaded.name, row.name)
        self.assertEqual(
            loaded.regular_price,
            row.regular_price,
        )
        self.assertEqual(
            loaded.stock_quantity,
            row.stock_quantity,
        )
        self.assertEqual(loaded.status, row.status)


if __name__ == "__main__":
    unittest.main()
