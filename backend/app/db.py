from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Iterable

import duckdb

from app.config import database_path


_SCHEMA_LOCK = RLock()


TABLES: tuple[str, ...] = (
    "sources",
    "watch_sources",
    "source_snapshots",
    "change_events",
    "digests",
    "lead_time_sources",
    "equipment_lead_times",
    "project_equipment_scope_models",
    "procurement_timeline_estimates",
    "commissioning_assumptions",
    "time_to_power_scenarios",
    "time_to_power_components",
    "procurement_critical_path_results",
    "time_to_power_estimates",
    "time_to_power_briefs",
    "iso_flexibility_rules",
    "flexibility_rule_sources",
    "compute_cost_assumptions",
    "curtailment_scenarios",
    "flexibility_eligibility_results",
    "flexibility_tradeoff_points",
    "flexibility_briefs",
    "real_lbnl_workbooks",
    "real_lbnl_project_records",
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
            CREATE TABLE IF NOT EXISTS watch_sources (
              watch_source_id TEXT PRIMARY KEY,
              source_name TEXT NOT NULL,
              source_type TEXT NOT NULL,
              jurisdiction TEXT NOT NULL,
              source_url TEXT NOT NULL,
              parser_type TEXT NOT NULL,
              watch_frequency TEXT NOT NULL,
              is_active BOOLEAN NOT NULL,
              last_snapshot_id TEXT,
              last_content_hash TEXT,
              last_checked_at TIMESTAMP,
              notes TEXT,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS source_snapshots (
              source_snapshot_id TEXT PRIMARY KEY,
              watch_source_id TEXT NOT NULL,
              retrieved_at TIMESTAMP NOT NULL,
              publication_date DATE,
              content_hash TEXT NOT NULL,
              content_text TEXT NOT NULL,
              raw_payload_json JSON NOT NULL,
              parse_status TEXT NOT NULL,
              parse_error TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS change_events (
              change_event_id TEXT PRIMARY KEY,
              event_domain TEXT NOT NULL,
              event_type TEXT NOT NULL,
              jurisdiction TEXT,
              market TEXT,
              entity_or_provision TEXT,
              entity_id TEXT,
              rule_id TEXT,
              source_snapshot_id TEXT,
              from_snapshot_id TEXT,
              to_snapshot_id TEXT,
              source_url TEXT,
              before_json JSON NOT NULL,
              after_json JSON NOT NULL,
              materiality_score DOUBLE NOT NULL,
              confidence DOUBLE NOT NULL,
              is_ambiguous BOOLEAN NOT NULL,
              is_hard_alert BOOLEAN NOT NULL,
              explanation TEXT NOT NULL,
              citation_ids_json JSON NOT NULL,
              detected_at TIMESTAMP NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS digests (
              digest_id TEXT PRIMARY KEY,
              digest_type TEXT NOT NULL,
              period_start DATE NOT NULL,
              period_end DATE NOT NULL,
              title TEXT NOT NULL,
              markdown_path TEXT NOT NULL,
              digest_json JSON NOT NULL,
              top_event_ids_json JSON NOT NULL,
              generated_at TIMESTAMP NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_time_sources (
              lead_time_source_id TEXT PRIMARY KEY,
              source_name TEXT NOT NULL,
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              publication_date DATE,
              retrieved_at TIMESTAMP NOT NULL,
              content_hash TEXT NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_lead_times (
              lead_time_id TEXT PRIMARY KEY,
              equipment_class TEXT NOT NULL,
              voltage_or_rating_band TEXT NOT NULL,
              lead_time_low_months DOUBLE NOT NULL,
              lead_time_high_months DOUBLE NOT NULL,
              as_of_date DATE NOT NULL,
              source_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              confidence TEXT NOT NULL,
              is_stale BOOLEAN NOT NULL,
              stale_threshold_months INTEGER NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_equipment_scope_models (
              scope_model_id TEXT PRIMARY KEY,
              project_type TEXT NOT NULL,
              size_mw_low DOUBLE NOT NULL,
              size_mw_high DOUBLE NOT NULL,
              interconnection_voltage_low_kv DOUBLE,
              interconnection_voltage_high_kv DOUBLE,
              likely_equipment_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              confidence TEXT NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS procurement_timeline_estimates (
              procurement_timeline_id TEXT PRIMARY KEY,
              project_type TEXT NOT NULL,
              size_mw DOUBLE NOT NULL,
              interconnection_voltage_kv DOUBLE,
              scope_model_id TEXT,
              lead_time_rows_json JSON NOT NULL,
              critical_path_equipment_class TEXT NOT NULL,
              timeline_low_months DOUBLE NOT NULL,
              timeline_high_months DOUBLE NOT NULL,
              confidence TEXT NOT NULL,
              caveats_json JSON NOT NULL,
              citations_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS commissioning_assumptions (
              commissioning_assumption_id TEXT PRIMARY KEY,
              assumption_name TEXT NOT NULL,
              version TEXT NOT NULL,
              default_commissioning_low_days DOUBLE NOT NULL,
              default_commissioning_high_days DOUBLE NOT NULL,
              energization_buffer_low_days DOUBLE NOT NULL,
              energization_buffer_high_days DOUBLE NOT NULL,
              source_type TEXT NOT NULL,
              source_url TEXT NOT NULL,
              as_of_date DATE NOT NULL,
              confidence TEXT NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS time_to_power_scenarios (
              scenario_id TEXT PRIMARY KEY,
              scenario_name TEXT NOT NULL,
              market TEXT NOT NULL,
              jurisdiction TEXT NOT NULL,
              county TEXT,
              region TEXT,
              project_type TEXT NOT NULL,
              peak_mw DOUBLE NOT NULL,
              average_load_factor DOUBLE NOT NULL,
              interconnection_voltage_kv DOUBLE,
              target_online_year INTEGER,
              target_online_date DATE,
              flexibility_scenario_id TEXT,
              selected_tradeoff_id TEXT,
              procurement_strategy TEXT NOT NULL,
              procurement_start_assumption TEXT NOT NULL,
              commissioning_assumption_id TEXT,
              equipment_scope_mode TEXT NOT NULL,
              manual_equipment_scope_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS time_to_power_components (
              component_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              component_type TEXT NOT NULL,
              component_name TEXT NOT NULL,
              low_days DOUBLE,
              high_days DOUBLE,
              confidence TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_id TEXT,
              source_url TEXT,
              citation_ids_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              caveats_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS procurement_critical_path_results (
              critical_path_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              equipment_scope_json JSON NOT NULL,
              lead_time_rows_json JSON NOT NULL,
              binding_equipment_class TEXT,
              binding_lead_time_low_months DOUBLE,
              binding_lead_time_high_months DOUBLE,
              procurement_low_days DOUBLE,
              procurement_high_days DOUBLE,
              confidence TEXT NOT NULL,
              stale_flag BOOLEAN NOT NULL,
              conflict_flag BOOLEAN NOT NULL,
              unsupported_flag BOOLEAN NOT NULL,
              citations_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              caveats_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS time_to_power_estimates (
              estimate_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              baseline_metric_id TEXT,
              flexibility_tradeoff_id TEXT,
              critical_path_id TEXT,
              commissioning_assumption_id TEXT,
              no_flex_serial_low_days DOUBLE,
              no_flex_serial_high_days DOUBLE,
              flex_serial_low_days DOUBLE,
              flex_serial_high_days DOUBLE,
              no_flex_overlap_low_days DOUBLE,
              no_flex_overlap_high_days DOUBLE,
              flex_overlap_low_days DOUBLE,
              flex_overlap_high_days DOUBLE,
              selected_case TEXT NOT NULL,
              binding_constraint TEXT NOT NULL,
              confidence TEXT NOT NULL,
              status TEXT NOT NULL,
              status_explanation TEXT NOT NULL,
              citations_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              reproducibility_trace_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS time_to_power_briefs (
              brief_id TEXT PRIMARY KEY,
              scenario_id TEXT NOT NULL,
              estimate_id TEXT NOT NULL,
              title TEXT NOT NULL,
              brief_json JSON NOT NULL,
              markdown_path TEXT NOT NULL,
              citations_json JSON NOT NULL,
              assumptions_json JSON NOT NULL,
              caveats_json JSON NOT NULL,
              reproducibility_trace_json JSON NOT NULL,
              generated_at TIMESTAMP NOT NULL,
              created_at TIMESTAMP NOT NULL
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
            CREATE TABLE IF NOT EXISTS real_lbnl_workbooks (
              workbook_id TEXT PRIMARY KEY,
              source_name TEXT NOT NULL,
              source_url TEXT NOT NULL,
              local_path TEXT NOT NULL,
              file_hash_sha256 TEXT NOT NULL,
              file_size_bytes BIGINT NOT NULL,
              publication_date TEXT,
              retrieved_at TIMESTAMP,
              user_provided_at TIMESTAMP,
              project_sheet_name TEXT NOT NULL,
              row_count_raw INTEGER NOT NULL,
              sheet_names_json JSON NOT NULL,
              parser_version TEXT NOT NULL,
              parse_status TEXT NOT NULL,
              parse_errors_json JSON NOT NULL,
              notes TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS real_lbnl_project_records (
              lbnl_record_id TEXT PRIMARY KEY,
              workbook_id TEXT NOT NULL,
              file_hash_sha256 TEXT NOT NULL,
              source_url TEXT NOT NULL,
              sheet_name TEXT NOT NULL,
              row_number INTEGER NOT NULL,
              q_id TEXT,
              q_status TEXT,
              q_date DATE,
              prop_date DATE,
              on_date DATE,
              wd_date DATE,
              ia_date DATE,
              ia_phase_raw TEXT,
              ia_phase_clean TEXT,
              county TEXT,
              state TEXT,
              region TEXT,
              project_name TEXT,
              utility TEXT,
              entity TEXT,
              developer TEXT,
              service TEXT,
              project_type TEXT,
              type_1 TEXT,
              type_2 TEXT,
              type_3 TEXT,
              type_clean TEXT,
              mw_1 DOUBLE,
              mw_2 DOUBLE,
              mw_3 DOUBLE,
              q_year INTEGER,
              prop_year INTEGER,
              raw_payload_json JSON NOT NULL,
              created_at TIMESTAMP NOT NULL
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
