# Ship deterministic paper MM before wiring model shadow

The Continuous Paper Market-Maker’s missing core is replay → quote → gate → paper execution → inventory/P&L → Ops Dashboard. Research shadow/advisory already exists separately and must never override the Deterministic Gate. The First Shippable Slice therefore runs Deterministic Strategy only; model influence in the quote loop is a later slice. Rejected: requiring shadow wiring inside the first MM vertical.
