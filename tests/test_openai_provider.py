import io
import json
import os
import unittest
from unittest.mock import patch

from woo_sync.ai_providers import (
    DEFAULT_OPENAI_MODEL,
    get_provider,
    openai_provider,
)
from woo_sync.core import ProductRow, ValidationError


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None
        self.timeout = None

    def open(self, request, timeout=None):
        self.request = request
        self.timeout = timeout
        return FakeResponse(
            json.dumps(self.payload).encode("utf-8")
        )


class OpenAiProviderTests(unittest.TestCase):

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
                "image_alt": "Klawiatura na biurku",
            },
        )

    def api_response(self):
        generated = {
            "description": "Nowy opis produktu.",
            "short_description": "Krótka treść produktu.",
            "image_alt": "Klawiatura na biurku",
        }

        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(generated),
                        }
                    ],
                }
            ],
        }

    def test_openai_provider_is_registered(self):
        self.assertIs(
            get_provider("openai"),
            openai_provider,
        )

    def test_missing_api_key_is_rejected_before_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ValidationError,
                "OPENAI_API_KEY",
            ):
                openai_provider(self.row())

    def test_structured_response_is_returned(self):
        opener = FakeOpener(self.api_response())

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-secret"},
            clear=True,
        ):
            with patch(
                "woo_sync.ai_providers.urllib.request.build_opener",
                return_value=opener,
            ):
                result = openai_provider(self.row())

        self.assertEqual(
            result["description"],
            "Nowy opis produktu.",
        )
        self.assertEqual(
            result["image_alt"],
            "Klawiatura na biurku",
        )

        body = json.loads(
            opener.request.data.decode("utf-8")
        )

        self.assertEqual(
            body["model"],
            DEFAULT_OPENAI_MODEL,
        )
        self.assertEqual(
            body["text"]["format"]["type"],
            "json_schema",
        )
        self.assertTrue(
            body["text"]["format"]["strict"]
        )

        auth = opener.request.get_header("Authorization")
        self.assertEqual(auth, "Bearer test-secret")

    def test_api_key_is_not_written_into_prompt(self):
        opener = FakeOpener(self.api_response())

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "super-secret-key"},
            clear=True,
        ):
            with patch(
                "woo_sync.ai_providers.urllib.request.build_opener",
                return_value=opener,
            ):
                openai_provider(self.row())

        body = opener.request.data.decode("utf-8")
        self.assertNotIn("super-secret-key", body)

    def test_refusal_is_rejected(self):
        opener = FakeOpener(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "refusal",
                                "refusal": "No",
                            }
                        ],
                    }
                ],
            }
        )

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-secret"},
            clear=True,
        ):
            with patch(
                "woo_sync.ai_providers.urllib.request.build_opener",
                return_value=opener,
            ):
                with self.assertRaisesRegex(
                    ValidationError,
                    "odmówił",
                ):
                    openai_provider(self.row())


if __name__ == "__main__":
    unittest.main()
