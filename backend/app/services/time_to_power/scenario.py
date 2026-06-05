from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.utils import new_id, stable_json, utcnow


PROCUREMENT_STRATEGIES = {"post_ntp_serial", "at_risk_overlap", "procurement_started", "unknown"}
EQUIPMENT_SCOPE_MODES = {"generated_planning_model", "manual_user_selected", "fixture_demo", "insufficient_data"}


def create_time_to_power_scenario(
    *,
    scenario_name: str = "Fixture Time-to-Power Scenario",
    market: str = "ERCOT",
    jurisdiction: str = "FERC",
    county: str | None = "Reeves",
    region: str | None = None,
    project_type: str = "AI data center load",
    peak_mw: float = 300,
    average_load_factor: float = 0.85,
    interconnection_voltage_kv: float | None = 345,
    target_online_year: int | None = 2029,
    target_online_date: date | str | None = None,
    flexibility_scenario_id: str | None = None,
    selected_tradeoff_id: str | None = None,
    procurement_strategy: str = "post_ntp_serial",
    procurement_start_assumption: str | None = None,
    commissioning_assumption_id: str | None = None,
    equipment_scope_mode: str = "generated_planning_model",
    manual_equipment_scope_json: list[dict[str, Any]] | dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    if procurement_strategy not in PROCUREMENT_STRATEGIES:
        raise ValueError(f"Unsupported procurement_strategy: {procurement_strategy}")
    if equipment_scope_mode not in EQUIPMENT_SCOPE_MODES:
        raise ValueError(f"Unsupported equipment_scope_mode: {equipment_scope_mode}")
    scenario_id = new_id("ttp_scenario")
    created_at = utcnow()
    target_date = _date_value(target_online_date)
    manual_scope = manual_equipment_scope_json or []
    procurement_start = procurement_start_assumption or _default_procurement_start(procurement_strategy)
    scenario = {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "market": market,
        "jurisdiction": jurisdiction,
        "county": county,
        "region": region,
        "project_type": project_type,
        "peak_mw": float(peak_mw),
        "average_load_factor": float(average_load_factor),
        "interconnection_voltage_kv": float(interconnection_voltage_kv) if interconnection_voltage_kv is not None else None,
        "target_online_year": target_online_year,
        "target_online_date": target_date.isoformat() if target_date else None,
        "flexibility_scenario_id": flexibility_scenario_id,
        "selected_tradeoff_id": selected_tradeoff_id,
        "procurement_strategy": procurement_strategy,
        "procurement_start_assumption": procurement_start,
        "commissioning_assumption_id": commissioning_assumption_id,
        "equipment_scope_mode": equipment_scope_mode,
        "manual_equipment_scope_json": manual_scope,
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
    }
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO time_to_power_scenarios
            (scenario_id, scenario_name, market, jurisdiction, county, region, project_type, peak_mw,
             average_load_factor, interconnection_voltage_kv, target_online_year, target_online_date,
             flexibility_scenario_id, selected_tradeoff_id, procurement_strategy, procurement_start_assumption,
             commissioning_assumption_id, equipment_scope_mode, manual_equipment_scope_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                scenario_id,
                scenario_name,
                market,
                jurisdiction,
                county,
                region,
                project_type,
                float(peak_mw),
                float(average_load_factor),
                float(interconnection_voltage_kv) if interconnection_voltage_kv is not None else None,
                target_online_year,
                target_date,
                flexibility_scenario_id,
                selected_tradeoff_id,
                procurement_strategy,
                procurement_start,
                commissioning_assumption_id,
                equipment_scope_mode,
                stable_json(manual_scope),
                created_at,
                created_at,
            ],
        )
    return scenario


def get_time_to_power_scenario(scenario_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT scenario_id, scenario_name, market, jurisdiction, county, region, project_type, peak_mw,
                   average_load_factor, interconnection_voltage_kv, target_online_year, target_online_date,
                   flexibility_scenario_id, selected_tradeoff_id, procurement_strategy, procurement_start_assumption,
                   commissioning_assumption_id, equipment_scope_mode, manual_equipment_scope_json, created_at, updated_at
            FROM time_to_power_scenarios
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()
    if not row:
        return None
    return {
        "scenario_id": row[0],
        "scenario_name": row[1],
        "market": row[2],
        "jurisdiction": row[3],
        "county": row[4],
        "region": row[5],
        "project_type": row[6],
        "peak_mw": row[7],
        "average_load_factor": row[8],
        "interconnection_voltage_kv": row[9],
        "target_online_year": row[10],
        "target_online_date": _iso(row[11]),
        "flexibility_scenario_id": row[12],
        "selected_tradeoff_id": row[13],
        "procurement_strategy": row[14],
        "procurement_start_assumption": row[15],
        "commissioning_assumption_id": row[16],
        "equipment_scope_mode": row[17],
        "manual_equipment_scope_json": _json(row[18]),
        "created_at": _iso(row[19]),
        "updated_at": _iso(row[20]),
    }


def _default_procurement_start(strategy: str) -> str:
    if strategy == "at_risk_overlap":
        return "Procurement may begin before final NTP at user risk; this is not a recommendation."
    if strategy == "procurement_started":
        return "User indicates procurement has already started; no delivery commitment is inferred."
    if strategy == "unknown":
        return "Procurement start is unknown; serial post-NTP is shown as the conservative comparison."
    return "Procurement starts after interconnection approval / NTP."


def _date_value(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value
