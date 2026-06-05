export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/backend";

export type Snapshot = {
  snapshot_id: string;
  market: string;
  source_id: string;
  snapshot_date: string;
  file_hash: string;
  row_count: number;
  ingestion_mode: string;
  created_at: string;
};

export type Source = {
  source_id: string;
  source_name: string;
  source_url: string;
  source_type: string;
  notes: string;
  snapshot_count: number;
};

export type BriefRequest = {
  market: string;
  project_type: string;
  county: string;
  capacity_mw: number;
  target_cod_year: number;
  question: string;
  min_sample_n: number;
};

export type Brief = {
  title: string;
  executive_summary: string[];
  queue_snapshot: {
    snapshot_id: string;
    snapshot_date: string;
    matching_records: number;
    active_count: number;
    active_mw: number;
    status_counts: Record<string, number>;
    citation_ids: string[];
  };
  comparable_projects: Array<Record<string, unknown>>;
  monthly_changes: {
    counts_by_event_type: Record<string, number>;
    events: Array<Record<string, unknown>>;
  };
  historical_proxy: Record<string, unknown>;
  large_load_context: Record<string, unknown> | null;
  caveats_and_abstentions: string[];
  citations: Array<Record<string, unknown>>;
  reproducibility_trace: string[];
  markdown: string;
};

export type FlexibilityRequest = {
  market: string;
  jurisdiction: string;
  county: string;
  peak_mw: number;
  average_load_factor: number;
  commitment_depth_pct: number;
  event_duration_hours: number;
  events_per_year: number;
  deferrable_workload_fraction: number;
  latency_sensitive_fraction: number;
  migratable_fraction: number;
  gpu_power_kw: number;
  gpu_hour_value_usd: number;
  deferral_penalty_per_gpu_hour_usd: number;
  migration_penalty_per_gpu_hour_usd: number;
  dropped_work_penalty_per_gpu_hour_usd: number;
  colocated_generation: boolean;
  dispatchable_or_curtailable: boolean | null;
  metering_or_control_capability: boolean | null;
  baseline_project_type: string;
  min_sample_n: number;
  value_per_day_usd: number | null;
};

export type FlexibilityBrief = {
  title: string;
  executive_summary: string[];
  input_scenario: Record<string, unknown>;
  relevant_flexibility_rules: Array<Record<string, unknown>>;
  eligibility_assessment: Array<Record<string, unknown>>;
  compute_cost_estimate: Record<string, unknown>;
  interconnection_benefit_assessment: Record<string, unknown>;
  commitment_tradeoff_table: Array<Record<string, unknown>>;
  recommendation: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  reproducibility_trace: string[];
  caveats_and_abstentions: string[];
  markdown: string;
  brief_id: string;
  scenario_id: string;
};

export type WatcherRequest = {
  mode: "fixture" | "manual" | "live";
  period_start: string;
  period_end: string;
  market: string;
  from_snapshot_id: string | null;
  to_snapshot_id: string | null;
  top_n: number;
};

export type WatcherDigest = {
  digest_id: string;
  title: string;
  executive_summary: string[];
  top_queue_changes: Array<Record<string, unknown>>;
  top_regulatory_changes: Array<Record<string, unknown>>;
  flexibility_rule_watch: Array<Record<string, unknown>>;
  suppressed_ambiguous: Array<Record<string, unknown>>;
  parse_failures: Array<Record<string, unknown>>;
  metrics_summary: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  reproducibility_trace: string[];
  caveats: string[];
  markdown: string;
  markdown_path: string;
};

export type WatcherRunResult = {
  status: string;
  digest: WatcherDigest;
  change_event_count: number;
};

export type TimeToPowerRequest = {
  scenario_name: string;
  market: string;
  jurisdiction: string;
  county: string | null;
  region: string | null;
  project_type: string;
  peak_mw: number;
  average_load_factor: number;
  interconnection_voltage_kv: number | null;
  target_online_year: number | null;
  target_online_date: string | null;
  commitment_depth_pct: number;
  event_duration_hours: number;
  events_per_year: number;
  procurement_strategy: "post_ntp_serial" | "at_risk_overlap" | "procurement_started" | "unknown";
  equipment_scope_mode: "generated_planning_model" | "manual_user_selected" | "fixture_demo" | "insufficient_data";
  manual_equipment_scope_json: Array<Record<string, unknown>> | Record<string, unknown> | null;
  min_sample_n: number;
  stale_threshold_months: number;
  commissioning_low_days: number | null;
  commissioning_high_days: number | null;
  energization_buffer_low_days: number | null;
  energization_buffer_high_days: number | null;
  deferrable_workload_fraction: number;
  latency_sensitive_fraction: number;
  migratable_fraction: number;
  gpu_power_kw: number;
  gpu_hour_value_usd: number;
  deferral_penalty_per_gpu_hour_usd: number;
  migration_penalty_per_gpu_hour_usd: number;
  dropped_work_penalty_per_gpu_hour_usd: number;
  colocated_generation: boolean;
  dispatchable_or_curtailable: boolean | null;
  metering_or_control_capability: boolean | null;
};

export type TimeToPowerBrief = {
  brief_id: string;
  title: string;
  executive_summary: string[];
  project_scenario: Record<string, unknown>;
  interconnection_baseline: Record<string, unknown>;
  flexibility_adjusted_scenario: Record<string, unknown>;
  procurement_critical_path: Record<string, unknown>;
  energization_timeline: Record<string, unknown>;
  scenario_comparison_table: Array<Record<string, unknown>>;
  binding_constraints: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  reproducibility_trace: string[];
  caveats_and_abstentions: string[];
  estimate: Record<string, unknown>;
  markdown: string;
  markdown_path: string;
};

export type DiffResult = {
  from_snapshot_id: string;
  to_snapshot_id: string;
  counts_by_event_type: Record<string, number>;
  event_count: number;
  events: Array<Record<string, unknown>>;
};

export type EntityMatches = {
  snapshot_id: string;
  matches: Array<Record<string, unknown>>;
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json() as Promise<T>;
}
