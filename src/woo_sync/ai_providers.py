"""AI content provider registry."""

from __future__ import annotations

from .core import ValidationError

PROVIDER_NAMES = ("demo",)


def demo_provider(row):
    """Deterministic provider used for tests and offline demonstrations."""

    name = row.name.strip()

    return {
        "description": (
            f"Propozycja demonstracyjna dla produktu {name}. "
            "Treść wymaga ręcznej akceptacji przed synchronizacją."
        ),
        "short_description": (
            f"Propozycja opisu produktu {name} do ręcznej weryfikacji."
        ),
        "image_alt": (
            row.extra.get("image_alt")
            or f"{name} — zdjęcie produktu"
        ),
    }


def get_provider(name):
    providers = {
        "demo": demo_provider,
    }

    try:
        return providers[name]
    except KeyError:
        raise ValidationError(
            f"Nieznany AI provider: {name}"
        ) from None
