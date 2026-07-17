from decimal import Decimal

import numpy as np
import pytest

from sneaker_market_maker.pipeline import PayloadError, SneakerDataPipeline

STOCKX_PAYLOAD = {
    "platform": "stockx",
    "styleCode": "DD1391-100",
    "shoeSize": 10,
    "highestBid": 180,
    "lowestAsk": 195,
    "daysSinceRelease": 4,
    "recentSales": [{"price": 185}, {"price": 190}, {"price": 175}],
    "fee_tier": 0.13,
}


def test_normalizes_camel_case_payload() -> None:
    snapshot, fee = SneakerDataPipeline().parse_payload(STOCKX_PAYLOAD)
    assert snapshot.platform == "stockx"
    assert snapshot.style_code == "DD1391-100"
    assert snapshot.highest_bid == Decimal("180")
    assert snapshot.sales_48h == 3
    assert float(snapshot.volatility_48h) == pytest.approx(7.637626, rel=1e-6)
    assert fee == Decimal("0.13")


def test_normalizes_snake_case_json_and_fallback_volatility() -> None:
    payload = """
    {
      "source": "goat",
      "style_code": "ABC-123",
      "size": "9.5",
      "highest_bid": "240.00",
      "lowest_ask": 260,
      "days_released": 12,
      "completed_sales": [{"price": 245}],
      "fallback_volatility": 11
    }
    """
    snapshot, fee = SneakerDataPipeline().parse_payload(payload)
    assert snapshot.shoe_size == Decimal("9.5")
    assert snapshot.volatility_48h == Decimal("11")
    assert fee == Decimal("0.13")


def test_numpy_features_have_stable_shape_and_dtype() -> None:
    result = SneakerDataPipeline().to_numpy([STOCKX_PAYLOAD, STOCKX_PAYLOAD])
    assert result.shape == (2, 5)
    assert result.dtype == np.float32
    np.testing.assert_array_equal(result[0, :3], np.array([180, 195, 4], np.float32))


def test_empty_batch_has_stable_shape() -> None:
    result = SneakerDataPipeline().to_numpy([])
    assert result.shape == (0, 5)


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        {"platform": "stockx", "styleCode": "ABC", "shoeSize": 10},
        {**STOCKX_PAYLOAD, "highestBid": "nan"},
        {**STOCKX_PAYLOAD, "fee_tier": 1},
        {**STOCKX_PAYLOAD, "recentSales": "not-a-list"},
        {**STOCKX_PAYLOAD, "recentSales": [{"price": -2}]},
    ],
)
def test_malformed_payloads_fail_closed(payload: object) -> None:
    with pytest.raises(PayloadError):
        SneakerDataPipeline().parse_payload(payload)  # type: ignore[arg-type]


def test_platform_argument_overrides_payload_source() -> None:
    snapshot, _ = SneakerDataPipeline().parse_payload(
        STOCKX_PAYLOAD, platform="test-platform"
    )
    assert snapshot.platform == "test-platform"
