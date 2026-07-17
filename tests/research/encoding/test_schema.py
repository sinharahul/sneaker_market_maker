from decimal import Decimal

import pytest
import torch

from sneaker_market_maker.research.contracts.action import ActionBounds, ActionMask
from sneaker_market_maker.research.contracts.state import StateValidationError
from sneaker_market_maker.research.encoding.schema import (
    MaskBuilder,
    Scaler,
    StateEncoder,
    StateSchema,
)


def schema() -> StateSchema:
    return StateSchema(
        version="rich-v1",
        continuous=("cash_usd", "spread_usd"),
        required=("cash_usd", "spread_usd", "regime"),
        categorical_vocabularies={"regime": ("normal", "restock")},
        collection_limits={"open_orders": 3, "inventory_lots": 2},
    )


def scaler() -> Scaler:
    return Scaler(
        version="train-fold-1-v1",
        fold_hash="fold-1-sha256",
        means={"cash_usd": 100.0, "spread_usd": 5.0},
        scales={"cash_usd": 20.0, "spread_usd": 2.0},
    )


def state(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "cash_usd": Decimal("140.00"),
        "spread_usd": Decimal("7.00"),
        "regime": "normal",
        "open_orders": [{"side": "bid"}],
        "inventory_lots": [{"sellable": True}, {"sellable": False}],
    }
    values.update(overrides)
    return values


def test_encoder_preserves_declared_order_units_versions_and_padding_masks() -> None:
    encoded = StateEncoder(schema(), scaler()).encode(state())

    assert encoded.values.dtype == torch.float32
    assert encoded.values.tolist() == pytest.approx([2.0, 1.0])
    assert encoded.collection_mask.dtype == torch.bool
    assert encoded.collection_mask.tolist() == [True, False, False, True, True]
    assert encoded.schema_version == "rich-v1"
    assert encoded.scaler_version == "train-fold-1-v1"


def test_scaler_clips_standardized_values() -> None:
    encoded = StateEncoder(schema(), scaler()).encode(
        state(cash_usd=Decimal("10000.00"), spread_usd=Decimal("-100.00"))
    )
    assert encoded.values.tolist() == [10.0, -10.0]


def test_schema_validates_categorical_vocabulary() -> None:
    with pytest.raises(StateValidationError, match="categorical"):
        StateEncoder(schema(), scaler()).encode(state(regime="unknown"))


def test_missingness_is_declared_and_deterministic_for_optional_fields() -> None:
    optional_schema = StateSchema(
        version="optional-v1",
        continuous=("cash_usd",),
        required=("cash_usd",),
        categorical_vocabularies={"regime": ("normal", "restock")},
        collection_limits={"open_orders": 2},
    )
    encoded = StateEncoder(
        optional_schema,
        Scaler("s1", "fold", {"cash_usd": 0.0}, {"cash_usd": 1.0}),
    ).encode({"cash_usd": Decimal("1.00")})

    assert encoded.missingness.dtype == torch.bool
    assert encoded.missingness.tolist() == [False, True, True]
    assert encoded.collection_mask.tolist() == [False, False]


@pytest.mark.parametrize(
    "bad_state",
    [
        {"spread_usd": Decimal("7.00"), "regime": "normal"},
        {"cash_usd": Decimal("NaN"), "spread_usd": Decimal("7.00"), "regime": "normal"},
        {"cash_usd": Decimal("140.00"), "spread_usd": float("inf"), "regime": "normal"},
    ],
)
def test_required_missing_or_non_finite_state_is_quarantined(
    bad_state: dict[str, object],
) -> None:
    with pytest.raises(StateValidationError):
        StateEncoder(schema(), scaler()).encode(bad_state)


def test_scaler_fit_is_train_only_and_records_fold_lineage() -> None:
    rows = [
        {"cash_usd": 80.0, "spread_usd": 3.0},
        {"cash_usd": 120.0, "spread_usd": 7.0},
    ]
    fitted = Scaler.fit(
        rows,
        "train",
        version="fold-1-v1",
        fold_hash="fold-1-sha256",
    )

    assert fitted.fold_hash == "fold-1-sha256"
    assert fitted.means == {"cash_usd": 100.0, "spread_usd": 5.0}
    assert fitted.scales == {"cash_usd": 20.0, "spread_usd": 2.0}
    with pytest.raises(ValueError, match="train"):
        Scaler.fit(rows, "validation", version="bad", fold_hash="fold-1-sha256")


def test_mask_builder_requires_inventory_for_quote_and_quote_for_cancel() -> None:
    builder = MaskBuilder()
    base = {
        "bid_offset_low": -3,
        "bid_offset_high": 3,
        "ask_offset_low": -4,
        "ask_offset_high": 4,
    }

    mask, bounds = builder.build(
        {**base, "sellable_inventory": 0, "cancellable_quote": False}
    )
    assert mask == ActionMask(no_op=True, quote=False, cancel=False)
    assert bounds == ActionBounds(-3, 3, -4, 4)

    mask, _ = builder.build({**base, "sellable_inventory": 1, "cancellable_quote": True})
    assert mask == ActionMask(no_op=True, quote=True, cancel=True)


def test_mask_builder_rejects_missing_or_invalid_bounds() -> None:
    with pytest.raises(StateValidationError):
        MaskBuilder().build(
            {
                "sellable_inventory": 1,
                "cancellable_quote": False,
                "bid_offset_low": -3,
                "bid_offset_high": 3,
                "ask_offset_low": 4,
                "ask_offset_high": -4,
            }
        )
