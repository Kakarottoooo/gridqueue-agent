"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, BarChart3, BookOpenCheck, Database, FileText, GitCompare, ListChecks, RefreshCw, SearchCode, ShieldCheck, Zap } from "lucide-react";
import { JsonBlock } from "@/components/JsonBlock";
import { apiGet, apiPost, type Brief, type BriefRequest, type DiffResult, type EntityMatches, type FlexibilityBrief, type FlexibilityRequest, type Snapshot, type Source } from "@/lib/api";

type TabKey = "brief" | "flexibility" | "diff" | "metrics" | "matching" | "citations" | "evals";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "brief", label: "Brief" },
  { key: "flexibility", label: "Flexibility Strategy" },
  { key: "diff", label: "Monthly Diff" },
  { key: "metrics", label: "Metrics" },
  { key: "matching", label: "Entity Matching" },
  { key: "citations", label: "Citations" },
  { key: "evals", label: "Evals" }
];

const defaultForm: BriefRequest = {
  market: "ERCOT",
  project_type: "Battery",
  county: "Reeves",
  capacity_mw: 100,
  target_cod_year: 2028,
  question: "What public interconnection risks should I know for a data center load?",
  min_sample_n: 2
};

const defaultFlexForm: FlexibilityRequest = {
  market: "ERCOT",
  jurisdiction: "FERC",
  county: "Reeves",
  peak_mw: 100,
  average_load_factor: 0.85,
  commitment_depth_pct: 25,
  event_duration_hours: 3,
  events_per_year: 20,
  deferrable_workload_fraction: 0.55,
  latency_sensitive_fraction: 0.25,
  migratable_fraction: 0.2,
  gpu_power_kw: 0.7,
  gpu_hour_value_usd: 3,
  deferral_penalty_per_gpu_hour_usd: 0.25,
  migration_penalty_per_gpu_hour_usd: 0.75,
  dropped_work_penalty_per_gpu_hour_usd: 4,
  colocated_generation: false,
  dispatchable_or_curtailable: true,
  metering_or_control_capability: true,
  baseline_project_type: "Battery",
  min_sample_n: 2,
  value_per_day_usd: null
};

export default function Home() {
  const [form, setForm] = useState<BriefRequest>(defaultForm);
  const [flexForm, setFlexForm] = useState<FlexibilityRequest>(defaultFlexForm);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [flexRules, setFlexRules] = useState<Array<Record<string, unknown>>>([]);
  const [fromSnapshot, setFromSnapshot] = useState("");
  const [toSnapshot, setToSnapshot] = useState("");
  const [activeTab, setActiveTab] = useState<TabKey>("brief");
  const [brief, setBrief] = useState<Brief | null>(null);
  const [flexBrief, setFlexBrief] = useState<FlexibilityBrief | null>(null);
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [matches, setMatches] = useState<EntityMatches | null>(null);
  const [evalOutput, setEvalOutput] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("Connect to the API, ingest fixtures, then generate a brief.");
  const [busy, setBusy] = useState(false);

  const latestSnapshot = snapshots.at(-1);

  const loadMetadata = useCallback(async () => {
    const snapshotData = await apiGet<{ snapshots: Snapshot[] }>("/snapshots");
    const sourceData = await apiGet<{ sources: Source[] }>("/sources").catch(() => ({ sources: [] }));
    setSnapshots(snapshotData.snapshots);
    setSources(sourceData.sources);
    if (snapshotData.snapshots.length >= 2) {
      const from = snapshotData.snapshots[snapshotData.snapshots.length - 2].snapshot_id;
      const to = snapshotData.snapshots[snapshotData.snapshots.length - 1].snapshot_id;
      setFromSnapshot((current) => current || from);
      setToSnapshot((current) => current || to);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function initialLoad() {
      try {
        const snapshotData = await apiGet<{ snapshots: Snapshot[] }>("/snapshots");
        const sourceData = await apiGet<{ sources: Source[] }>("/sources").catch(() => ({ sources: [] }));
        if (cancelled) return;
        setSnapshots(snapshotData.snapshots);
        setSources(sourceData.sources);
        if (snapshotData.snapshots.length >= 2) {
          setFromSnapshot(snapshotData.snapshots[snapshotData.snapshots.length - 2].snapshot_id);
          setToSnapshot(snapshotData.snapshots[snapshotData.snapshots.length - 1].snapshot_id);
        }
      } catch (error) {
        if (!cancelled) {
          setStatus(error instanceof Error ? `API not ready: ${error.message}` : "API not ready.");
        }
      }
    }

    void initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedDiffPath = useMemo(() => {
    if (!fromSnapshot || !toSnapshot) return null;
    return `/diff/${fromSnapshot}/${toSnapshot}`;
  }, [fromSnapshot, toSnapshot]);

  async function ingestFixtures() {
    setBusy(true);
    setStatus("Ingesting synthetic fixtures...");
    try {
      await apiPost("/ingest/fixtures");
      await loadMetadata();
      setStatus("Fixtures ingested. Synthetic data is ready for brief generation.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Fixture ingestion failed.");
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    setBusy(true);
    setStatus("Generating deterministic brief...");
    try {
      const briefResult = await apiPost<Brief>("/brief", form);
      setBrief(briefResult);
      setMetrics(briefResult.historical_proxy);
      if (selectedDiffPath) {
        const diffResult = await apiGet<DiffResult>(selectedDiffPath).catch(() => ({
          ...briefResult.monthly_changes,
          event_count: briefResult.monthly_changes.events.length
        } as DiffResult));
        setDiff(diffResult);
      }
      if (latestSnapshot) {
        const matchResult = await apiGet<EntityMatches>(`/entity-matches/${latestSnapshot.snapshot_id}`).catch(() => null);
        setMatches(matchResult);
      }
      setStatus("Brief generated from deterministic data and citation services.");
      setActiveTab("brief");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Brief generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshDiff() {
    if (!selectedDiffPath || !toSnapshot) return;
    setBusy(true);
    try {
      const [diffResult, matchResult] = await Promise.all([
        apiGet<DiffResult>(selectedDiffPath),
        apiGet<EntityMatches>(`/entity-matches/${toSnapshot}`)
      ]);
      setDiff(diffResult);
      setMatches(matchResult);
      setStatus("Diff and entity matching trace refreshed.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Diff refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runEvals() {
    setBusy(true);
    setStatus("Running deterministic evals...");
    try {
      const result = await apiPost<Record<string, unknown>>("/evals/run");
      setEvalOutput(result);
      setStatus("Eval runner finished. See stdout and latest report files.");
      setActiveTab("evals");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Eval run failed.");
    } finally {
      setBusy(false);
    }
  }

  async function seedFlexRules() {
    setBusy(true);
    setStatus("Seeding flexibility rules and evidence records...");
    try {
      await apiPost("/flexibility/seed");
      const result = await apiGet<{ rules: Array<Record<string, unknown>> }>("/flexibility/rules");
      setFlexRules(result.rules);
      setStatus("Flexibility rules seeded with conservative source-backed statuses.");
      setActiveTab("flexibility");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Flexibility rule seed failed.");
    } finally {
      setBusy(false);
    }
  }

  async function generateFlexibilityBrief() {
    setBusy(true);
    setStatus("Generating Flexibility Strategy Brief...");
    try {
      await apiPost("/flexibility/seed");
      const [rulesResult, briefResult] = await Promise.all([
        apiGet<{ rules: Array<Record<string, unknown>> }>("/flexibility/rules"),
        apiPost<{ brief: FlexibilityBrief }>("/flexibility/brief", flexForm)
      ]);
      setFlexRules(rulesResult.rules);
      setFlexBrief(briefResult.brief);
      setStatus("Flexibility Strategy Brief generated with rule statuses, assumptions, and citations.");
      setActiveTab("flexibility");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Flexibility brief generation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="control-panel" aria-label="Project input form">
        <div className="brand-row">
          <div className="brand-mark">GQ</div>
          <div>
            <h1>GridQueue Agent</h1>
            <p>Public-data signal only</p>
          </div>
        </div>

        <div className="status-line" role="status">
          <Activity size={16} aria-hidden="true" />
          <span>{status}</span>
        </div>

        <button className="secondary-button" type="button" onClick={ingestFixtures} disabled={busy}>
          <Database size={17} aria-hidden="true" />
          Ingest fixtures
        </button>

        <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void generate(); }}>
          <label>
            <span>Market</span>
            <select value={form.market} onChange={(event) => setForm({ ...form, market: event.target.value })}>
              <option value="ERCOT">ERCOT</option>
            </select>
          </label>
          <label>
            <span>Project type</span>
            <select value={form.project_type} onChange={(event) => setForm({ ...form, project_type: event.target.value })}>
              <option value="Battery">Battery</option>
              <option value="Solar">Solar</option>
              <option value="Hybrid">Hybrid</option>
              <option value="Wind">Wind</option>
              <option value="Gas">Gas</option>
            </select>
          </label>
          <label>
            <span>County</span>
            <input value={form.county} onChange={(event) => setForm({ ...form, county: event.target.value })} />
          </label>
          <label>
            <span>MW</span>
            <input type="number" value={form.capacity_mw} onChange={(event) => setForm({ ...form, capacity_mw: Number(event.target.value) })} />
          </label>
          <label>
            <span>Target COD year</span>
            <input type="number" value={form.target_cod_year} onChange={(event) => setForm({ ...form, target_cod_year: Number(event.target.value) })} />
          </label>
          <label>
            <span>Min sample N</span>
            <input type="number" min={1} value={form.min_sample_n} onChange={(event) => setForm({ ...form, min_sample_n: Number(event.target.value) })} />
          </label>
          <label className="wide-field">
            <span>Question</span>
            <textarea value={form.question} onChange={(event) => setForm({ ...form, question: event.target.value })} />
          </label>
          <button className="primary-button" type="submit" disabled={busy}>
            <FileText size={18} aria-hidden="true" />
            Generate brief
          </button>
        </form>

        <div className="snapshot-tools">
          <label>
            <span>From snapshot</span>
            <select value={fromSnapshot} onChange={(event) => setFromSnapshot(event.target.value)}>
              {snapshots.map((snapshot) => (
                <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>{snapshot.snapshot_date}</option>
              ))}
            </select>
          </label>
          <label>
            <span>To snapshot</span>
            <select value={toSnapshot} onChange={(event) => setToSnapshot(event.target.value)}>
              {snapshots.map((snapshot) => (
                <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>{snapshot.snapshot_date}</option>
              ))}
            </select>
          </label>
          <button className="secondary-button" type="button" onClick={refreshDiff} disabled={busy || !selectedDiffPath}>
            <RefreshCw size={17} aria-hidden="true" />
            Refresh diff
          </button>
          <button className="secondary-button" type="button" onClick={runEvals} disabled={busy}>
            <ListChecks size={17} aria-hidden="true" />
            Run evals
          </button>
        </div>

        <section className="flex-control-block" aria-label="Flexibility Strategy inputs">
          <div className="control-heading">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>Flexibility Strategy</span>
          </div>
          <button className="secondary-button" type="button" onClick={seedFlexRules} disabled={busy}>
            <Database size={17} aria-hidden="true" />
            Seed flex rules
          </button>
          <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void generateFlexibilityBrief(); }}>
            <label>
              <span>Jurisdiction</span>
              <select value={flexForm.jurisdiction} onChange={(event) => setFlexForm({ ...flexForm, jurisdiction: event.target.value })}>
                <option value="FERC">FERC</option>
                <option value="SPP">SPP</option>
                <option value="PJM">PJM</option>
                <option value="ERCOT">ERCOT</option>
                <option value="DEMO">DEMO</option>
              </select>
            </label>
            <label>
              <span>Peak MW</span>
              <input type="number" value={flexForm.peak_mw} onChange={(event) => setFlexForm({ ...flexForm, peak_mw: Number(event.target.value) })} />
            </label>
            <label>
              <span>Commitment %</span>
              <input type="number" value={flexForm.commitment_depth_pct} onChange={(event) => setFlexForm({ ...flexForm, commitment_depth_pct: Number(event.target.value) })} />
            </label>
            <label>
              <span>Event hours</span>
              <input type="number" value={flexForm.event_duration_hours} onChange={(event) => setFlexForm({ ...flexForm, event_duration_hours: Number(event.target.value) })} />
            </label>
            <label>
              <span>Events / year</span>
              <input type="number" value={flexForm.events_per_year} onChange={(event) => setFlexForm({ ...flexForm, events_per_year: Number(event.target.value) })} />
            </label>
            <label>
              <span>Deferrable frac.</span>
              <input type="number" step="0.01" value={flexForm.deferrable_workload_fraction} onChange={(event) => setFlexForm({ ...flexForm, deferrable_workload_fraction: Number(event.target.value) })} />
            </label>
            <label>
              <span>Migratable frac.</span>
              <input type="number" step="0.01" value={flexForm.migratable_fraction} onChange={(event) => setFlexForm({ ...flexForm, migratable_fraction: Number(event.target.value) })} />
            </label>
            <label>
              <span>Latency-sensitive frac.</span>
              <input type="number" step="0.01" value={flexForm.latency_sensitive_fraction} onChange={(event) => setFlexForm({ ...flexForm, latency_sensitive_fraction: Number(event.target.value) })} />
            </label>
            <label>
              <span>GPU power kW</span>
              <input type="number" step="0.01" value={flexForm.gpu_power_kw} onChange={(event) => setFlexForm({ ...flexForm, gpu_power_kw: Number(event.target.value) })} />
            </label>
            <label>
              <span>Deferral penalty</span>
              <input type="number" step="0.01" value={flexForm.deferral_penalty_per_gpu_hour_usd} onChange={(event) => setFlexForm({ ...flexForm, deferral_penalty_per_gpu_hour_usd: Number(event.target.value) })} />
            </label>
            <label>
              <span>Migration penalty</span>
              <input type="number" step="0.01" value={flexForm.migration_penalty_per_gpu_hour_usd} onChange={(event) => setFlexForm({ ...flexForm, migration_penalty_per_gpu_hour_usd: Number(event.target.value) })} />
            </label>
            <label>
              <span>Dropped work penalty</span>
              <input type="number" step="0.01" value={flexForm.dropped_work_penalty_per_gpu_hour_usd} onChange={(event) => setFlexForm({ ...flexForm, dropped_work_penalty_per_gpu_hour_usd: Number(event.target.value) })} />
            </label>
            <label>
              <span>Value / day</span>
              <input type="number" value={flexForm.value_per_day_usd ?? ""} onChange={(event) => setFlexForm({ ...flexForm, value_per_day_usd: event.target.value ? Number(event.target.value) : null })} />
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={Boolean(flexForm.dispatchable_or_curtailable)} onChange={(event) => setFlexForm({ ...flexForm, dispatchable_or_curtailable: event.target.checked })} />
              <span>Curtailable control</span>
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={Boolean(flexForm.metering_or_control_capability)} onChange={(event) => setFlexForm({ ...flexForm, metering_or_control_capability: event.target.checked })} />
              <span>Metering/control capability</span>
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={flexForm.colocated_generation} onChange={(event) => setFlexForm({ ...flexForm, colocated_generation: event.target.checked })} />
              <span>Co-located generation</span>
            </label>
            <button className="primary-button" type="submit" disabled={busy}>
              <Zap size={18} aria-hidden="true" />
              Generate flex brief
            </button>
          </form>
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p>Latest snapshot</p>
            <strong>{latestSnapshot ? `${latestSnapshot.snapshot_date} · ${latestSnapshot.row_count} rows` : "No snapshot loaded"}</strong>
          </div>
          <div>
            <p>Sources</p>
            <strong>{sources.length}</strong>
          </div>
        </header>

        <nav className="tabbar" aria-label="Result views">
          {tabs.map((tab) => (
            <button key={tab.key} className={activeTab === tab.key ? "active-tab" : ""} type="button" onClick={() => setActiveTab(tab.key)}>
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="tab-panel">
          {activeTab === "brief" && <BriefTab brief={brief} />}
          {activeTab === "flexibility" && <FlexibilityTab brief={flexBrief} rules={flexRules} />}
          {activeTab === "diff" && <DiffTab diff={diff} />}
          {activeTab === "metrics" && <MetricsTab metrics={metrics ?? brief?.historical_proxy ?? null} />}
          {activeTab === "matching" && <MatchesTab matches={matches} />}
          {activeTab === "citations" && <CitationsTab brief={brief} sources={sources} />}
          {activeTab === "evals" && <EvalsTab evalOutput={evalOutput} />}
        </div>
      </section>
    </main>
  );
}

function FlexibilityTab({ brief, rules }: { brief: FlexibilityBrief | null; rules: Array<Record<string, unknown>> }) {
  if (!brief && !rules.length) {
    return <EmptyState icon={<ShieldCheck size={24} />} title="No flexibility strategy loaded" body="Seed flexibility rules or generate a Flexibility Strategy Brief." />;
  }
  if (!brief) {
    return (
      <div className="content-stack">
        <section>
          <h2>Seeded Flexibility Rules</h2>
          <DataTable rows={rules} columns={["jurisdiction", "provision_name", "status", "provision_type", "source_url"]} />
        </section>
      </div>
    );
  }
  return (
    <div className="content-stack">
      <section className="brief-banner">
        <AlertTriangle size={20} aria-hidden="true" />
        <span>{brief.caveats_and_abstentions[0]}</span>
      </section>
      <section>
        <h2>Executive Summary</h2>
        <ul className="plain-list">
          {brief.executive_summary.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>
      <section className="metric-strip">
        <Metric label="Rule status" value={String(brief.relevant_flexibility_rules[0]?.rule_status ?? "NA")} />
        <Metric label="Eligibility" value={String(brief.relevant_flexibility_rules[0]?.eligibility_status ?? "NA")} />
        <Metric label="Compute cost" value={`$${Number(brief.compute_cost_estimate.estimated_compute_cost_usd ?? 0).toLocaleString()}`} />
        <Metric label="Benefit status" value={String(brief.interconnection_benefit_assessment.benefit_status ?? "NA")} />
      </section>
      <section>
        <h2>Relevant Flexibility Rules</h2>
        <DataTable rows={brief.relevant_flexibility_rules} columns={["jurisdiction", "provision_name", "rule_status", "eligibility_status", "source_url"]} />
      </section>
      <section>
        <h2>Commitment Tradeoff</h2>
        <DataTable rows={brief.commitment_tradeoff_table} columns={["commitment_depth_pct", "annual_curtailed_mwh", "estimated_compute_cost_usd", "estimated_timeline_delta_days", "benefit_status", "net_benefit_score"]} />
      </section>
      <section>
        <h2>Assumptions</h2>
        <JsonBlock value={brief.assumptions} />
      </section>
      <section>
        <h2>Citations</h2>
        <DataTable rows={brief.citations} columns={["citation_label", "citation_text", "source_url"]} />
      </section>
      <section>
        <h2>Reproducibility Trace</h2>
        <ul className="trace-list">
          {brief.reproducibility_trace.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>
    </div>
  );
}

function BriefTab({ brief }: { brief: Brief | null }) {
  if (!brief) return <EmptyState icon={<BookOpenCheck size={24} />} title="No brief generated" body="Use the project form to generate a deterministic public-data brief." />;
  return (
    <div className="content-stack">
      <section className="brief-banner">
        <BookOpenCheck size={20} aria-hidden="true" />
        <span>{brief.caveats_and_abstentions[0]}</span>
      </section>
      <section>
        <h2>Executive Summary</h2>
        <ul className="plain-list">
          {brief.executive_summary.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>
      <section className="metric-strip">
        <Metric label="Matching records" value={brief.queue_snapshot.matching_records} />
        <Metric label="Active MW" value={brief.queue_snapshot.active_mw} />
        <Metric label="Sample N" value={String(brief.historical_proxy.sample_n ?? "NA")} />
        <Metric label="Confidence" value={String(brief.historical_proxy.confidence ?? "NA")} />
      </section>
      <section>
        <h2>Comparable Projects</h2>
        <DataTable rows={brief.comparable_projects} columns={["project_name", "queue_id", "capacity_mw", "normalized_status", "target_cod"]} />
      </section>
      <section>
        <h2>Reproducibility Trace</h2>
        <ul className="trace-list">
          {brief.reproducibility_trace.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>
    </div>
  );
}

function DiffTab({ diff }: { diff: DiffResult | null }) {
  if (!diff) return <EmptyState icon={<GitCompare size={24} />} title="No diff loaded" body="Ingest fixtures or select snapshots, then refresh the diff." />;
  return (
    <div className="content-stack">
      <section className="metric-strip">
        <Metric label="Events" value={diff.event_count} />
        {Object.entries(diff.counts_by_event_type).slice(0, 5).map(([key, value]) => <Metric key={key} label={key} value={value} />)}
      </section>
      <DataTable rows={diff.events} columns={["event_type", "severity", "confidence", "explanation"]} />
    </div>
  );
}

function MetricsTab({ metrics }: { metrics: Record<string, unknown> | null }) {
  if (!metrics) return <EmptyState icon={<BarChart3 size={24} />} title="No metrics loaded" body="Generate a brief to compute sample-aware metric rollups." />;
  return <JsonBlock value={metrics} />;
}

function MatchesTab({ matches }: { matches: EntityMatches | null }) {
  if (!matches) return <EmptyState icon={<SearchCode size={24} />} title="No entity trace loaded" body="Generate a brief or refresh a diff to inspect match features." />;
  return <DataTable rows={matches.matches} columns={["project_name", "queue_id", "match_score", "match_method", "is_ambiguous"]} />;
}

function CitationsTab({ brief, sources }: { brief: Brief | null; sources: Source[] }) {
  return (
    <div className="content-stack">
      <section>
        <h2>Brief Citations</h2>
        {brief?.citations?.length ? <DataTable rows={brief.citations} columns={["citation_label", "citation_text", "source_url"]} /> : <p className="muted">Generate a brief to see record-level citations.</p>}
      </section>
      <section>
        <h2>Available Sources</h2>
        <DataTable rows={sources} columns={["source_name", "source_type", "snapshot_count", "source_url"]} />
      </section>
    </div>
  );
}

function EvalsTab({ evalOutput }: { evalOutput: Record<string, unknown> | null }) {
  if (!evalOutput) return <EmptyState icon={<ListChecks size={24} />} title="No eval run loaded" body="Run evals to verify deterministic behavior against fixture cases." />;
  return <JsonBlock value={evalOutput} />;
}

function EmptyState({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="empty-state">
      {icon}
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  if (!rows.length) return <p className="muted">No rows.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${columns.map((column) => String(row[column])).join("|")}-${index}`}>
              {columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "NA";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(3);
  return String(value);
}
