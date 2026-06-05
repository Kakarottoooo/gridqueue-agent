from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility.seed import seed_flexibility_rules
from app.services.ingestion import run_fixture_pipeline
from app.services.procurement.lead_time_kb import seed_lead_time_kb
from app.services.utils import stable_json, utcnow


FIXTURE_LEAD_SOURCE_ID = "lead_src_ttp_fixture_demo"
FIXTURE_LEAD_SOURCE_URL = "synthetic://gridqueue-agent/fixtures/time-to-power-lead-times"
COMMISSIONING_ASSUMPTION_ID = "comm_ttp_fixture_v1"
COMMISSIONING_SOURCE_URL = "synthetic://gridqueue-agent/fixtures/time-to-power-commissioning"


def seed_time_to_power_fixtures(*, reset_core: bool = False, db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    if reset_core or not _has_snapshots(db_path):
        run_fixture_pipeline(reset=True, db_path=db_path)
    seed_flexibility_rules(db_path)
    seed_lead_time_kb(db_path)
    with connect(db_path) as con:
        _insert_fixture_lead_source(con)
        for row in _fixture_lead_time_rows():
            _upsert_lead_time_row(con, row)
        _upsert_commissioning_assumption(con)
        counts = {
            "equipment_lead_times": int(con.execute("SELECT COUNT(*) FROM equipment_lead_times").fetchone()[0]),
            "commissioning_assumptions": int(con.execute("SELECT COUNT(*) FROM commissioning_assumptions").fetchone()[0]),
        }
    return {"status": "seeded", "fixture": "time_to_power", **counts}


def _has_snapshots(db_path: str | Path | None) -> bool:
    with connect(db_path) as con:
        return bool(con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])


def ensure_commissioning_assumption(
    *,
    commissioning_low_days: float | None = None,
    commissioning_high_days: float | None = None,
    energization_buffer_low_days: float | None = None,
    energization_buffer_high_days: float | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    seed_time_to_power_fixtures(reset_core=False, db_path=db_path)
    with connect(db_path) as con:
        if any(value is not None for value in [commissioning_low_days, commissioning_high_days, energization_buffer_low_days, energization_buffer_high_days]):
            assumption = {
                "commissioning_assumption_id": f"comm_request_{hashlib.sha256(stable_json([commissioning_low_days, commissioning_high_days, energization_buffer_low_days, energization_buffer_high_days]).encode('utf-8')).hexdigest()[:12]}",
                "assumption_name": "API request commissioning assumption",
                "version": "1",
                "default_commissioning_low_days": float(commissioning_low_days if commissioning_low_days is not None else 30),
                "default_commissioning_high_days": float(commissioning_high_days if commissioning_high_days is not None else 60),
                "energization_buffer_low_days": float(energization_buffer_low_days if energization_buffer_low_days is not None else 7),
                "energization_buffer_high_days": float(energization_buffer_high_days if energization_buffer_high_days is not None else 14),
                "source_type": "user_assumption",
                "source_url": "user-input://time-to-power/commissioning-assumption",
                "as_of_date": "2026-06-05",
                "confidence": "low",
                "notes": "User-supplied planning assumption; not a commissioning plan.",
            }
            _upsert_commissioning_assumption(con, assumption)
        row = con.execute(
            """
            SELECT commissioning_assumption_id, assumption_name, version, default_commissioning_low_days,
                   default_commissioning_high_days, energization_buffer_low_days, energization_buffer_high_days,
                   source_type, source_url, as_of_date, confidence, notes, created_at
            FROM commissioning_assumptions
            WHERE commissioning_assumption_id = ?
            """,
            [assumption["commissioning_assumption_id"] if "assumption" in locals() else COMMISSIONING_ASSUMPTION_ID],
        ).fetchone()
    return {
        "commissioning_assumption_id": row[0],
        "assumption_name": row[1],
        "version": row[2],
        "default_commissioning_low_days": row[3],
        "default_commissioning_high_days": row[4],
        "energization_buffer_low_days": row[5],
        "energization_buffer_high_days": row[6],
        "source_type": row[7],
        "source_url": row[8],
        "as_of_date": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
        "confidence": row[10],
        "notes": row[11],
        "created_at": row[12].isoformat() if hasattr(row[12], "isoformat") else row[12],
    }


def _insert_fixture_lead_source(con: Any) -> None:
    exists = con.execute("SELECT COUNT(*) FROM lead_time_sources WHERE lead_time_source_id = ?", [FIXTURE_LEAD_SOURCE_ID]).fetchone()[0]
    if exists:
        return
    con.execute(
        """
        INSERT INTO lead_time_sources
        (lead_time_source_id, source_name, source_url, source_type, publication_date,
         retrieved_at, content_hash, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            FIXTURE_LEAD_SOURCE_ID,
            "GridQueue Time-to-Power synthetic lead-time fixture",
            FIXTURE_LEAD_SOURCE_URL,
            "synthetic_fixture",
            "2026-05-01",
            utcnow(),
            hashlib.sha256(FIXTURE_LEAD_SOURCE_URL.encode("utf-8")).hexdigest(),
            "Synthetic rows for deterministic Time-to-Power critical-path tests. Not market facts.",
            utcnow(),
        ],
    )


def _fixture_lead_time_rows() -> list[dict[str, Any]]:
    return [
        {
            "lead_time_id": "lead_ttp_hv_gis_fixture_18_30",
            "equipment_class": "HV Switchgear / GIS",
            "voltage_or_rating_band": "Transmission-class 230-500 kV",
            "lead_time_low_months": 18.0,
            "lead_time_high_months": 30.0,
            "as_of_date": "2026-05-01",
            "confidence": "low",
            "notes": "Synthetic fixture range for deterministic critical-path comparison.",
        },
        {
            "lead_time_id": "lead_ttp_hv_gis_fixture_conflict_28_42",
            "equipment_class": "HV Switchgear / GIS",
            "voltage_or_rating_band": "Transmission-class 230-500 kV",
            "lead_time_low_months": 28.0,
            "lead_time_high_months": 42.0,
            "as_of_date": "2024-01-15",
            "confidence": "low",
            "notes": "Synthetic stale/conflicting fixture row. Not a market fact.",
        },
        {
            "lead_time_id": "lead_ttp_mv_switchgear_fixture_8_14",
            "equipment_class": "Medium-Voltage Switchgear",
            "voltage_or_rating_band": "Campus and collector medium-voltage",
            "lead_time_low_months": 8.0,
            "lead_time_high_months": 14.0,
            "as_of_date": "2026-05-01",
            "confidence": "low",
            "notes": "Synthetic fixture row. Not a supplier quote.",
        },
        {
            "lead_time_id": "lead_ttp_gsu_fixture_24_40",
            "equipment_class": "GSU Transformer",
            "voltage_or_rating_band": "Transmission-class step-up transformer",
            "lead_time_low_months": 24.0,
            "lead_time_high_months": 40.0,
            "as_of_date": "2026-05-01",
            "confidence": "low",
            "notes": "Synthetic fixture row for storage/solar-plus-storage scopes.",
        },
    ]


def _upsert_lead_time_row(con: Any, row: dict[str, Any]) -> None:
    exists = con.execute("SELECT COUNT(*) FROM equipment_lead_times WHERE lead_time_id = ?", [row["lead_time_id"]]).fetchone()[0]
    if exists:
        return
    con.execute(
        """
        INSERT INTO equipment_lead_times
        (lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
         lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
         is_stale, stale_threshold_months, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row["lead_time_id"],
            row["equipment_class"],
            row["voltage_or_rating_band"],
            row["lead_time_low_months"],
            row["lead_time_high_months"],
            row["as_of_date"],
            FIXTURE_LEAD_SOURCE_ID,
            FIXTURE_LEAD_SOURCE_URL,
            "synthetic_fixture",
            row["confidence"],
            False,
            18,
            row["notes"],
            utcnow(),
            utcnow(),
        ],
    )


def _upsert_commissioning_assumption(con: Any, assumption: dict[str, Any] | None = None) -> None:
    row = assumption or {
        "commissioning_assumption_id": COMMISSIONING_ASSUMPTION_ID,
        "assumption_name": "Fixture commissioning and energization buffer",
        "version": "1",
        "default_commissioning_low_days": 30.0,
        "default_commissioning_high_days": 60.0,
        "energization_buffer_low_days": 7.0,
        "energization_buffer_high_days": 14.0,
        "source_type": "synthetic_fixture",
        "source_url": COMMISSIONING_SOURCE_URL,
        "as_of_date": "2026-05-01",
        "confidence": "low",
        "notes": "Planning assumption only; not a commissioning plan or energization guarantee.",
    }
    exists = con.execute(
        "SELECT COUNT(*) FROM commissioning_assumptions WHERE commissioning_assumption_id = ?",
        [row["commissioning_assumption_id"]],
    ).fetchone()[0]
    if exists:
        return
    con.execute(
        """
        INSERT INTO commissioning_assumptions
        (commissioning_assumption_id, assumption_name, version, default_commissioning_low_days,
         default_commissioning_high_days, energization_buffer_low_days, energization_buffer_high_days,
         source_type, source_url, as_of_date, confidence, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row["commissioning_assumption_id"],
            row["assumption_name"],
            row["version"],
            row["default_commissioning_low_days"],
            row["default_commissioning_high_days"],
            row["energization_buffer_low_days"],
            row["energization_buffer_high_days"],
            row["source_type"],
            row["source_url"],
            row["as_of_date"],
            row["confidence"],
            row["notes"],
            utcnow(),
        ],
    )
