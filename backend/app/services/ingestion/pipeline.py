from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.config import fixtures_dir
from app.db import connect, init_database, reset_database
from app.services.citations import ensure_reference_sources, insert_record_citation
from app.services.normalization.normalizer import get_value, normalize_date, normalize_record
from app.services.utils import file_sha256, new_id, stable_json, utcnow


FIXTURE_SOURCE_ID = "src_fixture_ercot_gis_like"
FIXTURE_SOURCE_URL = "synthetic://gridqueue-agent/fixtures/ercot-gis-like"


def _clean_payload(value: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if pd.isna(item):
            cleaned[key] = None
        elif hasattr(item, "isoformat"):
            cleaned[key] = item.isoformat()
        else:
            cleaned[key] = item
    return cleaned


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _snapshot_date_from_frame(frame: pd.DataFrame, fallback: str) -> str:
    if "Snapshot Date" in frame.columns:
        parsed = pd.to_datetime(frame["Snapshot Date"].dropna().iloc[0], errors="coerce")
        if not pd.isna(parsed):
            return str(parsed.date())
    return fallback


def _insert_source(con: Any, *, source_id: str, source_name: str, source_url: str, source_type: str, notes: str) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO sources
        (source_id, source_name, source_url, source_type, retrieved_at, publication_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [source_id, source_name, source_url, source_type, utcnow(), None, notes],
    )


def ingest_fixture_data(db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    ensure_reference_sources(db_path)
    files = sorted(fixtures_dir().glob("ercot_*.csv"))
    if not files:
        raise FileNotFoundError(f"No fixture CSV files found in {fixtures_dir()}")

    snapshot_ids: list[str] = []
    with connect(db_path) as con:
        _insert_source(
            con,
            source_id=FIXTURE_SOURCE_ID,
            source_name="Synthetic ERCOT GIS-like fixtures",
            source_url=FIXTURE_SOURCE_URL,
            source_type="synthetic_fixture",
            notes="Synthetic data for deterministic entity-resolution, diff, metric, and brief tests.",
        )
        for file_path in files:
            frame = _read_table(file_path)
            snapshot_date = _snapshot_date_from_frame(frame, file_path.stem.replace("ercot_", "").replace("_", "-") + "-01")
            snapshot_id = f"snap_ercot_{snapshot_date.replace('-', '_')}"
            con.execute(
                """
                INSERT OR REPLACE INTO snapshots
                (snapshot_id, market, source_id, snapshot_date, file_hash, row_count, ingestion_mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [snapshot_id, "ERCOT", FIXTURE_SOURCE_ID, snapshot_date, file_sha256(file_path), len(frame), "fixture", utcnow()],
            )
            snapshot_ids.append(snapshot_id)

            for idx, raw in enumerate(frame.to_dict(orient="records"), start=1):
                payload = _clean_payload(raw)
                raw_record_id = new_id("raw")
                con.execute(
                    """
                    INSERT INTO raw_project_records
                    (raw_record_id, snapshot_id, raw_payload_json, row_number, source_sheet, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [raw_record_id, snapshot_id, stable_json(payload), idx, file_path.name, utcnow()],
                )
                record = normalize_record(payload, raw_record_id, snapshot_id, "ERCOT")
                _insert_normalized_record(con, record)
                insert_record_citation(
                    con,
                    source_id=FIXTURE_SOURCE_ID,
                    snapshot_id=snapshot_id,
                    record_id=record["record_id"],
                    citation_label=f"{snapshot_date} row {idx}",
                    citation_text=(
                        "Synthetic ERCOT GIS-like fixture "
                        f"{file_path.name}, row {idx}, queue_id={record['queue_id'] or 'missing'}."
                    ),
                    source_url=FIXTURE_SOURCE_URL,
                )
    return {"snapshots": snapshot_ids, "row_count": sum(pd.read_csv(path).shape[0] for path in files)}


def ingest_manual_file(
    path: str | Path,
    *,
    market: str,
    source_name: str,
    source_url: str,
    source_type: str,
    ingestion_mode: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    ensure_reference_sources(db_path)
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Manual ingestion file does not exist: {file_path}")

    frame = _read_table(file_path)
    first_payload = _clean_payload(frame.to_dict(orient="records")[0]) if len(frame) else {}
    parsed_snapshot_date = normalize_date(get_value(first_payload, "last_updated_date"))
    if parsed_snapshot_date is None:
        parsed_snapshot_date = pd.Timestamp.utcnow().date()
    source_id = new_id("src")
    snapshot_id = f"snap_{market.lower()}_{parsed_snapshot_date.isoformat().replace('-', '_')}_{new_id('file')[-6:]}"

    with connect(db_path) as con:
        _insert_source(
            con,
            source_id=source_id,
            source_name=source_name,
            source_url=source_url,
            source_type=source_type,
            notes=f"Manual local file ingestion from {file_path.name}.",
        )
        con.execute(
            """
            INSERT INTO snapshots
            (snapshot_id, market, source_id, snapshot_date, file_hash, row_count, ingestion_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [snapshot_id, market, source_id, parsed_snapshot_date, file_sha256(file_path), len(frame), ingestion_mode, utcnow()],
        )
        for idx, raw in enumerate(frame.to_dict(orient="records"), start=1):
            payload = _clean_payload(raw)
            raw_record_id = new_id("raw")
            con.execute(
                """
                INSERT INTO raw_project_records
                (raw_record_id, snapshot_id, raw_payload_json, row_number, source_sheet, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [raw_record_id, snapshot_id, stable_json(payload), idx, file_path.name, utcnow()],
            )
            record = normalize_record(payload, raw_record_id, snapshot_id, market)
            _insert_normalized_record(con, record)
            insert_record_citation(
                con,
                source_id=source_id,
                snapshot_id=snapshot_id,
                record_id=record["record_id"],
                citation_label=f"{market} {parsed_snapshot_date} row {idx}",
                citation_text=f"{source_name}, local file {file_path.name}, row {idx}.",
                source_url=source_url,
            )
    return {"snapshot_id": snapshot_id, "row_count": len(frame), "source_id": source_id}


def run_fixture_pipeline(db_path: str | Path | None = None, *, reset: bool = True) -> dict[str, Any]:
    if reset:
        reset_database(db_path)
    result = ingest_fixture_data(db_path)

    from app.services.entity_resolution.resolver import resolve_market
    from app.services.diffing.service import diff_adjacent_snapshots
    from app.services.metrics.service import precompute_default_rollups

    resolve_market("ERCOT", db_path)
    diff_result = diff_adjacent_snapshots("ERCOT", db_path)
    precompute_default_rollups("ERCOT", db_path)
    result["diffs"] = diff_result
    return result


def _insert_normalized_record(con: Any, record: dict[str, Any]) -> None:
    con.execute(
        """
        INSERT INTO normalized_project_records
        (record_id, snapshot_id, market, queue_id, project_name, normalized_project_name,
         interconnecting_entity, county, state, point_of_interconnection, transmission_owner,
         fuel_type, normalized_fuel_type, capacity_mw, status, normalized_status,
         request_date, target_cod, actual_cod, withdrawn_date, interconnection_agreement_date,
         last_updated_date, raw_record_id, data_quality_flags_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            record["record_id"],
            record["snapshot_id"],
            record["market"],
            record["queue_id"],
            record["project_name"],
            record["normalized_project_name"],
            record["interconnecting_entity"],
            record["county"],
            record["state"],
            record["point_of_interconnection"],
            record["transmission_owner"],
            record["fuel_type"],
            record["normalized_fuel_type"],
            record["capacity_mw"],
            record["status"],
            record["normalized_status"],
            record["request_date"],
            record["target_cod"],
            record["actual_cod"],
            record["withdrawn_date"],
            record["interconnection_agreement_date"],
            record["last_updated_date"],
            record["raw_record_id"],
            stable_json(record["data_quality_flags_json"]),
        ],
    )

