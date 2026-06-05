from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import connect, init_database, table_counts
from app.schemas import BriefRequest, DiffRequest, IngestManualRequest, MetricsRequest
from app.services.brief_generation import generate_brief
from app.services.diffing import diff_snapshots, get_diff_result
from app.services.entity_resolution import resolve_market
from app.services.ingestion import ingest_manual_file, run_fixture_pipeline
from app.services.metrics import compute_metric_rollup


router = APIRouter()


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/health")
def health() -> dict[str, str]:
    init_database()
    return {"status": "ok"}


@router.get("/sources")
def sources() -> dict[str, Any]:
    init_database()
    with connect() as con:
        rows = con.execute(
            """
            SELECT s.source_id, s.source_name, s.source_url, s.source_type, s.retrieved_at,
                   s.publication_date, s.notes, COUNT(sn.snapshot_id) AS snapshots
            FROM sources s
            LEFT JOIN snapshots sn ON sn.source_id = s.source_id
            GROUP BY s.source_id, s.source_name, s.source_url, s.source_type, s.retrieved_at,
                     s.publication_date, s.notes
            ORDER BY s.source_name
            """
        ).fetchall()
    return {
        "sources": [
            {
                "source_id": row[0],
                "source_name": row[1],
                "source_url": row[2],
                "source_type": row[3],
                "retrieved_at": _iso(row[4]),
                "publication_date": _iso(row[5]),
                "notes": row[6],
                "snapshot_count": row[7],
            }
            for row in rows
        ]
    }


@router.get("/snapshots")
def snapshots() -> dict[str, Any]:
    init_database()
    with connect() as con:
        rows = con.execute(
            """
            SELECT snapshot_id, market, source_id, snapshot_date, file_hash, row_count,
                   ingestion_mode, created_at
            FROM snapshots
            ORDER BY market, snapshot_date
            """
        ).fetchall()
    return {
        "snapshots": [
            {
                "snapshot_id": row[0],
                "market": row[1],
                "source_id": row[2],
                "snapshot_date": _iso(row[3]),
                "file_hash": row[4],
                "row_count": row[5],
                "ingestion_mode": row[6],
                "created_at": _iso(row[7]),
            }
            for row in rows
        ]
    }


@router.post("/ingest/fixtures")
def ingest_fixtures() -> dict[str, Any]:
    return run_fixture_pipeline(reset=True)


@router.post("/ingest/ercot")
def ingest_ercot(request: IngestManualRequest | None = None) -> dict[str, Any]:
    local_path = request.local_path if request else None
    if not local_path:
        return {
            "status": "manual_download_required",
            "message": "Automatic ERCOT GIS download is intentionally conservative for this MVP. Download the current GIS report from ERCOT, place it in data/raw, then call this endpoint with local_path.",
            "source_url": "https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er",
            "example": {"local_path": "data/raw/ERCOT_GIS_Report.xlsx", "market": "ERCOT", "source_kind": "ercot"},
        }
    return ingest_manual_file(
        local_path,
        market=request.market,
        source_name="ERCOT GIS Report manual file",
        source_url="https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er",
        source_type="manual_ercot_gis",
        ingestion_mode="manual_ercot",
    )


@router.post("/ingest/lbnl")
def ingest_lbnl(request: IngestManualRequest | None = None) -> dict[str, Any]:
    local_path = request.local_path if request else None
    if not local_path:
        return {
            "status": "manual_download_required",
            "message": "Download LBNL Queued Up data from the source page, place it in data/raw, then call this endpoint with local_path.",
            "source_url": "https://emp.lbl.gov/queues",
            "example": {"local_path": "data/raw/lbnl_queued_up.xlsx", "market": "LBNL", "source_kind": "lbnl"},
        }
    return ingest_manual_file(
        local_path,
        market=request.market,
        source_name="LBNL Queued Up manual file",
        source_url="https://emp.lbl.gov/queues",
        source_type="manual_lbnl",
        ingestion_mode="manual_lbnl",
    )


@router.post("/diff")
def create_diff(request: DiffRequest) -> dict[str, Any]:
    resolve_market(request.market)
    return diff_snapshots(request.market, request.from_snapshot_id, request.to_snapshot_id)


@router.get("/diff/{from_snapshot_id}/{to_snapshot_id}")
def read_diff(from_snapshot_id: str, to_snapshot_id: str) -> dict[str, Any]:
    return get_diff_result(from_snapshot_id, to_snapshot_id)


@router.post("/metrics")
def metrics(request: MetricsRequest) -> dict[str, Any]:
    return compute_metric_rollup(
        market=request.market,
        county=request.county,
        fuel_type=request.fuel_type,
        min_sample_n=request.min_sample_n,
    )


@router.post("/brief")
def brief(request: BriefRequest) -> dict[str, Any]:
    try:
        return generate_brief(
            market=request.market,
            project_type=request.project_type,
            county=request.county,
            capacity_mw=request.capacity_mw,
            target_cod_year=request.target_cod_year,
            question=request.question,
            min_sample_n=request.min_sample_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/entity-matches/{snapshot_id}")
def entity_matches(snapshot_id: str) -> dict[str, Any]:
    init_database()
    with connect() as con:
        rows = con.execute(
            """
            SELECT l.link_id, l.entity_id, l.record_id, l.snapshot_id, l.match_score, l.match_method,
                   l.match_features_json, l.is_ambiguous, r.queue_id, r.project_name, r.county,
                   r.normalized_fuel_type, r.capacity_mw
            FROM project_entity_links l
            JOIN normalized_project_records r ON r.record_id = l.record_id
            WHERE l.snapshot_id = ?
            ORDER BY l.is_ambiguous DESC, l.match_score ASC, r.project_name
            """,
            [snapshot_id],
        ).fetchall()
    return {
        "snapshot_id": snapshot_id,
        "matches": [
            {
                "link_id": row[0],
                "entity_id": row[1],
                "record_id": row[2],
                "snapshot_id": row[3],
                "match_score": row[4],
                "match_method": row[5],
                "match_features_json": json.loads(row[6]) if isinstance(row[6], str) else row[6],
                "is_ambiguous": row[7],
                "queue_id": row[8],
                "project_name": row[9],
                "county": row[10],
                "fuel_type": row[11],
                "capacity_mw": row[12],
            }
            for row in rows
        ],
    }


@router.get("/counts")
def counts() -> dict[str, int]:
    return table_counts()


@router.post("/evals/run")
def run_evals() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, str(repo_root / "evals" / "run_evals.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
