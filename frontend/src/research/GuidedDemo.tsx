import { useEffect, useMemo, useState } from "react";

import { createDemoService, DemoService } from "./demoService";
import type { ActionView, DemoSnapshotView } from "./types";

const DEFAULT_BEAT_INTERVAL_MS = 1000;

function formatAction(action: ActionView): string {
  return `${action.category}; allocation ${action.allocation}; bid ${action.bid_offset_ticks}; ask ${action.ask_offset_ticks}`;
}

function formatMoney(value: string): string {
  return `$${value}`;
}

export interface GuidedDemoProps {
  createService?: () => DemoService;
  beatIntervalMs?: number;
}

export function GuidedDemo({
  createService = createDemoService,
  beatIntervalMs = DEFAULT_BEAT_INTERVAL_MS,
}: GuidedDemoProps): JSX.Element {
  const service = useMemo(() => createService(), [createService]);
  const [snapshot, setSnapshot] = useState<DemoSnapshotView>(() => service.snapshot());

  useEffect(() => {
    if (snapshot.paused) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setSnapshot(service.step());
    }, beatIntervalMs);

    return () => {
      window.clearInterval(timer);
    };
  }, [beatIntervalMs, service, snapshot.paused]);

  const updateSnapshot = (next: DemoSnapshotView) => {
    setSnapshot(next);
  };

  return (
    <main>
      <h1>Guided demo</h1>
      <p role="status" aria-live="polite" aria-label="Demo beat">
        {snapshot.beat}
      </p>

      <div role="toolbar" aria-label="Guided demo controls">
        <button
          type="button"
          aria-label="Pause demo"
          onClick={() => updateSnapshot(service.pause())}
        >
          Pause
        </button>
        <button
          type="button"
          aria-label="Resume demo"
          onClick={() => updateSnapshot(service.resume())}
        >
          Resume
        </button>
        <button
          type="button"
          aria-label="Step demo forward"
          onClick={() => updateSnapshot(service.step())}
        >
          Step
        </button>
        <button
          type="button"
          aria-label="Restart demo"
          onClick={() => updateSnapshot(service.restart())}
        >
          Restart
        </button>
      </div>

      <section role="region" aria-label="Guided demo frame">
        <h2>{snapshot.beat}</h2>
        <p>Simulation second: {snapshot.simulation_second}</p>
        <p>Deterministic action: {formatAction(snapshot.deterministic_action)}</p>
        <p>PFHedge score: {snapshot.pfhedge_score}</p>
        <p>IQL shadow action: {formatAction(snapshot.iql_shadow_action)}</p>
        <p>Final gated action: {formatAction(snapshot.final_action)}</p>
        <p>Inventory lifecycle: {snapshot.inventory_state}</p>
        <p>Cash: {formatMoney(snapshot.cash)}</p>
        <p>NAV: {formatMoney(snapshot.nav)}</p>
        <p>Realized P&L: {formatMoney(snapshot.realized_pnl)}</p>
        <p>Unrealized P&L: {formatMoney(snapshot.unrealized_pnl)}</p>

        <table>
          <caption>Itemized fees</caption>
          <thead>
            <tr>
              <th scope="col">Component</th>
              <th scope="col">Amount</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(snapshot.fees).map(([name, amount]) => (
              <tr key={name}>
                <th scope="row">{name.replaceAll("_", " ")}</th>
                <td>{formatMoney(amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
