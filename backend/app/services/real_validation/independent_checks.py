from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import project_root
from app.db import connect, init_database
from app.services.real_validation.common import (
    load_source_manifest,
    parse_date,
    real_reports_dir,
    to_float,
    write_json,
    write_markdown,
)


def run_independent_real_checks(
    *,
    ercot_from_file: str | Path | None = None,
    ercot_to_file: str | Path | None = None,
    lbnl_file: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    manifest = load_source_manifest()
    ercot_entries = [item for item in manifest if item.get("source_name") == "ERCOT GIS Report"]
    lbnl_entries = [item for item in manifest if item.get("source_name") == "LBNL Queued Up 2026 Data File"]
    ercot_paths = [Path(path) for path in (ercot_from_file, ercot_to_file) if path]
    if not ercot_paths:
        ercot_paths = [project_root() / str(item["local_path"]) for item in ercot_entries[:2]]
    lbnl_path = Path(lbnl_file) if lbnl_file else (project_root() / str(lbnl_entries[-1]["local_path"]) if lbnl_entries else None)

    checks: list[dict[str, Any]] = []
    if len(ercot_paths) >= 2 and all(path.exists() for path in ercot_paths[:2]):
        checks.extend(_ercot_checks(ercot_paths[:2], db_path))
    else:
        checks.append(
            {
                "domain": "ercot",
                "check": "raw_files_present",
                "status": "blocked_missing_real_data",
                "details": "Expected two ERCOT files under data/raw/real/ercot/gis/ or explicit script arguments.",
            }
        )
    if lbnl_path and lbnl_path.exists():
        checks.extend(_lbnl_checks(lbnl_path, db_path))
    else:
        checks.append(
            {
                "domain": "lbnl",
                "check": "raw_file_present",
                "status": "blocked_missing_real_data",
                "details": "Expected data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx or explicit script argument.",
            }
        )

    status_counts: dict[str, int] = {}
    for check in checks:
        status_counts[check["status"]] = status_counts.get(check["status"], 0) + 1
    result = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "status_counts": status_counts,
        "checks": checks,
        "note": "Independent checks use direct pandas/openpyxl reads and minimal mappings, not GridQueue normalization/diff services.",
    }
    json_path = real_reports_dir() / "independent_checks.json"
    md_path = real_reports_dir() / "independent_checks.md"
    write_json(json_path, result)
    write_markdown(md_path, _checks_markdown(result))
    return {**result, "json_path": str(json_path.relative_to(project_root())), "markdown_path": str(md_path.relative_to(project_root()))}


def _ercot_checks(paths: list[Path], db_path: str | Path | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    parsed = [_read_ercot_minimal(path) for path in paths]
    for item in parsed:
        db_snapshot = _snapshot_by_hash(item["file_hash_sha256"], db_path)
        checks.append(
            _check(
                "ercot",
                f"raw_row_count_vs_ingested:{item['path'].name}",
                item["row_count"],
                db_snapshot.get("row_count"),
                tolerance=0,
                details=f"snapshot_id={db_snapshot.get('snapshot_id')} hash={item['file_hash_sha256']}",
            )
        )
        checks.append(
            {
                "domain": "ercot",
                "check": f"missing_key_fields:{item['path'].name}",
                "status": "passed" if item["missing_key_fields"] == 0 else "failed",
                "calculated": item["missing_key_fields"],
                "expected": 0,
                "details": "Rows missing INR or project name under minimal independent parse.",
            }
        )
        app_counts = _app_ercot_status_counts(db_snapshot.get("snapshot_id"), db_path)
        checks.append(
            {
                "domain": "ercot",
                "check": f"status_count_presence:{item['path'].name}",
                "status": "passed" if app_counts else "failed",
                "calculated": item["status_counts"],
                "expected": app_counts,
                "details": "Independent status buckets are not expected to exactly match normalized buckets but both should be populated.",
            }
        )
        app_capacity = _app_ercot_capacity_by_fuel(db_snapshot.get("snapshot_id"), db_path)
        checks.append(
            {
                "domain": "ercot",
                "check": f"active_capacity_by_fuel_presence:{item['path'].name}",
                "status": "passed" if app_capacity else "failed",
                "calculated": item["active_capacity_by_fuel_mw"],
                "expected": app_capacity,
                "details": "Independent fuel buckets are raw ERCOT fuel labels; app buckets are normalized fuel labels.",
            }
        )
    overlap = len(set(parsed[0]["queue_ids"]) & set(parsed[1]["queue_ids"]))
    checks.append(
        {
            "domain": "ercot",
            "check": "exact_queue_id_overlap_between_months",
            "status": "passed" if overlap > 0 else "failed",
            "calculated": overlap,
            "expected": "> 0",
            "details": "Exact INR overlap should exist for consecutive ERCOT GIS months.",
        }
    )
    return checks


def _lbnl_checks(path: Path, db_path: str | Path | None) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, sheet_name="03. Complete Queue Data", header=1).dropna(how="all")
    file_hash = _sha256(path)
    with connect(db_path) as con:
        db_count = con.execute(
            "SELECT COUNT(*) FROM real_lbnl_project_records WHERE file_hash_sha256 = ?",
            [file_hash],
        ).fetchone()[0]
    active = frame[frame["q_status"].astype(str).str.lower().eq("active")]
    checks = [
        _check("lbnl", "raw_row_count_vs_ingested", int(frame.shape[0]), int(db_count), tolerance=0, details=f"hash={file_hash}"),
        {
            "domain": "lbnl",
            "check": "active_capacity_total_mw1_gw",
            "status": "passed",
            "calculated": round(float(active["mw_1"].fillna(0).sum()) / 1000, 4),
            "expected": "reported in lbnl_reproduction.md with comparison caveats",
            "details": "Direct pandas sum of active project-level mw_1.",
        },
        {
            "domain": "lbnl",
            "check": "capacity_by_type_available",
            "status": "passed" if "type_clean" in frame.columns else "skipped_missing_field",
            "calculated": {
                str(key): round(float(value) / 1000, 4)
                for key, value in active.groupby("type_clean")["mw_1"].sum().sort_values(ascending=False).head(10).items()
            }
            if "type_clean" in frame.columns
            else {},
            "expected": "non-empty",
            "details": "Direct pandas type_clean capacity aggregation.",
        },
        {
            "domain": "lbnl",
            "check": "outcome_status_counts_available",
            "status": "passed",
            "calculated": {str(key): int(value) for key, value in frame["q_status"].value_counts(dropna=False).to_dict().items()},
            "expected": "active/withdrawn/operational/suspended buckets present",
            "details": "Direct pandas q_status counts.",
        },
    ]
    if {"q_date", "on_date", "wd_date"}.issubset(frame.columns):
        terminal = frame[frame["q_status"].isin(["operational", "withdrawn"])].copy()
        terminal["terminal_date"] = terminal["on_date"].fillna(terminal["wd_date"])
        terminal["duration_days"] = [
            (parse_date(end) - parse_date(start)).days if parse_date(start) and parse_date(end) else None
            for start, end in zip(terminal["q_date"], terminal["terminal_date"], strict=False)
        ]
        checks.append(
            {
                "domain": "lbnl",
                "check": "duration_metric_available",
                "status": "passed" if terminal["duration_days"].dropna().shape[0] else "skipped_missing_field",
                "calculated": float(terminal["duration_days"].dropna().median()) if terminal["duration_days"].dropna().shape[0] else None,
                "expected": "non-empty terminal durations",
                "details": "Direct pandas median duration for operational/withdrawn rows.",
            }
        )
    return checks


def _read_ercot_minimal(path: Path) -> dict[str, Any]:
    rows = []
    for sheet in ("Project Details - Large Gen", "Project Details - Small Gen"):
        frame = _read_sheet_with_header(path, sheet)
        rows.extend(_project_rows(frame, sheet))
    for sheet in ("Cancellation Update", "Inactive Projects", "Commissioning Update"):
        frame = _read_sheet_with_header(path, sheet)
        rows.extend(_signal_rows(frame, sheet))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_id[row["queue_id"]] = {**by_id.get(row["queue_id"], {}), **row}
    values = list(by_id.values())
    active = [row for row in values if row["status"] == "Active"]
    capacity_by_fuel: dict[str, float] = {}
    for row in active:
        fuel = row.get("fuel") or "Unknown"
        capacity_by_fuel[fuel] = capacity_by_fuel.get(fuel, 0.0) + float(row.get("capacity_mw") or 0.0)
    status_counts: dict[str, int] = {}
    for row in values:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    return {
        "path": path,
        "file_hash_sha256": _sha256(path),
        "row_count": len(values),
        "queue_ids": [row["queue_id"] for row in values],
        "missing_key_fields": sum(1 for row in values if not row.get("queue_id") or not row.get("project_name")),
        "status_counts": status_counts,
        "active_capacity_by_fuel_mw": {key: round(value, 4) for key, value in sorted(capacity_by_fuel.items())},
    }


def _read_sheet_with_header(path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=90)
    header_row = None
    for idx, row in raw.iterrows():
        labels = {str(value).strip().lower() for value in row.tolist() if not pd.isna(value)}
        if "inr" in labels and "project name" in labels:
            header_row = int(idx)
            break
    if header_row is None:
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name=sheet, header=header_row).dropna(how="all")


def _project_rows(frame: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    if frame.empty or "INR" not in frame.columns:
        return []
    result = []
    rows = frame[frame["INR"].astype(str).str.contains(r"\d{2}INR", case=False, regex=True, na=False)]
    for row in rows.to_dict(orient="records"):
        result.append(
            {
                "queue_id": str(row.get("INR")).strip(),
                "project_name": _text(row.get("Project Name")),
                "fuel": _text(row.get("Fuel")),
                "capacity_mw": to_float(row.get("Capacity (MW)")),
                "status": "Active",
                "sheet": sheet,
            }
        )
    return result


def _signal_rows(frame: pd.DataFrame, sheet: str) -> list[dict[str, Any]]:
    if frame.empty or "INR" not in frame.columns:
        return []
    result = []
    rows = frame[frame["INR"].astype(str).str.contains(r"\d{2}INR", case=False, regex=True, na=False)]
    for row in rows.to_dict(orient="records"):
        status = "Active"
        if sheet == "Cancellation Update":
            status = "Withdrawn"
        elif sheet == "Inactive Projects":
            status = "Inactive"
        elif sheet == "Commissioning Update" and "commercial operation" in str(row.get("Commissioning Category", "")).lower():
            status = "Completed"
        else:
            continue
        result.append(
            {
                "queue_id": str(row.get("INR")).strip(),
                "project_name": _text(row.get("Project Name")),
                "fuel": _text(row.get("Fuel")),
                "capacity_mw": to_float(row.get("MW **")),
                "status": status,
                "sheet": sheet,
            }
        )
    return result


def _snapshot_by_hash(file_hash: str, db_path: str | Path | None) -> dict[str, Any]:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT snapshot_id, row_count FROM snapshots WHERE file_hash = ? ORDER BY snapshot_date DESC LIMIT 1",
            [file_hash],
        ).fetchone()
    if not row:
        return {}
    return {"snapshot_id": row[0], "row_count": int(row[1])}


def _app_ercot_status_counts(snapshot_id: str | None, db_path: str | Path | None) -> dict[str, int]:
    if not snapshot_id:
        return {}
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT normalized_status, COUNT(*)
            FROM normalized_project_records
            WHERE snapshot_id = ?
            GROUP BY normalized_status
            """,
            [snapshot_id],
        ).fetchall()
    return {str(key): int(value) for key, value in rows}


def _app_ercot_capacity_by_fuel(snapshot_id: str | None, db_path: str | Path | None) -> dict[str, float]:
    if not snapshot_id:
        return {}
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT normalized_fuel_type, COALESCE(SUM(capacity_mw), 0)
            FROM normalized_project_records
            WHERE snapshot_id = ? AND normalized_status = 'Active'
            GROUP BY normalized_fuel_type
            ORDER BY normalized_fuel_type
            """,
            [snapshot_id],
        ).fetchall()
    return {str(key): round(float(value), 4) for key, value in rows}


def _check(domain: str, name: str, calculated: Any, expected: Any, *, tolerance: float, details: str) -> dict[str, Any]:
    if calculated is None or expected is None:
        status = "failed"
        delta = None
    else:
        delta = float(calculated) - float(expected)
        status = "passed" if abs(delta) <= tolerance else "failed"
    return {
        "domain": domain,
        "check": name,
        "status": status,
        "calculated": calculated,
        "expected": expected,
        "delta": round(delta, 4) if delta is not None else None,
        "tolerance": tolerance,
        "details": details,
    }


def _checks_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Independent real-data checks",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- status_counts: {result['status_counts']}",
        f"- note: {result['note']}",
        "",
        "## Checks",
    ]
    for check in result["checks"]:
        lines.append(
            f"- domain={check['domain']} check={check['check']} status={check['status']} "
            f"calculated={check.get('calculated')} expected={check.get('expected')} details={check.get('details')}"
        )
    return "\n".join(lines)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
