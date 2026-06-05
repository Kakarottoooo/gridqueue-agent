from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.utils import new_id, stable_json, utcnow


def store_scenario(
    *,
    market: str,
    jurisdiction: str,
    county: str | None,
    peak_mw: float,
    average_load_factor: float,
    commitment_depth_pct: float,
    event_duration_hours: float,
    events_per_year: int,
    job_mix_json: dict[str, Any],
    colocated_generation: bool,
    dispatchable_or_curtailable: bool | None,
    metering_or_control_capability: bool | None,
    assumption_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    scenario = {
        "scenario_id": new_id("scenario"),
        "market": market,
        "jurisdiction": jurisdiction,
        "county": county,
        "peak_mw": peak_mw,
        "average_load_factor": average_load_factor,
        "commitment_depth_pct": commitment_depth_pct,
        "event_duration_hours": event_duration_hours,
        "events_per_year": events_per_year,
        "job_mix_json": job_mix_json,
        "colocated_generation": colocated_generation,
        "dispatchable_or_curtailable": dispatchable_or_curtailable,
        "metering_or_control_capability": metering_or_control_capability,
        "assumption_id": assumption_id,
        "created_at": utcnow().isoformat(),
    }
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO curtailment_scenarios
            (scenario_id, market, jurisdiction, county, peak_mw, average_load_factor,
             commitment_depth_pct, event_duration_hours, events_per_year, job_mix_json,
             colocated_generation, dispatchable_or_curtailable, metering_or_control_capability,
             assumption_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                scenario["scenario_id"],
                market,
                jurisdiction,
                county,
                peak_mw,
                average_load_factor,
                commitment_depth_pct,
                event_duration_hours,
                events_per_year,
                stable_json(job_mix_json),
                colocated_generation,
                dispatchable_or_curtailable,
                metering_or_control_capability,
                assumption_id,
                utcnow(),
            ],
        )
    return scenario
