import unittest

from woo_sync.ai_providers import (
    PROVIDER_NAMES,
    demo_provider,
    get_provider,
)
from woo_sync.core import ProductRow, ValidationError


class AiProviderTests(unittest.TestCase):

    def row(self):
        return ProductRow(
            2,
            "A-1",
            "Klawiatura",
            "199.00",
            10,
            "publish",
            {
                "image_alt": "Istniejący ALT",
            },
        )

    def test_demo_provider_is_registered(self):
        self.assertIn("demo", PROVIDER_NAMES)
        self.assertIs(
            get_provider("demo"),
            demo_provider,
        )

    def test_demo_provider_returns_content_only(self):
        result = demo_provider(self.row())

        self.assertEqual(
            set(result),
            {
                "description",
                "short_description",
                "image_alt",
            },
        )

        self.assertEqual(
            result["image_alt"],
            "Istniejący ALT",
        )

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(
            ValidationError,
            "Nieznany AI provider",
        ):
            get_provider("missing")


if __name__ == "__main__":
    unittest.main()
