from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.metrics import compute_metric_rollup


PROJECT_TYPE_TO_PROXY_FUEL = {
    "ai data center load": "Battery",
    "data center load": "Battery",
    "generic large load": "Battery",
    "large load": "Battery",
    "battery storage": "Battery",
    "storage": "Battery",
    "battery": "Battery",
    "solar + storage": "Hybrid",
    "solar storage": "Hybrid",
    "hybrid": "Hybrid",
    "solar": "Solar",
    "wind": "Wind",
    "gas": "Gas",
}


def get_interconnection_baseline(
    *,
    market: str,
    county: str | None,
    project_type: str,
    peak_mw: float | None = None,
    target_online_year: int | None = None,
    baseline_metric_id: str | None = None,
    min_sample_n: int = 30,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    if baseline_metric_id:
        metric = _metric_by_id(baseline_metric_id, db_path)
        if not metric:
            return _insufficient("Metric id was supplied but not found.", baseline_metric_id=baseline_metric_id)
    else:
        metric = compute_metric_rollup(
            market=market,
            county=county,
            fuel_type=_proxy_fuel(project_type),
            min_sample_n=min_sample_n,
            db_path=db_path,
        )

    citations = _metric_citations(metric, db_path)
    low_days = metric.get("median_duration_days")
    high_days = metric.get("p75_duration_days")
    if metric.get("confidence") == "Insufficient" or low_days is None or high_days is None:
        return {
            "status": "insufficient_interconnection_baseline",
            "baseline_low_days": None,
            "baseline_high_days": None,
            "baseline_mid_days": low_days,
            "metric_id": metric.get("metric_id"),
            "sample_n": metric.get("sample_n"),
            "fallback_level": metric.get("fallback_level"),
            "confidence": metric.get("confidence"),
            "source_snapshot_id": metric.get("source_snapshot_id"),
            "citations": citations,
            "assumptions": {
                "baseline_project_type": _proxy_fuel(project_type),
                "min_sample_n": min_sample_n,
                "peak_mw": peak_mw,
                "target_online_year": target_online_year,
            },
            "caveats": [
                "No fallback scope produced a sufficient duration sample; GridQueue abstains from an interconnection timeline.",
                "Baseline is a public queue proxy, not a formal study or approval forecast.",
            ],
        }

    return {
        "status": "complete",
        "baseline_low_days": float(low_days),
        "baseline_high_days": float(max(high_days, low_days)),
        "baseline_mid_days": float(low_days),
        "metric_id": metric.get("metric_id"),
        "sample_n": metric.get("sample_n"),
        "fallback_level": metric.get("fallback_level"),
        "confidence": metric.get("confidence"),
        "source_snapshot_id": metric.get("source_snapshot_id"),
        "citations": citations,
        "assumptions": {
            "baseline_project_type": _proxy_fuel(project_type),
            "min_sample_n": min_sample_n,
            "peak_mw": peak_mw,
            "target_online_year": target_online_year,
        },
        "caveats": [
            "Baseline is a sample-aware historical proxy from public queue records, not a formal interconnection study.",
            "Large-load scenarios use generation-queue proxy records where no verified large-load queue fixture is available.",
        ],
    }


def _proxy_fuel(project_type: str) -> str:
    return PROJECT_TYPE_TO_PROXY_FUEL.get(project_type.strip().lower(), project_type)


def _metric_by_id(metric_id: str, db_path: str | Path | None) -> dict[str, Any] | None:
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT metric_id, market, scope_type, scope_value, fuel_type, sample_n, active_count,
                   active_mw, completed_count, withdrawn_count, completion_rate, withdrawal_rate,
                   median_duration_days, p75_duration_days, confidence, fallback_level, source_snapshot_id, created_at
            FROM metric_rollups
            WHERE metric_id = ?
            """,
            [metric_id],
        ).fetchone()
    if not row:
        return None
    return {
        "metric_id": row[0],
        "market": row[1],
        "scope_type": row[2],
        "scope_value": row[3],
        "fuel_type": row[4],
        "sample_n": row[5],
        "active_count": row[6],
        "active_mw": row[7],
        "completed_count": row[8],
        "withdrawn_count": row[9],
        "completion_rate": row[10],
        "withdrawal_rate": row[11],
        "median_duration_days": row[12],
        "p75_duration_days": row[13],
        "confidence": row[14],
        "fallback_level": row[15],
        "source_snapshot_id": row[16],
        "created_at": row[17],
    }


def _metric_citations(metric: dict[str, Any], db_path: str | Path | None) -> list[dict[str, Any]]:
    snapshot_id = metric.get("source_snapshot_id")
    if not snapshot_id:
        return []
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT sn.snapshot_id, sn.snapshot_date, s.source_id, s.source_name, s.source_url, s.source_type
            FROM snapshots sn
            JOIN sources s ON s.source_id = sn.source_id
            WHERE sn.snapshot_id = ?
            """,
            [snapshot_id],
        ).fetchone()
    if not row:
        return []
    return [
        {
            "citation_label": "Interconnection baseline metric source",
            "citation_text": f"Metric {metric.get('metric_id')} uses snapshot {row[0]} dated {row[1]} with sample_n={metric.get('sample_n')}.",
            "source_id": row[2],
            "source_snapshot_id": row[0],
            "source_name": row[3],
            "source_url": row[4],
            "source_type": row[5],
        }
    ]


def _insufficient(explanation: str, baseline_metric_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "insufficient_interconnection_baseline",
        "baseline_low_days": None,
        "baseline_high_days": None,
        "baseline_mid_days": None,
        "metric_id": baseline_metric_id,
        "sample_n": 0,
        "fallback_level": "none",
        "confidence": "Insufficient",
        "source_snapshot_id": None,
        "citations": [],
        "assumptions": {},
        "caveats": [explanation],
    }


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
