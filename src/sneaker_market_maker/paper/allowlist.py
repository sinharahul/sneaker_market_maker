"""Versioned Product-Family Allowlist for Continuous Paper Market-Maker."""

from __future__ import annotations

from enum import Enum

from sneaker_market_maker.paper.errors import PaperError

ALLOWLIST_VERSION = "product-families-v1"


class ProductFamily(str, Enum):
    JORDAN_1_RETRO = "jordan_1_retro"
    NIKE_DUNK_LOW = "nike_dunk_low"


ALLOWED_FAMILIES = frozenset(family.value for family in ProductFamily)


def assert_family_allowed(family: str) -> ProductFamily:
    """Return the canonical family or fail closed for unsupported products."""

    normalized = family.strip().casefold()
    try:
        return ProductFamily(normalized)
    except ValueError as error:
        raise PaperError(
            "unsupported_product_family",
            f"product family '{family}' is outside the Product-Family Allowlist",
        ) from error
