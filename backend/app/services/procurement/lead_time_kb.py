from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.utils import utcnow


DOE_LPT_SOURCE_ID = "lead_src_doe_lpt_resilience_2024"
DOE_LPT_SOURCE_URL = (
    "https://www.energy.gov/sites/default/files/2024-10/EXEC-2022-001242%20-%20Large%20Power%20"
    "Transformer%20Resilience%20Report%20signed%20by%20Secretary%20Granholm%20on%207-10-24.pdf"
)
LEAD_TIME_CAVEAT = (
    "Planning proxy only: this is not a procurement quote, OEM commitment, price, engineering design, or guaranteed "
    "delivery timeline."
)


def seed_lead_time_kb(db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        _insert_source(con)
        _insert_lpt_row(con)
        source_count = con.execute("SELECT COUNT(*) FROM lead_time_sources").fetchone()[0]
        lead_time_count = con.execute("SELECT COUNT(*) FROM equipment_lead_times").fetchone()[0]
    return {"status": "seeded", "source_count": int(source_count), "lead_time_count": int(lead_time_count)}


def list_lead_times(
    *,
    equipment_class: str | None = None,
    db_path: str | Path | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    init_database(db_path)
    filters = []
    params: list[Any] = []
    if equipment_class:
        filters.append("equipment_class = ?")
        params.append(equipment_class)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            SELECT lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
                   lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
                   is_stale, stale_threshold_months, notes, created_at, updated_at
            FROM equipment_lead_times
            {where}
            ORDER BY equipment_class, voltage_or_rating_band, source_id
            """,
            params,
        ).fetchall()
    current_date = today or date.today()
    results = [_row_to_lead_time(row, current_date) for row in rows]
    conflicts = _conflict_flags(results)
    for result in results:
        result["has_conflict"] = conflicts.get((result["equipment_class"], result["voltage_or_rating_band"]), False)
        result["caveats"] = [LEAD_TIME_CAVEAT]
    return results


def _insert_source(con: Any) -> None:
    exists = con.execute(
        "SELECT COUNT(*) FROM lead_time_sources WHERE lead_time_source_id = ?",
        [DOE_LPT_SOURCE_ID],
    ).fetchone()[0]
    if exists:
        return
    notes = (
        "DOE July 2024 Large Power Transformer Resilience Report. Seeded as primary public-source metadata for a "
        "range-based Large Power Transformer lead-time demo."
    )
    con.execute(
        """
        INSERT INTO lead_time_sources
        (lead_time_source_id, source_name, source_url, source_type, publication_date,
         retrieved_at, content_hash, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            DOE_LPT_SOURCE_ID,
            "DOE Large Power Transformer Resilience Report",
            DOE_LPT_SOURCE_URL,
            "government_report",
            "2024-07-10",
            utcnow(),
            hashlib.sha256(f"{DOE_LPT_SOURCE_ID}:{DOE_LPT_SOURCE_URL}:36-60".encode("utf-8")).hexdigest(),
            notes,
            utcnow(),
        ],
    )


def _insert_lpt_row(con: Any) -> None:
    lead_time_id = "lead_lpt_doe_2024_36_60_months"
    exists = con.execute(
        "SELECT COUNT(*) FROM equipment_lead_times WHERE lead_time_id = ?",
        [lead_time_id],
    ).fetchone()[0]
    if exists:
        return
    as_of_date = date(2024, 7, 10)
    stale_threshold_months = 18
    con.execute(
        """
        INSERT INTO equipment_lead_times
        (lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
         lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
         is_stale, stale_threshold_months, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            lead_time_id,
            "Large Power Transformer",
            "Transmission-class / high-voltage recovery transformer",
            36.0,
            60.0,
            as_of_date,
            DOE_LPT_SOURCE_ID,
            DOE_LPT_SOURCE_URL,
            "government_report",
            "medium",
            _is_stale(as_of_date, stale_threshold_months, date.today()),
            stale_threshold_months,
            (
                "DOE July 2024 report says 36-month LPT lead times are commonly quoted and maximum lead times "
                "reach as much as 60 months. Stored as a range, not a quote or point estimate."
            ),
            utcnow(),
            utcnow(),
        ],
    )


def _row_to_lead_time(row: tuple[Any, ...], today: date) -> dict[str, Any]:
    as_of = row[5]
    if not isinstance(as_of, date):
        as_of = date.fromisoformat(str(as_of))
    is_stale = _is_stale(as_of, int(row[11]), today)
    return {
        "lead_time_id": row[0],
        "equipment_class": row[1],
        "voltage_or_rating_band": row[2],
        "lead_time_low_months": row[3],
        "lead_time_high_months": row[4],
        "as_of_date": as_of.isoformat(),
        "source_id": row[6],
        "source_url": row[7],
        "source_type": row[8],
        "confidence": row[9],
        "is_stale": is_stale,
        "stale_threshold_months": row[11],
        "notes": row[12],
        "created_at": row[13].isoformat() if hasattr(row[13], "isoformat") else row[13],
        "updated_at": row[14].isoformat() if hasattr(row[14], "isoformat") else row[14],
    }


def _is_stale(as_of: date, threshold_months: int, today: date) -> bool:
    age_months = (today.year - as_of.year) * 12 + (today.month - as_of.month)
    return age_months >= threshold_months


def _conflict_flags(rows: list[dict[str, Any]]) -> dict[tuple[str, str], bool]:
    grouped: dict[tuple[str, str], set[tuple[float, float]]] = {}
    for row in rows:
        key = (row["equipment_class"], row["voltage_or_rating_band"])
        grouped.setdefault(key, set()).add((float(row["lead_time_low_months"]), float(row["lead_time_high_months"])))
    return {key: len(ranges) > 1 for key, ranges in grouped.items()}
