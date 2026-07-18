# Observe-only market data (Track L1)

**Audience:** operators / developers starting live readiness  
**Scope:** read-only StockX-shaped observations  
**Not in scope:** shadow would-quote (L2), kill-switch / ADR-0004 (L3), live-send (L4)

## What L1 is

A **read-only** observation port (`sneaker_market_maker.observe`) that normalizes allowlisted product-family snapshots from recorded fixtures (no HTTP order client, no send credentials).

```python
from sneaker_market_maker.observe import (
    RecordedReadOnlyMarketPort,
    default_observe_fixture_path,
)

port = RecordedReadOnlyMarketPort(default_observe_fixture_path())
snapshots = port.poll()  # jordan_1_retro + nike_dunk_low only
```

Fixture: `data/observe/fixtures/allowlisted_v1/observations.json`.

## Fail-closed rules

- Off-allowlist product families → reject  
- Missing fields / non-finite / crossed book / naive timestamps → `corrupt_payload`  
- No invented bid/ask liquidity  

## Safety

`tests/safety/test_observe_no_send.py` asserts the observe package imports no HTTP/marketplace SDKs and calls no place/submit order methods.

## Next

- **L2:** shadow “would quote” logs against this port (still no send)  
- **L4:** live-send only after ADR-0004 + human gate  
