from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility.seed import DEFAULT_ASSUMPTION_ID, seed_flexibility_rules
from app.services.utils import new_id, stable_json, utcnow


ASSUMPTION_FIELDS = (
    "peak_mw",
    "average_load_factor",
    "deferrable_workload_fraction",
    "latency_sensitive_fraction",
    "migratable_fraction",
    "gpu_power_kw",
    "gpu_hour_value_usd",
    "deferral_penalty_per_gpu_hour_usd",
    "migration_penalty_per_gpu_hour_usd",
    "dropped_work_penalty_per_gpu_hour_usd",
    "default_event_duration_hours",
    "default_events_per_year",
)


def get_compute_assumption(
    assumption_id: str = DEFAULT_ASSUMPTION_ID,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    seed_flexibility_rules(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT assumption_id, assumption_name, version, peak_mw, average_load_factor,
                   deferrable_workload_fraction, latency_sensitive_fraction, migratable_fraction,
                   gpu_power_kw, gpu_hour_value_usd, deferral_penalty_per_gpu_hour_usd,
                   migration_penalty_per_gpu_hour_usd, dropped_work_penalty_per_gpu_hour_usd,
                   default_event_duration_hours, default_events_per_year, evidence_anchor_json, notes, created_at
            FROM compute_cost_assumptions
            WHERE assumption_id = ?
            """,
            [assumption_id],
        ).fetchone()
    if not row:
        raise ValueError(f"Unknown compute-cost assumption_id: {assumption_id}")
    return _assumption_from_row(row)


def ensure_compute_assumption(
    *,
    assumption_id: str | None = None,
    assumption_name: str,
    peak_mw: float,
    average_load_factor: float,
    deferrable_workload_fraction: float,
    latency_sensitive_fraction: float,
    migratable_fraction: float,
    gpu_power_kw: float,
    gpu_hour_value_usd: float,
    deferral_penalty_per_gpu_hour_usd: float,
    migration_penalty_per_gpu_hour_usd: float,
    dropped_work_penalty_per_gpu_hour_usd: float,
    default_event_duration_hours: float,
    default_events_per_year: int,
    evidence_anchor_json: dict[str, Any],
    notes: str,
    version: str = "request",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    _validate_fractions(deferrable_workload_fraction, latency_sensitive_fraction, migratable_fraction)
    if gpu_power_kw <= 0:
        raise ValueError("gpu_power_kw must be greater than zero.")
    final_id = assumption_id or new_id("assumption")
    assumption = {
        "assumption_id": final_id,
        "assumption_name": assumption_name,
        "version": version,
        "peak_mw": peak_mw,
        "average_load_factor": average_load_factor,
        "deferrable_workload_fraction": deferrable_workload_fraction,
        "latency_sensitive_fraction": latency_sensitive_fraction,
        "migratable_fraction": migratable_fraction,
        "gpu_power_kw": gpu_power_kw,
        "gpu_hour_value_usd": gpu_hour_value_usd,
        "deferral_penalty_per_gpu_hour_usd": deferral_penalty_per_gpu_hour_usd,
        "migration_penalty_per_gpu_hour_usd": migration_penalty_per_gpu_hour_usd,
        "dropped_work_penalty_per_gpu_hour_usd": dropped_work_penalty_per_gpu_hour_usd,
        "default_event_duration_hours": default_event_duration_hours,
        "default_events_per_year": default_events_per_year,
        "evidence_anchor_json": evidence_anchor_json,
        "notes": notes,
    }
    with connect(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO compute_cost_assumptions
            (assumption_id, assumption_name, version, peak_mw, average_load_factor,
             deferrable_workload_fraction, latency_sensitive_fraction, migratable_fraction,
             gpu_power_kw, gpu_hour_value_usd, deferral_penalty_per_gpu_hour_usd,
             migration_penalty_per_gpu_hour_usd, dropped_work_penalty_per_gpu_hour_usd,
             default_event_duration_hours, default_events_per_year, evidence_anchor_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                final_id,
                assumption_name,
                version,
                peak_mw,
                average_load_factor,
                deferrable_workload_fraction,
                latency_sensitive_fraction,
                migratable_fraction,
                gpu_power_kw,
                gpu_hour_value_usd,
                deferral_penalty_per_gpu_hour_usd,
                migration_penalty_per_gpu_hour_usd,
                dropped_work_penalty_per_gpu_hour_usd,
                default_event_duration_hours,
                default_events_per_year,
                stable_json(evidence_anchor_json),
                notes,
                utcnow(),
            ],
        )
    return {**assumption, "created_at": utcnow().isoformat()}


def calculate_compute_cost(
    *,
    peak_mw: float,
    commitment_depth_pct: float,
    event_duration_hours: float,
    events_per_year: int,
    assumption: dict[str, Any],
) -> dict[str, Any]:
    missing = [field for field in ASSUMPTION_FIELDS if field not in assumption]
    if missing:
        raise ValueError(f"Compute-cost assumptions are missing required fields: {', '.join(missing)}")
    _validate_fractions(
        float(assumption["deferrable_workload_fraction"]),
        float(assumption["latency_sensitive_fraction"]),
        float(assumption["migratable_fraction"]),
    )
    gpu_power_kw = float(assumption["gpu_power_kw"])
    if gpu_power_kw <= 0:
        raise ValueError("gpu_power_kw must be greater than zero.")

    annual_curtailed_mwh = peak_mw * commitment_depth_pct / 100.0 * event_duration_hours * events_per_year
    equivalent_gpu_hours = annual_curtailed_mwh * 1000.0 / gpu_power_kw
    deferred_gpu_hours = equivalent_gpu_hours * float(assumption["deferrable_workload_fraction"])
    migrated_gpu_hours = equivalent_gpu_hours * float(assumption["migratable_fraction"])
    dropped_or_unserved_gpu_hours = max(0.0, equivalent_gpu_hours - deferred_gpu_hours - migrated_gpu_hours)
    estimated_compute_cost_usd = (
        deferred_gpu_hours * float(assumption["deferral_penalty_per_gpu_hour_usd"])
        + migrated_gpu_hours * float(assumption["migration_penalty_per_gpu_hour_usd"])
        + dropped_or_unserved_gpu_hours * float(assumption["dropped_work_penalty_per_gpu_hour_usd"])
    )
    extrapolation_flag = commitment_depth_pct > 25 or event_duration_hours > 3
    return {
        "annual_curtailed_mwh": round(annual_curtailed_mwh, 4),
        "equivalent_gpu_hours": round(equivalent_gpu_hours, 4),
        "deferred_gpu_hours": round(deferred_gpu_hours, 4),
        "migrated_gpu_hours": round(migrated_gpu_hours, 4),
        "dropped_or_unserved_gpu_hours": round(dropped_or_unserved_gpu_hours, 4),
        "estimated_compute_cost_usd": round(estimated_compute_cost_usd, 2),
        "extrapolation_flag": extrapolation_flag,
        "extrapolation_reason": (
            "Scenario exceeds the public field-demo anchor of 25 percent curtailment or 3 hours."
            if extrapolation_flag
            else "Within the public field-demo anchor of 25 percent curtailment for 3 hours."
        ),
        "assumptions_json": {field: assumption[field] for field in ASSUMPTION_FIELDS},
        "evidence_anchor_json": assumption.get("evidence_anchor_json", {}),
    }


def _validate_fractions(deferrable: float, latency_sensitive: float, migratable: float) -> None:
    if any(value < 0 or value > 1 for value in (deferrable, latency_sensitive, migratable)):
        raise ValueError("Workload fractions must be between 0 and 1.")
    total = deferrable + latency_sensitive + migratable
    if total > 1.000001:
        raise ValueError("Workload fractions must sum to 1.0 or less.")


def _assumption_from_row(row: Any) -> dict[str, Any]:
    return {
        "assumption_id": row[0],
        "assumption_name": row[1],
        "version": row[2],
        "peak_mw": row[3],
        "average_load_factor": row[4],
        "deferrable_workload_fraction": row[5],
        "latency_sensitive_fraction": row[6],
        "migratable_fraction": row[7],
        "gpu_power_kw": row[8],
        "gpu_hour_value_usd": row[9],
        "deferral_penalty_per_gpu_hour_usd": row[10],
        "migration_penalty_per_gpu_hour_usd": row[11],
        "dropped_work_penalty_per_gpu_hour_usd": row[12],
        "default_event_duration_hours": row[13],
        "default_events_per_year": row[14],
        "evidence_anchor_json": json.loads(row[15]) if isinstance(row[15], str) else row[15],
        "notes": row[16],
        "created_at": row[17].isoformat() if hasattr(row[17], "isoformat") else row[17],
    }
