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
