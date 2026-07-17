from decimal import Decimal

import pytest

from sneaker_market_maker.core import MarketSnapshot
from sneaker_market_maker.pipeline import SneakerDataPipeline
from sneaker_market_maker.research.adapters.legacy import LegacyFiveVectorAdapter
from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
    RawHybridAction,
    canonicalize_action,
)
from sneaker_market_maker.research.contracts.state import StateSchema, StateValidationError


def snapshot(**overrides: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "platform": "stockx",
        "style_code": "DD1391-100",
        "shoe_size": Decimal("10"),
        "highest_bid": Decimal("180.25"),
        "lowest_ask": Decimal("195.75"),
        "sales_48h": 3,
        "volatility_48h": Decimal("7.5"),
        "days_since_release": 4,
    }
    values.update(overrides)
    return MarketSnapshot(**values)  # type: ignore[arg-type]


def test_legacy_five_feature_names_and_order_are_frozen() -> None:
    assert SneakerDataPipeline.FEATURE_NAMES == (
        "highest_bid",
        "lowest_ask",
        "days_since_release",
        "volatility_48h",
        "fee_rate",
    )
    assert LegacyFiveVectorAdapter.feature_names == SneakerDataPipeline.FEATURE_NAMES
    assert LegacyFiveVectorAdapter().encode(snapshot(), Decimal("0.13")) == (
        180.25,
        195.75,
        4.0,
        7.5,
        0.13,
    )


@pytest.mark.parametrize("category", [ActionCategory.NO_OP, ActionCategory.CANCEL])
def test_inactive_action_categories_neutralize_continuous_values(
    category: ActionCategory,
) -> None:
    result = canonicalize_action(
        RawHybridAction(category, float("nan"), float("inf"), float("-inf")),
        ActionBounds(-3, 3, -4, 4),
        ActionMask(True, True, True),
    )
    assert result == HybridAction(category, 0.0, 0, 0)


def test_quote_is_tick_rounded_and_clamped() -> None:
    result = canonicalize_action(
        RawHybridAction(ActionCategory.QUOTE, 1.4, -4.6, 2.6),
        ActionBounds(-3, 3, -4, 2),
        ActionMask(True, True, True),
    )
    assert result == HybridAction(ActionCategory.QUOTE, 1.0, -3, 2)


def test_masked_action_category_fails_closed() -> None:
    with pytest.raises(ValueError, match="masked action category"):
        canonicalize_action(
            RawHybridAction(ActionCategory.QUOTE, 0.5, 0.0, 0.0),
            ActionBounds(-3, 3, -4, 4),
            ActionMask(True, False, True),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"highest_bid": 180.0},
        {"highest_bid": 180.0, "lowest_ask": float("nan")},
        {"highest_bid": Decimal("Infinity"), "lowest_ask": 195.0},
    ],
)
def test_state_schema_rejects_missing_or_non_finite_required_state(
    payload: dict[str, object],
) -> None:
    schema = StateSchema(
        version="legacy-v1",
        feature_names=("highest_bid", "lowest_ask"),
        required_fields=("highest_bid", "lowest_ask"),
    )
    with pytest.raises(StateValidationError):
        schema.validate(payload)


def test_state_schema_accepts_finite_required_state() -> None:
    schema = StateSchema(
        version="legacy-v1",
        feature_names=("highest_bid", "lowest_ask"),
        required_fields=("highest_bid", "lowest_ask"),
    )
    schema.validate({"highest_bid": Decimal("180.25"), "lowest_ask": 195.75})


def test_quote_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="action values must be finite"):
        canonicalize_action(
            RawHybridAction(ActionCategory.QUOTE, float("nan"), 0.0, 0.0),
            ActionBounds(-3, 3, -4, 4),
            ActionMask(True, True, True),
        )


def test_legacy_adapter_rejects_non_finite_output() -> None:
    with pytest.raises(StateValidationError, match="finite"):
        LegacyFiveVectorAdapter().encode(snapshot(), Decimal("NaN"))
