import { useEffect, useState } from "react";

import { loadResearchPage, type ResearchPageLoadResult } from "./api";
import type {
  ActionView,
  PolicyTrackView,
  ResearchPageProps,
} from "./types";

const ASSUMPTION_LABELS: Record<keyof ResearchPageProps["assumptions"], string> = {
  episode_hash: "Episode hash",
  fee_version: "Fee version",
  slippage_version: "Slippage version",
  logistics_version: "Logistics version",
  terminal_policy_version: "Terminal policy version",
  gate_policy_version: "Gate policy version",
  latency_ms: "Latency (ms)",
};

function formatAction(action: ActionView | null): string {
  if (action === null) {
    return "Unavailable";
  }
  return `${action.category}; allocation ${action.allocation}; bid ${action.bid_offset_ticks}; ask ${action.ask_offset_ticks}`;
}

export function PolicyTrack({ track }: { track: PolicyTrackView }): JSX.Element {
  const label =
    track.kind === "pfhedge"
      ? "PFHedge — Direct hedging baseline"
      : track.kind === "iql"
        ? "IQL — Custom Bellman IQL"
        : track.name;
  return (
    <section aria-labelledby={`track-${track.id}`}>
      <h3 id={`track-${track.id}`}>{label}</h3>
      <p>{track.provenance === "historical" ? "Historical" : "Synthetic"}</p>
      <p>{track.ope.valid ? track.ope.summary : "OPE not valid"}</p>
      <p>{`Net return 95% CI: ${track.netReturn.lower} to ${track.netReturn.upper}`}</p>
      <p>{`Net return point estimate: ${track.netReturn.point}`}</p>
    </section>
  );
}

export function ResearchPageError({ message }: { message: string }): JSX.Element {
  return (
    <main>
      <h1>Research comparison</h1>
      <p role="status">Deterministic-only — research data unavailable</p>
      <p role="alert">{message}</p>
    </main>
  );
}

export function ResearchPageLoader({
  load = loadResearchPage,
}: {
  load?: () => Promise<ResearchPageLoadResult>;
}): JSX.Element {
  const [result, setResult] = useState<ResearchPageLoadResult | null>(null);

  useEffect(() => {
    let active = true;
    void load().then((nextResult) => {
      if (active) {
        setResult(nextResult);
      }
    });
    return () => {
      active = false;
    };
  }, [load]);

  if (result === null) {
    return <p role="status">Loading research data</p>;
  }
  if (result.status === "deterministic-only") {
    return <ResearchPageError message={result.message} />;
  }
  return <ResearchPage {...result.data} />;
}

export function ResearchPage({
  assumptions,
  tracks,
  registry,
  trace,
}: ResearchPageProps): JSX.Element {
  const advisoryActive =
    registry.state === "advisory_approved" && trace.fallback_reason === null;
  const gateSummary = trace.gate_results
    .map(([name, passed]) => `${name}: ${passed ? "passed" : "failed"}`)
    .join("; ");

  return (
    <main>
      <h1>Research comparison</h1>
      <p role="status">
        Registry status: {registry.state}. Serving mode:{" "}
        {advisoryActive ? "advisory" : "deterministic-only"}.
      </p>

      <section aria-labelledby="frozen-assumptions">
        <h2 id="frozen-assumptions">Frozen assumptions</h2>
        <table>
          <caption>Evaluation assumptions</caption>
          <tbody>
            {Object.entries(assumptions).map(([name, value]) => (
              <tr key={name}>
                <th scope="row">
                  {ASSUMPTION_LABELS[name as keyof typeof ASSUMPTION_LABELS]}
                </th>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="policy-comparison">
        <h2 id="policy-comparison">Policy comparison</h2>
        {tracks.map((track) => (
          <PolicyTrack key={track.id} track={track} />
        ))}
      </section>

      <section aria-labelledby="registry">
        <h2 id="registry">Registry and lineage</h2>
        <table>
          <caption>Model registry status</caption>
          <tbody>
            <tr>
              <th scope="row">Status</th>
              <td>{registry.state}</td>
            </tr>
            <tr>
              <th scope="row">Model ID</th>
              <td>{registry.model_id}</td>
            </tr>
            <tr>
              <th scope="row">Artifact hash</th>
              <td>{registry.artifact_hash}</td>
            </tr>
            <tr>
              <th scope="row">Benchmark report</th>
              <td>{registry.benchmark_report_id}</td>
            </tr>
            <tr>
              <th scope="row">Created</th>
              <td>{registry.created_at}</td>
            </tr>
            {Object.entries(registry.compatibility).map(([name, value]) => (
              <tr key={name}>
                <th scope="row">{name.replaceAll("_", " ")}</th>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" aria-label="Request advisory approval">
          Request advisory approval
        </button>
      </section>

      <section aria-labelledby="recommendation-trace">
        <h2 id="recommendation-trace">Recommendation trace</h2>
        <p>Request {trace.request_id}</p>
        <table>
          <caption>Recommendation trace</caption>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Deterministic</th>
              <td>{formatAction(trace.deterministic_action)}</td>
            </tr>
            <tr>
              <th scope="row">PFHedge</th>
              <td>{formatAction(trace.pfhedge_action)}</td>
            </tr>
            <tr>
              <th scope="row">IQL</th>
              <td>{formatAction(trace.iql_action)}</td>
            </tr>
            <tr>
              <th scope="row">Canonical</th>
              <td>{formatAction(trace.canonical_action)}</td>
            </tr>
            <tr>
              <th scope="row">Gate</th>
              <td>{gateSummary || "No gate results"}</td>
            </tr>
            <tr>
              <th scope="row">Final</th>
              <td>
                {formatAction(trace.final_action)}
                {trace.fallback_reason === null
                  ? "; no fallback"
                  : `; fallback: ${trace.fallback_reason}`}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  );
}
