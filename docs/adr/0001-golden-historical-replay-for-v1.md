# Use a golden historical-shaped replay dataset for V1 paper MM

Version 1 Continuous Paper Market-Maker needs an authoritative StockX Historical Replay driver, but the repo had no real historical dump. We accept a versioned, checksummed Golden Historical Replay Dataset (allowlisted families only) as that V1 artifact so the engine and Ops Dashboard can ship; a larger real dump may replace it later without changing the market-event port. Rejected: blocking on a full raw dump (A), and shipping fixture-only without a historical-replay claim (C).
