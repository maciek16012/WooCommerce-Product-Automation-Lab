import unittest

from woo_sync.content_proposals import (
    apply_approved,
    build_proposal,
    set_approval,
    source_fingerprint,
    validate_proposal,
)
from woo_sync.core import ProductRow, ValidationError


class ContentProposalTests(unittest.TestCase):

    def make_row(self, **changes):
        values = {
            "line": 2,
            "sku": "A-1",
            "name": "Klawiatura testowa",
            "regular_price": "199.00",
            "stock_quantity": 10,
            "status": "publish",
            "extra": {
                "description": "Stary opis",
                "short_description": "Stary krótki opis",
                "categories": ["peryferia"],
                "image_id": "22",
                "image_alt": "Stary ALT",
            },
        }

        values.update(changes)
        return ProductRow(**values)


    def provider(self, row):
        return {
            "description": f"Nowy opis produktu {row.name}",
            "short_description": "Nowy krótki opis",
            "image_alt": "Klawiatura na biurku",
        }


    def test_build_proposal_is_pending_and_auditable(self):
        row = self.make_row()

        proposal = build_proposal(
            [row],
            self.provider,
            "catalog.json",
        )

        self.assertEqual(proposal["schema_version"], 1)
        self.assertTrue(proposal["proposal_id"])
        self.assertTrue(proposal["created_at"])
        self.assertEqual(proposal["source"], "catalog.json")
        self.assertEqual(len(proposal["items"]), 1)

        item = proposal["items"][0]

        self.assertEqual(item["sku"], "A-1")
        self.assertEqual(item["approval"], "pending")
        self.assertEqual(
            item["source_fingerprint"],
            source_fingerprint(row),
        )
        self.assertEqual(len(item["source_fingerprint"]), 64)


    def test_approved_content_is_applied_without_changing_master_data(self):
        row = self.make_row()

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

        result = apply_approved(
            [row],
            proposal,
        )

        updated = result[0]

        self.assertEqual(updated.sku, row.sku)
        self.assertEqual(updated.name, row.name)
        self.assertEqual(updated.regular_price, row.regular_price)
        self.assertEqual(updated.stock_quantity, row.stock_quantity)
        self.assertEqual(updated.status, row.status)

        self.assertEqual(
            updated.extra["description"],
            "Nowy opis produktu Klawiatura testowa",
        )
        self.assertEqual(
            updated.extra["short_description"],
            "Nowy krótki opis",
        )
        self.assertEqual(
            updated.extra["image_alt"],
            "Klawiatura na biurku",
        )
        self.assertEqual(
            updated.extra["categories"],
            ["peryferia"],
        )
        self.assertEqual(updated.extra["image_id"], "22")


    def test_rejected_content_is_not_applied(self):
        row = self.make_row()

        proposal = build_proposal(
            [row],
            self.provider,
            "catalog.json",
        )

        proposal = set_approval(
            proposal,
            "A-1",
            "rejected",
        )

        result = apply_approved(
            [row],
            proposal,
        )

        self.assertEqual(result, [row])


    def test_stale_proposal_is_blocked_after_source_change(self):
        row = self.make_row()

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

        changed = self.make_row(
            regular_price="249.00",
        )

        with self.assertRaisesRegex(
            ValidationError,
            "źródło zmieniło się",
        ):
            apply_approved(
                [changed],
                proposal,
            )


    def test_provider_html_is_rejected(self):
        row = self.make_row()

        def bad_provider(_row):
            return {
                "description": "<script>bad</script>",
            }

        with self.assertRaisesRegex(
            ValidationError,
            "HTML",
        ):
            build_proposal(
                [row],
                bad_provider,
                "catalog.json",
            )


    def test_duplicate_sku_in_proposal_is_rejected(self):
        row = self.make_row()

        proposal = build_proposal(
            [row],
            self.provider,
            "catalog.json",
        )

        duplicate = dict(proposal["items"][0])
        duplicate["sku"] = "a-1"
        proposal["items"].append(duplicate)

        with self.assertRaisesRegex(
            ValidationError,
            "powtórzone SKU",
        ):
            validate_proposal(proposal)


if __name__ == "__main__":
    unittest.main()
