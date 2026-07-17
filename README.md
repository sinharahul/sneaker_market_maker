# Sneaker Market Maker

A conservative, fee-aware analytics core for evaluating sneaker resale
opportunities. It normalizes marketplace observations, prices all transaction
friction, rejects trades that violate explicit risk limits, and simulates
holding-period price risk.

This project does **not** bypass marketplace protections or place live orders.
Connect only through documented, authorized marketplace integrations and keep a
human approval step until the strategy has been validated with real data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Example

```python
from decimal import Decimal

from sneaker_market_maker import (
    FeeSchedule,
    OpportunityEvaluator,
    SneakerDataPipeline,
)

payload = {
    "platform": "stockx",
    "styleCode": "DD1391-100",
    "shoeSize": 10,
    "highestBid": 100,
    "lowestAsk": 150,
    "daysSinceRelease": 100,
    "recentSales": [{"price": 140}, {"price": 145}, {"price": 150}],
}

snapshot, _ = SneakerDataPipeline().parse_payload(payload)
fees = FeeSchedule(
    seller_rate=Decimal("0.10"),
    processor_rate=Decimal("0.03"),
    inbound_shipping=Decimal("8"),
    outbound_shipping=Decimal("2"),
)
result = OpportunityEvaluator(fees).evaluate(snapshot)
print(result)
```

## Design choices

- `Decimal` is used for all money and fee arithmetic.
- Invalid market payloads fail closed rather than becoming zero-filled data.
- Risk rejections have deterministic priority and machine-readable reasons.
- NumPy arrays are reserved for analytics and simulation, not accounting.
- Simulations can be seeded and can model discrete restock/event shocks.

GBM is only a baseline. Before using capital, backtest size-specific sales,
model restocks as discontinuous shocks, account for failed authentication and
shipping delays, and validate the exact fee schedule for each account.
