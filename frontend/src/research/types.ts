export interface FrozenAssumptionsView {
  episode_hash: string;
  fee_version: string;
  slippage_version: string;
  logistics_version: string;
  terminal_policy_version: string;
  gate_policy_version: string;
  latency_ms: number;
}

export interface PolicyTrackView {
  id: string;
  kind: "deterministic" | "heuristic" | "v1_mlp" | "pfhedge" | "iql";
  name: string;
  provenance: "historical" | "synthetic";
  ope: { valid: boolean; summary: string };
  netReturn: { point: number; lower: number; upper: number };
}

export type RegistryState =
  | "candidate"
  | "validated"
  | "shadow"
  | "benchmark_qualified"
  | "advisory_approved"
  | "rolled_back"
  | "rejected";

export interface CompatibilityContractView {
  state_schema_version: string;
  action_schema_version: string;
  encoder_version: string;
  reward_version: string;
  architecture: string;
  environment_hash: string;
}

export interface RegistryView {
  model_id: string;
  artifact_hash: string;
  compatibility: CompatibilityContractView;
  benchmark_report_id: string;
  state: RegistryState;
  created_at: string;
}

export interface ActionView {
  category: "NO_OP" | "QUOTE" | "CANCEL";
  allocation: number;
  bid_offset_ticks: number;
  ask_offset_ticks: number;
}

export interface RecommendationTraceView {
  request_id: string;
  deterministic_action: ActionView;
  pfhedge_action: ActionView | null;
  iql_action: ActionView | null;
  canonical_action: ActionView | null;
  gate_results: [string, boolean][];
  final_action: ActionView;
  fallback_reason: string | null;
}

export interface ResearchPageProps {
  assumptions: FrozenAssumptionsView;
  tracks: PolicyTrackView[];
  registry: RegistryView;
  trace: RecommendationTraceView;
}
