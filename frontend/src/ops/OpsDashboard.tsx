import { useCallback, useEffect, useState } from "react";

import {
  loadOpsSnapshot,
  paperOpsCommands,
  type OpsSnapshot,
} from "./api";

type OpsDashboardProps = {
  load?: typeof loadOpsSnapshot;
  commands?: typeof paperOpsCommands;
};

function pauseLabel(status: OpsSnapshot["status"]): string {
  if (status.pause_reason === "iql_unavailable") {
    return "paused (IQL unavailable)";
  }
  if (status.pause_reason === "operator") {
    return "paused (operator)";
  }
  return status.replay.status;
}

export function OpsDashboard({
  load = loadOpsSnapshot,
  commands = paperOpsCommands,
}: OpsDashboardProps): JSX.Element {
  const [snapshot, setSnapshot] = useState<OpsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const next = await load();
      setSnapshot(next);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ops projections unavailable");
      setSnapshot(null);
    }
  }, [load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<void>): Promise<void> {
    setBusy(true);
    try {
      await action();
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Command failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Ops Dashboard</h1>
      <p>
        Continuous Paper Market-Maker control plane. Projections from{" "}
        <code>/api/paper</code> are authoritative — this UI does not invent book
        state.
      </p>

      <section aria-labelledby="ops-controls">
        <h2 id="ops-controls">Replay and strategy</h2>
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => void run(commands.load)}>
            Load golden replay
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.start)}>
            Start
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.pause)}>
            Pause
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.resume)}>
            Resume
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.stop)}>
            Stop
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.enable)}>
            Enable strategy
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.disable)}>
            Disable strategy
          </button>
          <button type="button" disabled={busy} onClick={() => void run(commands.tick)}>
            Tick
          </button>
          <button type="button" disabled={busy} onClick={() => void refresh()}>
            Refresh projections
          </button>
        </div>
      </section>

      <section aria-labelledby="ops-mode">
        <h2 id="ops-mode">Strategy Mode</h2>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => commands.setMode("deterministic"))}
          >
            Mode: deterministic
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => commands.setMode("advisory"))}
          >
            Mode: advisory
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => commands.setMode("iql_primary"))}
          >
            Mode: iql_primary
          </button>
        </div>
      </section>

      {error !== null ? <p role="alert">{error}</p> : null}
      {snapshot === null && error === null ? (
        <p role="status">Loading paper projections</p>
      ) : null}

      {snapshot !== null ? (
        <>
          <section aria-labelledby="ops-status">
            <h2 id="ops-status">Status</h2>
            <p>{`Replay: ${pauseLabel(snapshot.status)} (${snapshot.status.replay.events_emitted}/${snapshot.status.replay.events_total})`}</p>
            <p>{`Dataset: ${snapshot.status.replay.dataset_id ?? "none"}`}</p>
            <p>{`Strategy: ${snapshot.status.strategy_enabled ? "enabled" : "disabled"}`}</p>
            <p>{`Strategy Mode: ${snapshot.status.strategy_mode}`}</p>
            <p>{`Registry: ${snapshot.status.registry.model_id ?? "none"} (${snapshot.status.registry.state ?? "unbound"})`}</p>
            <p>{`Latency budget: ${snapshot.status.inference_latency_budget_ms}ms`}</p>
            <p>{`Fallback: ${snapshot.status.fallback_reason ?? "none"}`}</p>
            <p>
              {`Last IQL action: ${
                snapshot.status.last_iql_action === null
                  ? "none"
                  : `${snapshot.status.last_iql_action.category} bid ${snapshot.status.last_iql_action.bid_offset_ticks} ask ${snapshot.status.last_iql_action.ask_offset_ticks}`
              }`}
            </p>
            <p>{`Cash: ${snapshot.status.capital.cash} / initial ${snapshot.status.capital.initial}`}</p>
            <p>{`P&L: ${snapshot.status.pnl.pnl} (equity ${snapshot.status.pnl.equity})`}</p>
          </section>

          <section aria-labelledby="ops-orders">
            <h2 id="ops-orders">Paper Orders</h2>
            {snapshot.orders.length === 0 ? (
              <p>No orders yet.</p>
            ) : (
              <ul>
                {snapshot.orders.map((order) => (
                  <li key={order.order_id}>
                    {`${order.side} ${order.style_code} @ ${order.price} — ${order.status}`}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="ops-fills">
            <h2 id="ops-fills">Fee-Aware Fills</h2>
            {snapshot.fills.length === 0 ? (
              <p>No fills yet.</p>
            ) : (
              <ul>
                {snapshot.fills.map((fill) => (
                  <li key={fill.fill_id}>
                    {`${fill.side} @ ${fill.execution_price} fees ${fill.total_fees} (${fill.source_event_id})`}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="ops-lots">
            <h2 id="ops-lots">Inventory Lots</h2>
            {snapshot.lots.length === 0 ? (
              <p>No lots yet.</p>
            ) : (
              <ul>
                {snapshot.lots.map((lot) => (
                  <li key={lot.lot_id}>
                    {`${lot.style_code} ${lot.state} landed ${lot.landed_cost}`}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
