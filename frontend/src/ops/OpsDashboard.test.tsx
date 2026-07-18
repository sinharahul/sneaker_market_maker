import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OpsDashboard } from "./OpsDashboard";
import type { OpsSnapshot } from "./api";

afterEach(cleanup);

const snapshot = (overrides: Partial<OpsSnapshot["status"]> = {}): OpsSnapshot => ({
  status: {
    run_id: "run-1",
    strategy_enabled: true,
    strategy_mode: "deterministic",
    registry: { model_id: null, state: null },
    inference_latency_budget_ms: 100,
    pause_reason: null,
    fallback_reason: null,
    last_iql_action: null,
    open_orders: 1,
    fills: 1,
    lots: 1,
    capital: {
      initial: "2500.00",
      cash: "2274.00",
      reserved_buy_principal: "0.00",
      available_cash: "2274.00",
    },
    pnl: {
      equity: "2500.00",
      pnl: "0.00",
      inventory_landed_cost: "226.00",
      cash: "2274.00",
    },
    replay: {
      status: "running",
      speed: 1,
      events_emitted: 2,
      events_total: 3,
      dataset_id: "golden-stockx-v1",
      source_kind: "historical",
      simulation_time: "2026-01-02T15:00:10+00:00",
    },
    ...overrides,
  },
  orders: [
    {
      order_id: "o1",
      side: "buy",
      price: "221.00",
      quantity: 1,
      status: "filled",
      product_family: "jordan_1_retro",
      style_code: "555088-001",
    },
  ],
  fills: [
    {
      fill_id: "f1",
      side: "buy",
      execution_price: "221.00",
      total_fees: "5.00",
      source_event_id: "g2",
    },
  ],
  lots: [
    {
      lot_id: "l1",
      state: "available",
      landed_cost: "226.00",
      product_family: "jordan_1_retro",
      style_code: "555088-001",
    },
  ],
});

const idleCommands = {
  load: vi.fn(async () => undefined),
  start: vi.fn(async () => undefined),
  pause: vi.fn(async () => undefined),
  resume: vi.fn(async () => undefined),
  stop: vi.fn(async () => undefined),
  enable: vi.fn(async () => undefined),
  disable: vi.fn(async () => undefined),
  tick: vi.fn(async () => undefined),
  setMode: vi.fn(async () => undefined),
  setBudget: vi.fn(async () => undefined),
};

describe("OpsDashboard", () => {
  it("renders authoritative projections and does not invent book rows", async () => {
    render(<OpsDashboard load={async () => snapshot()} />);
    expect(await screen.findByRole("heading", { name: "Ops Dashboard" })).toBeInTheDocument();
    expect(screen.getByText(/golden-stockx-v1/)).toBeInTheDocument();
    expect(screen.getByText(/Cash: 2274.00/)).toBeInTheDocument();
    expect(screen.getByText(/buy 555088-001 @ 221.00 — filled/)).toBeInTheDocument();
    expect(screen.getByText(/555088-001 available landed 226.00/)).toBeInTheDocument();
    expect(screen.getByText(/Strategy Mode: deterministic/)).toBeInTheDocument();
  });

  it("runs load then refresh from projections after commands", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(
        snapshot({
          strategy_enabled: false,
          replay: {
            status: "empty",
            speed: 1,
            events_emitted: 0,
            events_total: 0,
            dataset_id: null,
            source_kind: null,
            simulation_time: null,
          },
        }),
      )
      .mockResolvedValue(snapshot());
    const commands = { ...idleCommands, load: vi.fn(async () => undefined) };

    render(<OpsDashboard load={load} commands={commands} />);
    await screen.findByRole("heading", { name: "Ops Dashboard" });
    fireEvent.click(screen.getByRole("button", { name: "Load golden replay" }));
    expect(commands.load).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/golden-stockx-v1/)).toBeInTheDocument();
    expect(load.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("requests set-mode from projections-backed controls", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValue(
        snapshot({
          strategy_mode: "advisory",
          registry: { model_id: "iql-1", state: "advisory_approved" },
          inference_latency_budget_ms: 150,
        }),
      );
    const commands = { ...idleCommands, setMode: vi.fn(async () => undefined) };
    render(<OpsDashboard load={load} commands={commands} />);
    await screen.findByText(/Strategy Mode: deterministic/);
    fireEvent.click(screen.getByRole("button", { name: "Mode: advisory" }));
    expect(commands.setMode).toHaveBeenCalledWith("advisory");
    expect(await screen.findByText(/Strategy Mode: advisory/)).toBeInTheDocument();
    expect(screen.getByText(/Registry: iql-1 \(advisory_approved\)/)).toBeInTheDocument();
    expect(screen.getByText(/Latency budget: 150ms/)).toBeInTheDocument();
  });

  it("labels IQL pause distinctly and shows last IQL action", async () => {
    render(
      <OpsDashboard
        load={async () =>
          snapshot({
            strategy_mode: "iql_primary",
            pause_reason: "iql_unavailable",
            replay: {
              status: "paused",
              speed: 1,
              events_emitted: 1,
              events_total: 3,
              dataset_id: "golden-stockx-v1",
              source_kind: "historical",
              simulation_time: null,
            },
            last_iql_action: {
              source: "iql_primary",
              category: "QUOTE",
              allocation: 0.5,
              bid_offset_ticks: 2,
              ask_offset_ticks: -2,
            },
          })
        }
      />,
    );
    expect(await screen.findByText(/paused \(IQL unavailable\)/)).toBeInTheDocument();
    expect(screen.getByText(/Last IQL action: QUOTE bid 2 ask -2/)).toBeInTheDocument();
  });

  it("fails closed when projections are unavailable", async () => {
    render(
      <OpsDashboard
        load={async () => {
          throw new Error("Paper status unavailable");
        }}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Paper status unavailable");
  });
});
