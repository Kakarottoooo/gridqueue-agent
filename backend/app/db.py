from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Iterable

import duckdb

from app.config import database_path


_SCHEMA_LOCK = RLock()


TABLES: tuple[str, ...] = (
    "sources",
    "iso_flexibility_rules",
    "flexibility_rule_sources",
    "compute_cost_assumptions",
    "curtailment_scenarios",
    "flexibility_eligibility_results",
    "flexibility_tradeoff_points",
    "flexibility_briefs",
    "snapshots",
    "raw_project_records",
    "normalized_project_records",
    "project_entities",
    "project_entity_links",
    "diff_events",
    "metric_rollups",
    "citations",
)


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(db_path) if db_path is not None else database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_database(db_path: str | Path | None = None) -> None:
    with _SCHEMA_LOCK, connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY,
              source_name TEXT NOT NULL,
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              retrieved_at TIMESTAMP,
              publication_date DATE,
              notes TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS iso_flexibility_rules (
              rule_id TEXT PRIMARY KEY,
              jurisdiction TEXT NOT NULL,
              provision_name TEXT NOT NULL,
              provision_type TEXT NOT NULL,
              eligibility_criteria_json JSON NOT NULL,
              granted_benefit_text TEXT NOT NULL,
              quantified_benefit_json JSON NOT NULL,
              status TEXT NOT NULL,
              effective_date DATE,
              expiration_date DATE,
              source_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              retrieved_at TIMESTAMP NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS flexibility_rule_sources (
              rule_source_id TEXT PRIMARY KEY,
              rule_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              citation_label TEXT NOT NULL,
              citation_text TEXT NOT NULL,
              source_url TEXT NOT NULL,
              retrieved_at TIMESTAMP NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (rule_id) REFERENCES iso_flexibility_rules(rule_id),
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS compute_cost_assumptions (
              assumption_id TEXT PRIMARY KEY,
              assumption_name TEXT NOT NULL,
              version TEXT NOT NULL,
              peak_mw DOUBLE NOT NULL,
              average_load_factor DOUBLE NOT NULL,
              deferrable_workload_fraction DOUBLE NOT NULL,
              latency_sensitive_fraction DOUBLE NOT NULL,
              migratable_fraction DOUBLE NOT NULL,
              gpu_power_kw DOUBLE NOT NULL,
              gpu_hour_value_usd DOUBLE NOT NULL,
              deferral_penalty_per_gpu_hour_usd DOUBLE NOT NULL,
              migration_penalty_per_gpu_hour_usd DOUBLE NOT NULL,
              dropped_work_penalty_per_gpu_hour_usd DOUBLE NOT NULL,
              default_event_duration_hours DOUBLE NOT NULL,
              default_events_per_year INTEGER NOT NULL,
              evidence_anchor_json JSON NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS curtailment_scenarios (
              scenario_id TEXT PRIMARY KEY,
              market TEXT NOT NULL,
              jurisdiction TEXT NOT NULL,
              county TEXT,
              peak_mw DOUBLE NOT NULL,
              average_load_factor DOUBLE NOT NULL,
              commitment_depth_pct DOUBLE NOT NULL,
              event_duration_hours DOUBLE NOT NULL,
              events_per_year INTEGER NOT NULL,
              job_mix_json JSON NOT NULL,
              colocated_generation BOOLEAN NOT NULL,
              dispatchable_or_curtailable BOOLEAN,
              metering_or_control_capability BOOLEAN,
              assumption_id TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (assumption_id) REFERENCES compute_cost_assumptions(assumption_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS flexibility_eligibility_results (
              eligibility_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              rule_id TEXT NOT NULL,
              eligibility_status TEXT NOT NULL,
              confidence TEXT NOT NULL,
              matched_criteria_json JSON NOT NULL,
              missing_criteria_json JSON NOT NULL,
              explanation TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (scenario_id) REFERENCES curtailment_scenarios(scenario_id),
              FOREIGN KEY (rule_id) REFERENCES iso_flexibility_rules(rule_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS flexibility_tradeoff_points (
              tradeoff_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              commitment_depth_pct DOUBLE NOT NULL,
              annual_curtailed_mwh DOUBLE NOT NULL,
              deferred_gpu_hours DOUBLE NOT NULL,
              migrated_gpu_hours DOUBLE NOT NULL,
              dropped_or_unserved_gpu_hours DOUBLE NOT NULL,
              estimated_compute_cost_usd DOUBLE NOT NULL,
              baseline_timeline_days DOUBLE,
              baseline_metric_id TEXT,
              baseline_sample_n INTEGER NOT NULL,
              baseline_fallback_level TEXT NOT NULL,
              baseline_confidence TEXT NOT NULL,
              with_flex_timeline_days DOUBLE,
              estimated_timeline_delta_days DOUBLE,
              benefit_status TEXT NOT NULL,
              net_benefit_score DOUBLE,
              explanation TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (scenario_id) REFERENCES curtailment_scenarios(scenario_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS flexibility_briefs (
              brief_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              selected_tradeoff_id TEXT,
              brief_json JSON NOT NULL,
              citations_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              reproducibility_trace_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (scenario_id) REFERENCES curtailment_scenarios(scenario_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
              snapshot_id TEXT PRIMARY KEY,
              market TEXT NOT NULL,
              source_id TEXT NOT NULL,
              snapshot_date DATE NOT NULL,
              file_hash TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              ingestion_mode TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_project_records (
              raw_record_id TEXT PRIMARY KEY,
              snapshot_id TEXT NOT NULL,
              raw_payload_json JSON NOT NULL,
              row_number INTEGER NOT NULL,
              source_sheet TEXT,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS normalized_project_records (
              record_id TEXT PRIMARY KEY,
              snapshot_id TEXT NOT NULL,
              market TEXT NOT NULL,
              queue_id TEXT,
              project_name TEXT,
              normalized_project_name TEXT,
              interconnecting_entity TEXT,
              county TEXT,
              state TEXT,
              point_of_interconnection TEXT,
              transmission_owner TEXT,
              fuel_type TEXT,
              normalized_fuel_type TEXT NOT NULL,
              capacity_mw DOUBLE,
              status TEXT,
              normalized_status TEXT NOT NULL,
              request_date DATE,
              target_cod DATE,
              actual_cod DATE,
              withdrawn_date DATE,
              interconnection_agreement_date DATE,
              last_updated_date DATE,
              raw_record_id TEXT NOT NULL,
              data_quality_flags_json JSON NOT NULL,
              FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id),
              FOREIGN KEY (raw_record_id) REFERENCES raw_project_records(raw_record_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_entities (
              entity_id TEXT PRIMARY KEY,
              market TEXT NOT NULL,
              canonical_name TEXT,
              canonical_county TEXT,
              canonical_state TEXT,
              canonical_fuel_type TEXT,
              first_seen_snapshot_id TEXT NOT NULL,
              latest_seen_snapshot_id TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_entity_links (
              link_id TEXT PRIMARY KEY,
              entity_id TEXT NOT NULL,
              record_id TEXT NOT NULL,
              snapshot_id TEXT NOT NULL,
              match_score DOUBLE NOT NULL,
              match_method TEXT NOT NULL,
              match_features_json JSON NOT NULL,
              is_ambiguous BOOLEAN NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (entity_id) REFERENCES project_entities(entity_id),
              FOREIGN KEY (record_id) REFERENCES normalized_project_records(record_id),
              FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS diff_events (
              event_id TEXT PRIMARY KEY,
              market TEXT NOT NULL,
              from_snapshot_id TEXT NOT NULL,
              to_snapshot_id TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              severity TEXT NOT NULL,
              confidence DOUBLE NOT NULL,
              before_record_id TEXT,
              after_record_id TEXT,
              changed_fields_json JSON NOT NULL,
              explanation TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_rollups (
              metric_id TEXT PRIMARY KEY,
              market TEXT NOT NULL,
              scope_type TEXT NOT NULL,
              scope_value TEXT NOT NULL,
              fuel_type TEXT,
              sample_n INTEGER NOT NULL,
              active_count INTEGER NOT NULL,
              active_mw DOUBLE NOT NULL,
              completed_count INTEGER NOT NULL,
              withdrawn_count INTEGER NOT NULL,
              completion_rate DOUBLE,
              withdrawal_rate DOUBLE,
              median_duration_days DOUBLE,
              p75_duration_days DOUBLE,
              confidence TEXT NOT NULL,
              fallback_level TEXT NOT NULL,
              source_snapshot_id TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS citations (
              citation_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              snapshot_id TEXT,
              record_id TEXT,
              citation_label TEXT NOT NULL,
              citation_text TEXT NOT NULL,
              source_url TEXT NOT NULL,
              created_at TIMESTAMP NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
            """
        )


def reset_database(db_path: str | Path | None = None) -> None:
    with _SCHEMA_LOCK:
        with connect(db_path) as con:
            for table in reversed(TABLES):
                con.execute(f"DROP TABLE IF EXISTS {table}")
        init_database(db_path)


def table_counts(db_path: str | Path | None = None, tables: Iterable[str] = TABLES) -> dict[str, int]:
    init_database(db_path)
    counts: dict[str, int] = {}
    with connect(db_path) as con:
        for table in tables:
            counts[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts
