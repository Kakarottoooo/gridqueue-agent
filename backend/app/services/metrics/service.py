from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from app.db import connect, init_database
from app.services.utils import new_id, utcnow


def compute_metric_rollup(
    *,
    market: str,
    county: str | None,
    fuel_type: str | None,
    min_sample_n: int = 30,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        snapshot = con.execute(
            """
            SELECT snapshot_id, snapshot_date
            FROM snapshots
            WHERE market = ?
            ORDER BY snapshot_date DESC, snapshot_id DESC
            LIMIT 1
            """,
            [market],
        ).fetchone()
        if not snapshot:
            return _insufficient_result(market, county, fuel_type, min_sample_n, None, "No snapshots are available for this market.")

        source_snapshot_id = snapshot[0]
        levels = _fallback_levels(market, county, fuel_type)
        last_candidate: dict[str, Any] | None = None
        for level in levels:
            records = _records_for_level(con, source_snapshot_id, level)
            candidate = _calculate(level, records, market, source_snapshot_id, min_sample_n)
            last_candidate = candidate
            if candidate["sample_n"] >= min_sample_n:
                _store_metric(con, candidate)
                return candidate

        result = last_candidate or _insufficient_result(market, county, fuel_type, min_sample_n, source_snapshot_id, "No comparable records found.")
        result["completion_rate"] = None
        result["withdrawal_rate"] = None
        result["median_duration_days"] = None
        result["p75_duration_days"] = None
        result["confidence"] = "Insufficient"
        result["explanation"] = (
            f"No fallback scope reached min_sample_n={min_sample_n}; "
            "GridQueue abstains from reporting completion or withdrawal rates."
        )
        _store_metric(con, result)
        return result


def precompute_default_rollups(market: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_database(db_path)
    results = []
    with connect(db_path) as con:
        latest = con.execute(
            "SELECT snapshot_id FROM snapshots WHERE market = ? ORDER BY snapshot_date DESC LIMIT 1",
            [market],
        ).fetchone()
        if not latest:
            return results
        rows = con.execute(
            """
            SELECT DISTINCT county, normalized_fuel_type
            FROM normalized_project_records
            WHERE snapshot_id = ?
            ORDER BY county, normalized_fuel_type
            """,
            [latest[0]],
        ).fetchall()
    for county, fuel in rows:
        results.append(compute_metric_rollup(market=market, county=county, fuel_type=fuel, min_sample_n=2, db_path=db_path))
    return results


def _fallback_levels(market: str, county: str | None, fuel_type: str | None) -> list[dict[str, str | None]]:
    levels: list[dict[str, str | None]] = []
    if county and fuel_type:
        levels.append({"fallback_level": "county_fuel", "scope_type": "county", "scope_value": county, "fuel_type": fuel_type})
    if county:
        levels.append({"fallback_level": "county_all_fuels", "scope_type": "county", "scope_value": county, "fuel_type": None})
    if fuel_type:
        levels.append({"fallback_level": "market_fuel", "scope_type": "market", "scope_value": market, "fuel_type": fuel_type})
    levels.append({"fallback_level": "market_all", "scope_type": "market", "scope_value": market, "fuel_type": None})
    levels.append({"fallback_level": "lbnl_national_fuel", "scope_type": "lbnl_national", "scope_value": "US queues", "fuel_type": fuel_type})
    levels.append({"fallback_level": "lbnl_national_all", "scope_type": "lbnl_national", "scope_value": "US queues", "fuel_type": None})
    return levels


def _records_for_level(con: Any, snapshot_id: str, level: dict[str, str | None]) -> list[dict[str, Any]]:
    if level["scope_type"] == "lbnl_national":
        return []
    filters = ["snapshot_id = ?"]
    params: list[Any] = [snapshot_id]
    if level["scope_type"] == "county":
        filters.append("county = ?")
        params.append(level["scope_value"])
    if level["fuel_type"]:
        filters.append("normalized_fuel_type = ?")
        params.append(level["fuel_type"])
    where_clause = " AND ".join(filters)
    rows = con.execute(
        f"""
        SELECT record_id, normalized_status, capacity_mw, request_date, actual_cod, withdrawn_date
        FROM normalized_project_records
        WHERE {where_clause}
        """,
        params,
    ).fetchall()
    return [
        {
            "record_id": row[0],
            "status": row[1],
            "capacity_mw": row[2],
            "request_date": row[3],
            "actual_cod": row[4],
            "withdrawn_date": row[5],
        }
        for row in rows
    ]


def _calculate(
    level: dict[str, str | None],
    records: list[dict[str, Any]],
    market: str,
    source_snapshot_id: str,
    min_sample_n: int,
) -> dict[str, Any]:
    sample_n = len(records)
    active = [row for row in records if row["status"] == "Active"]
    completed = [row for row in records if row["status"] == "Completed"]
    withdrawn = [row for row in records if row["status"] == "Withdrawn"]
    durations = []
    for row in completed:
        if row["request_date"] and row["actual_cod"]:
            durations.append((row["actual_cod"] - row["request_date"]).days)
    for row in withdrawn:
        if row["request_date"] and row["withdrawn_date"]:
            durations.append((row["withdrawn_date"] - row["request_date"]).days)

    report_rates = sample_n >= min_sample_n
    return {
        "metric_id": new_id("met"),
        "market": market,
        "scope_type": level["scope_type"],
        "scope_value": level["scope_value"] or market,
        "fuel_type": level["fuel_type"],
        "sample_n": sample_n,
        "active_count": len(active),
        "active_mw": float(sum(row["capacity_mw"] or 0.0 for row in active)),
        "completed_count": len(completed),
        "withdrawn_count": len(withdrawn),
        "completion_rate": round(len(completed) / sample_n, 4) if report_rates and sample_n else None,
        "withdrawal_rate": round(len(withdrawn) / sample_n, 4) if report_rates and sample_n else None,
        "median_duration_days": float(median(durations)) if report_rates and durations else None,
        "p75_duration_days": _percentile(durations, 0.75) if report_rates and durations else None,
        "confidence": _confidence(sample_n, min_sample_n, level["fallback_level"]),
        "fallback_level": level["fallback_level"],
        "source_snapshot_id": source_snapshot_id,
        "created_at": utcnow().isoformat(),
        "explanation": _explanation(sample_n, min_sample_n, level["fallback_level"]),
    }


def _confidence(sample_n: int, min_sample_n: int, fallback_level: str) -> str:
    if sample_n < min_sample_n:
        return "Insufficient"
    if sample_n >= 100 and fallback_level in {"county_fuel", "county_all_fuels", "market_fuel", "market_all"}:
        return "High"
    if sample_n >= 30 and fallback_level in {"county_fuel", "county_all_fuels", "market_fuel", "market_all"}:
        return "Medium"
    return "Low"


def _explanation(sample_n: int, min_sample_n: int, fallback_level: str) -> str:
    if sample_n < min_sample_n:
        return f"Scope sample_n={sample_n} is below min_sample_n={min_sample_n}; attempting broader fallback."
    if fallback_level == "county_fuel":
        return "County plus fuel-type scope reached the sample threshold."
    return f"Rolled up to {fallback_level} to satisfy the sample threshold."


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower))


def _store_metric(con: Any, metric: dict[str, Any]) -> None:
    con.execute(
        """
        INSERT INTO metric_rollups
        (metric_id, market, scope_type, scope_value, fuel_type, sample_n, active_count,
         active_mw, completed_count, withdrawn_count, completion_rate, withdrawal_rate,
         median_duration_days, p75_duration_days, confidence, fallback_level, source_snapshot_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            metric["metric_id"],
            metric["market"],
            metric["scope_type"],
            metric["scope_value"],
            metric["fuel_type"],
            metric["sample_n"],
            metric["active_count"],
            metric["active_mw"],
            metric["completed_count"],
            metric["withdrawn_count"],
            metric["completion_rate"],
            metric["withdrawal_rate"],
            metric["median_duration_days"],
            metric["p75_duration_days"],
            metric["confidence"],
            metric["fallback_level"],
            metric["source_snapshot_id"],
            metric["created_at"],
        ],
    )


def _insufficient_result(
    market: str,
    county: str | None,
    fuel_type: str | None,
    min_sample_n: int,
    source_snapshot_id: str | None,
    explanation: str,
) -> dict[str, Any]:
    return {
        "metric_id": new_id("met"),
        "market": market,
        "scope_type": "requested",
        "scope_value": county or market,
        "fuel_type": fuel_type,
        "sample_n": 0,
        "active_count": 0,
        "active_mw": 0.0,
        "completed_count": 0,
        "withdrawn_count": 0,
        "completion_rate": None,
        "withdrawal_rate": None,
        "median_duration_days": None,
        "p75_duration_days": None,
        "confidence": "Insufficient",
        "fallback_level": "none",
        "source_snapshot_id": source_snapshot_id,
        "created_at": utcnow().isoformat(),
        "explanation": explanation,
        "min_sample_n": min_sample_n,
    }

