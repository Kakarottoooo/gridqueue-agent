"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, BarChart3, BookOpenCheck, Database, FileText, GitCompare, ListChecks, RefreshCw, SearchCode } from "lucide-react";
import { JsonBlock } from "@/components/JsonBlock";
import { apiGet, apiPost, type Brief, type BriefRequest, type DiffResult, type EntityMatches, type Snapshot, type Source } from "@/lib/api";

type TabKey = "brief" | "diff" | "metrics" | "matching" | "citations" | "evals";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "brief", label: "Brief" },
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

export default function Home() {
  const [form, setForm] = useState<BriefRequest>(defaultForm);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [fromSnapshot, setFromSnapshot] = useState("");
  const [toSnapshot, setToSnapshot] = useState("");
  const [activeTab, setActiveTab] = useState<TabKey>("brief");
  const [brief, setBrief] = useState<Brief | null>(null);
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
