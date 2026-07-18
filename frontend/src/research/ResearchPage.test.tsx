import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ResearchPage, ResearchPageLoader } from "./ResearchPage";

afterEach(cleanup);

const assumptions = {
  episode_hash: "episodes-sha256",
  fee_version: "fees-v3",
  slippage_version: "slippage-v2",
  logistics_version: "logistics-v4",
  terminal_policy_version: "terminal-v2",
  gate_policy_version: "gates-v5",
  latency_ms: 25,
};

const tracks = [
  {
    id: "deterministic",
    kind: "deterministic" as const,
    name: "Deterministic",
    provenance: "historical" as const,
    ope: { valid: true, summary: "Supported historical evaluation" },
    netReturn: { point: 0.12, lower: 0.08, upper: 0.16 },
  },
  {
    id: "pfhedge",
    kind: "pfhedge" as const,
    name: "PFHedge",
    provenance: "synthetic" as const,
    ope: { valid: false, summary: "Missing trustworthy propensities" },
    netReturn: { point: 0.1, lower: 0.04, upper: 0.14 },
  },
  {
    id: "iql",
    kind: "iql" as const,
    name: "IQL",
    provenance: "historical" as const,
    ope: { valid: true, summary: "WIS supported" },
    netReturn: { point: 0.14, lower: 0.09, upper: 0.18 },
  },
];

const registry = {
  model_id: "00000000-0000-0000-0000-000000000019",
  artifact_hash: "a".repeat(64),
  compatibility: {
    state_schema_version: "state-v1",
    action_schema_version: "action-v1",
    encoder_version: "encoder-v1",
    reward_version: "reward-v1",
    architecture: "iql-v1",
    environment_hash: "b".repeat(64),
  },
  benchmark_report_id: "00000000-0000-0000-0000-000000000020",
  state: "shadow" as const,
  created_at: "2026-07-17T12:00:00Z",
};

const quote = {
  category: "QUOTE" as const,
  allocation: 0.5,
  bid_offset_ticks: -2,
  ask_offset_ticks: 2,
};

const trace = {
  request_id: "00000000-0000-0000-0000-000000000022",
  deterministic_action: { ...quote, allocation: 0.4 },
  pfhedge_action: { ...quote, allocation: 0.6 },
  iql_action: quote,
  canonical_action: quote,
  gate_results: [
    ["schema", true],
    ["capital", false],
  ] as [string, boolean][],
  final_action: { category: "NO_OP" as const, allocation: 0, bid_offset_ticks: 0, ask_offset_ticks: 0 },
  fallback_reason: "gate_failed:capital",
};

describe("ResearchPage", () => {
  it("presents governed comparisons and the complete recommendation trace", () => {
    render(
      <ResearchPage
        assumptions={assumptions}
        tracks={tracks}
        registry={registry}
        trace={trace}
      />,
    );

    expect(screen.getByRole("heading", { name: "Frozen assumptions" })).toBeVisible();
    expect(screen.getByText("fees-v3")).toBeVisible();
    expect(screen.getAllByText("Historical")).toHaveLength(2);
    expect(screen.getByText("Synthetic")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "PFHedge — Direct hedging baseline" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "IQL — Custom Bellman IQL" }),
    ).toBeVisible();
    expect(screen.getByText("Net return 95% CI: 0.04 to 0.14")).toBeVisible();
    expect(screen.getByText("OPE not valid")).toBeVisible();

    const registryTable = screen.getByRole("table", { name: "Model registry status" });
    expect(within(registryTable).getByText("shadow")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Serving mode: deterministic-only",
    );

    const traceTable = screen.getByRole("table", { name: "Recommendation trace" });
    for (const stage of ["Deterministic", "PFHedge", "IQL", "Canonical", "Gate", "Final"]) {
      expect(within(traceTable).getByText(stage)).toBeVisible();
    }
    expect(
      screen.getByRole("button", { name: "Request advisory approval" }),
    ).toBeEnabled();
  });

  it("fails closed when research data cannot be loaded", async () => {
    render(
      <ResearchPageLoader
        load={async () => ({
          status: "deterministic-only",
          message: "Research API unavailable",
        })}
      />,
    );

    const fallback = await screen.findByText(
      "Deterministic-only — research data unavailable",
    );
    expect(fallback).toHaveAttribute("role", "status");
    expect(screen.queryByText(/advisory approved/i)).not.toBeInTheDocument();
  });
});
