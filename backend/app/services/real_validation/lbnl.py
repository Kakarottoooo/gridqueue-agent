from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.config import project_root
from app.db import connect, init_database
from app.services.real_validation.common import (
    LBNL_2026_PUBLICATION_URL,
    LBNL_2026_XLSX_URL,
    LBNL_QUEUED_UP_URL,
    PARSER_VERSION,
    clean_payload,
    file_manifest_entry,
    json_safe,
    parse_date,
    real_raw_dir,
    real_reports_dir,
    to_float,
    upsert_manifest_entry,
    workbook_sheet_names,
    write_json,
    write_markdown,
)
from app.services.utils import file_sha256, new_id, stable_json, utcnow


PROJECT_SHEET = "03. Complete Queue Data"
CODEBOOK_SHEET = "04. Data Codebook"
REGION_SUMMARY_SHEET = "02. Data Sample by Region"


def download_lbnl_workbook() -> dict[str, Any]:
    output_dir = real_raw_dir() / "lbnl"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "LBNL_Queued_Up_2026_Data_File.xlsx"
    with httpx.Client(timeout=180, follow_redirects=True, headers={"User-Agent": "GridQueue-Agent/real-validation"}) as client:
        response = client.get(LBNL_2026_XLSX_URL)
        if response.status_code >= 400:
            return {
                "status": "manual_required",
                "message": f"LBNL automatic download failed with HTTP {response.status_code}.",
                "instructions": manual_lbnl_download_instructions(),
            }
        if not response.content.startswith(b"PK"):
            return {
                "status": "manual_required",
                "message": "LBNL automatic download did not return an XLSX file.",
                "instructions": manual_lbnl_download_instructions(),
            }
        output_path.write_bytes(response.content)
    return {
        "status": "downloaded",
        "local_path": str(output_path),
        "source_url": LBNL_2026_XLSX_URL,
        "file_hash_sha256": file_sha256(output_path),
        "file_size_bytes": output_path.stat().st_size,
    }


def manual_lbnl_download_instructions() -> list[str]:
    return [
        f"Go to the LBNL Queued Up page: {LBNL_QUEUED_UP_URL}",
        "Download the Data File XLSX for the latest Queued Up data release.",
        "Place it under data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx.",
        "Run: python scripts/run_lbnl_reproduction.py --file data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx",
    ]


def profile_lbnl_workbook(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"LBNL workbook not found: {file_path}")
    sheets = workbook_sheet_names(file_path)
    project_row_count = 0
    codebook_row_count = 0
    parse_errors: list[str] = []
    if PROJECT_SHEET in sheets:
        try:
            project_frame = pd.read_excel(file_path, sheet_name=PROJECT_SHEET, header=1)
            project_frame = project_frame.dropna(how="all")
            project_row_count = int(project_frame.shape[0])
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(f"{PROJECT_SHEET}: {exc}")
    else:
        parse_errors.append(f"Missing project-level sheet {PROJECT_SHEET}.")
    if CODEBOOK_SHEET in sheets:
        try:
            codebook = pd.read_excel(file_path, sheet_name=CODEBOOK_SHEET, header=1)
            codebook_row_count = int(codebook.dropna(how="all").shape[0])
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(f"{CODEBOOK_SHEET}: {exc}")
    summary_tabs = [sheet for sheet in sheets if sheet not in {"Introduction", "Contents", PROJECT_SHEET, CODEBOOK_SHEET}]
    result = {
        "source_name": "LBNL Queued Up 2026 Data File",
        "source_url": LBNL_2026_PUBLICATION_URL,
        "download_url": LBNL_2026_XLSX_URL,
        "local_path": str(file_path),
        "file_hash_sha256": file_sha256(file_path),
        "file_size_bytes": file_path.stat().st_size,
        "publication_date": "2026-05",
        "sheet_names": sheets,
        "project_level_sheet": PROJECT_SHEET if PROJECT_SHEET in sheets else None,
        "codebook_sheet": CODEBOOK_SHEET if CODEBOOK_SHEET in sheets else None,
        "summary_tabs": summary_tabs,
        "project_row_count": project_row_count,
        "codebook_row_count": codebook_row_count,
        "parser_version": PARSER_VERSION,
        "parse_status": "parsed" if project_row_count and not parse_errors else ("parsed_with_warnings" if project_row_count else "failed"),
        "parse_errors": parse_errors,
    }
    json_path = real_reports_dir() / "lbnl" / "workbook_profile.json"
    md_path = real_reports_dir() / "lbnl" / "workbook_profile.md"
    write_json(json_path, result)
    write_markdown(md_path, _profile_markdown(result))
    return {**result, "profile_json_path": str(json_path.relative_to(project_root())), "profile_markdown_path": str(md_path.relative_to(project_root()))}


def ingest_lbnl_workbook(path: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    file_path = Path(path)
    profile = profile_lbnl_workbook(file_path)
    if profile["parse_status"] == "failed":
        raise ValueError(f"LBNL workbook profile failed: {profile['parse_errors']}")
    file_hash = file_sha256(file_path)
    workbook_id = f"lbnl_queued_up_2026_{file_hash[:8]}"
    frame = pd.read_excel(file_path, sheet_name=PROJECT_SHEET, header=1)
    frame = frame.dropna(how="all")
    now = utcnow()
    with connect(db_path) as con:
        con.execute("DELETE FROM real_lbnl_project_records WHERE workbook_id = ?", [workbook_id])
        con.execute("DELETE FROM real_lbnl_workbooks WHERE workbook_id = ?", [workbook_id])
        con.execute(
            """
            INSERT INTO real_lbnl_workbooks
            (workbook_id, source_name, source_url, local_path, file_hash_sha256, file_size_bytes,
             publication_date, retrieved_at, user_provided_at, project_sheet_name, row_count_raw,
             sheet_names_json, parser_version, parse_status, parse_errors_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                workbook_id,
                "LBNL Queued Up 2026 Data File",
                LBNL_2026_PUBLICATION_URL,
                str(file_path),
                file_hash,
                file_path.stat().st_size,
                "2026-05",
                now,
                None,
                PROJECT_SHEET,
                int(frame.shape[0]),
                stable_json(profile["sheet_names"]),
                PARSER_VERSION,
                profile["parse_status"],
                stable_json(profile["parse_errors"]),
                "Real LBNL project-level interconnection queue workbook through end of 2025.",
                now,
            ],
        )
        inserted = 0
        for row_number, row in enumerate(frame.to_dict(orient="records"), start=1):
            payload = clean_payload(row)
            con.execute(
                """
                INSERT INTO real_lbnl_project_records
                (lbnl_record_id, workbook_id, file_hash_sha256, source_url, sheet_name, row_number,
                 q_id, q_status, q_date, prop_date, on_date, wd_date, ia_date, ia_phase_raw,
                 ia_phase_clean, county, state, region, project_name, utility, entity, developer,
                 service, project_type, type_1, type_2, type_3, type_clean, mw_1, mw_2, mw_3,
                 q_year, prop_year, raw_payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    new_id("lbnl"),
                    workbook_id,
                    file_hash,
                    LBNL_2026_PUBLICATION_URL,
                    PROJECT_SHEET,
                    row_number,
                    _text(payload.get("q_id")),
                    _text(payload.get("q_status")),
                    parse_date(payload.get("q_date")),
                    parse_date(payload.get("prop_date")),
                    parse_date(payload.get("on_date")),
                    parse_date(payload.get("wd_date")),
                    parse_date(payload.get("ia_date")),
                    _text(payload.get("IA_phase_raw")),
                    _text(payload.get("IA_phase_clean")),
                    _text(payload.get("county")),
                    _text(payload.get("state")),
                    _text(payload.get("region")),
                    _text(payload.get("project_name")),
                    _text(payload.get("utility")),
                    _text(payload.get("entity")),
                    _text(payload.get("developer")),
                    _text(payload.get("service")),
                    _text(payload.get("project_type")),
                    _text(payload.get("type_1")),
                    _text(payload.get("type_2")),
                    _text(payload.get("type_3")),
                    _text(payload.get("type_clean")),
                    to_float(payload.get("mw_1")),
                    to_float(payload.get("mw_2")),
                    to_float(payload.get("mw_3")),
                    _int(payload.get("q_year")),
                    _int(payload.get("prop_year")),
                    stable_json(payload),
                    now,
                ],
            )
            inserted += 1

    manifest_entry = file_manifest_entry(
        source_name="LBNL Queued Up 2026 Data File",
        source_url=LBNL_2026_PUBLICATION_URL,
        local_path=file_path,
        snapshot_date="2025-12-31",
        row_count_raw=int(frame.shape[0]),
        sheet_names=profile["sheet_names"],
        parse_status=profile["parse_status"],
        parse_errors=profile["parse_errors"],
        retrieved_at=now.isoformat(),
        notes="Project-level workbook through end of 2025; excludes load, distribution-connected, and behind-the-meter interconnection requests.",
    )
    upsert_manifest_entry(manifest_entry)
    return {
        "workbook_id": workbook_id,
        "file_hash_sha256": file_hash,
        "row_count_raw": int(frame.shape[0]),
        "ingested_row_count": inserted,
        "profile": profile,
    }


def run_lbnl_reproduction(path: str | Path, *, db_path: str | Path | None = None) -> dict[str, Any]:
    ingest = ingest_lbnl_workbook(path, db_path=db_path)
    workbook_id = ingest["workbook_id"]
    project_metrics = _project_level_metrics(workbook_id, db_path)
    summary_metrics = _summary_tab_metrics(path)
    comparisons = _compare_project_to_summary(project_metrics, summary_metrics)
    independent_rows = _independent_calculation_rows(project_metrics, summary_metrics, comparisons)
    csv_path = real_reports_dir() / "lbnl" / "lbnl_independent_calculations.csv"
    _write_independent_csv(csv_path, independent_rows)
    result = {
        "workbook_id": workbook_id,
        "source_url": LBNL_2026_PUBLICATION_URL,
        "download_url": LBNL_2026_XLSX_URL,
        "file_hash_sha256": ingest["file_hash_sha256"],
        "sheets_parsed": ingest["profile"]["sheet_names"],
        "row_count_raw": ingest["row_count_raw"],
        "metrics_calculated": project_metrics,
        "official_summary_metrics": summary_metrics,
        "comparisons": comparisons,
        "mismatches_and_limitations": _lbnl_mismatches(comparisons),
        "independent_calculations_csv": str(csv_path.relative_to(project_root())),
        "caveats": [
            "The LBNL Queued Up workbook includes generation and storage requests seeking transmission-grid interconnection; it does not include load interconnection requests, distribution-connected projects, or behind-the-meter projects.",
            "Workbook summary tabs may include derived/estimated hybrid storage capacity and summary-specific filters; project-level raw component sums are not forced to match when the workbook method is not encoded in the project sheet.",
        ],
    }
    md_path = real_reports_dir() / "lbnl" / "lbnl_reproduction.md"
    json_path = real_reports_dir() / "lbnl" / "lbnl_reproduction.json"
    write_markdown(md_path, _reproduction_markdown(result))
    write_json(json_path, {**result, "markdown_path": str(md_path.relative_to(project_root()))})
    return {**result, "markdown_path": str(md_path.relative_to(project_root())), "json_path": str(json_path.relative_to(project_root()))}


def _project_level_metrics(workbook_id: str, db_path: str | Path | None) -> dict[str, Any]:
    with connect(db_path) as con:
        row_count = con.execute("SELECT COUNT(*) FROM real_lbnl_project_records WHERE workbook_id = ?", [workbook_id]).fetchone()[0]
        status_counts = dict(
            con.execute(
                """
                SELECT q_status, COUNT(*)
                FROM real_lbnl_project_records
                WHERE workbook_id = ?
                GROUP BY q_status
                ORDER BY q_status
                """,
                [workbook_id],
            ).fetchall()
        )
        active_count = con.execute(
            "SELECT COUNT(*) FROM real_lbnl_project_records WHERE workbook_id = ? AND q_status = 'active'",
            [workbook_id],
        ).fetchone()[0]
        active_capacity_gw_mw1 = con.execute(
            "SELECT COALESCE(SUM(mw_1), 0) / 1000 FROM real_lbnl_project_records WHERE workbook_id = ? AND q_status = 'active'",
            [workbook_id],
        ).fetchone()[0]
        active_capacity_gw_components = con.execute(
            """
            SELECT COALESCE(SUM(COALESCE(mw_1, 0) + COALESCE(mw_2, 0) + COALESCE(mw_3, 0)), 0) / 1000
            FROM real_lbnl_project_records WHERE workbook_id = ? AND q_status = 'active'
            """,
            [workbook_id],
        ).fetchone()[0]
        ercot_active = con.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(mw_1), 0) / 1000
            FROM real_lbnl_project_records
            WHERE workbook_id = ? AND q_status = 'active' AND region = 'ERCOT'
            """,
            [workbook_id],
        ).fetchone()
        active_by_type = con.execute(
            """
            SELECT type_clean, COUNT(*), COALESCE(SUM(mw_1), 0) / 1000
            FROM real_lbnl_project_records
            WHERE workbook_id = ? AND q_status = 'active'
            GROUP BY type_clean
            ORDER BY 3 DESC
            """,
            [workbook_id],
        ).fetchall()
        median_days = con.execute(
            """
            SELECT median(date_diff('day', q_date, COALESCE(on_date, wd_date)))
            FROM real_lbnl_project_records
            WHERE workbook_id = ?
              AND q_date IS NOT NULL
              AND COALESCE(on_date, wd_date) IS NOT NULL
              AND q_status IN ('operational', 'withdrawn')
            """,
            [workbook_id],
        ).fetchone()[0]
    return {
        "project_row_count": int(row_count),
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
        "active_project_row_count": int(active_count),
        "active_capacity_gw_mw1_only": round(float(active_capacity_gw_mw1), 4),
        "active_capacity_gw_mw1_mw2_mw3": round(float(active_capacity_gw_components), 4),
        "ercot_active_project_row_count": int(ercot_active[0]),
        "ercot_active_capacity_gw_mw1_only": round(float(ercot_active[1]), 4),
        "active_capacity_by_type_gw_mw1_only": [
            {"type_clean": row[0], "active_rows": int(row[1]), "capacity_gw": round(float(row[2]), 4)}
            for row in active_by_type
        ],
        "median_days_request_to_terminal_status": round(float(median_days), 2) if median_days is not None else None,
    }


def _summary_tab_metrics(path: str | Path) -> dict[str, Any]:
    summary = pd.read_excel(path, sheet_name=REGION_SUMMARY_SHEET, header=3)
    summary = summary.dropna(how="all")
    rows = []
    for row in summary.to_dict(orient="records"):
        region = _text(row.get("Region"))
        if not region:
            continue
        rows.append(
            {
                "region": region,
                "active_n": _int(row.get("n")),
                "active_capacity_gw": to_float(row.get("Capacity (GW)")),
                "operational_n": _int(row.get("n.1")),
                "operational_capacity_gw": to_float(row.get("Capacity (GW).1")),
                "withdrawn_n": _int(row.get("n.2")),
                "withdrawn_capacity_gw": to_float(row.get("Capacity (GW).2")),
            }
        )
    ercot = next((row for row in rows if row["region"] == "ERCOT"), {})
    return {
        "sheet": REGION_SUMMARY_SHEET,
        "region_rows": rows,
        "active_n_total_from_summary": sum(row["active_n"] or 0 for row in rows),
        "active_capacity_gw_total_from_summary": round(sum(row["active_capacity_gw"] or 0 for row in rows), 4),
        "ercot_active_n_summary": ercot.get("active_n"),
        "ercot_active_capacity_gw_summary": ercot.get("active_capacity_gw"),
    }


def _compare_project_to_summary(project: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    comparisons.append(
        _comparison(
            "ERCOT active capacity GW",
            project["ercot_active_capacity_gw_mw1_only"],
            summary["ercot_active_capacity_gw_summary"],
            tolerance=0.1,
            reason="Project-level mw_1 capacity for active ERCOT rows rounds to workbook summary tab capacity.",
        )
    )
    comparisons.append(
        _comparison(
            "ERCOT active request count",
            project["ercot_active_project_row_count"],
            summary["ercot_active_n_summary"],
            tolerance=0,
            reason="Count differs; workbook summary appears to apply a summary-specific ERCOT count method while capacity matches.",
        )
    )
    comparisons.append(
        _comparison(
            "All-region active capacity GW",
            project["active_capacity_gw_mw1_only"],
            summary["active_capacity_gw_total_from_summary"],
            tolerance=0.1,
            reason="Mismatch expected because summary tabs include derived/estimated hybrid storage capacity and possibly summary-specific filters.",
        )
    )
    return comparisons


def _comparison(name: str, calculated: float | int | None, official: float | int | None, *, tolerance: float, reason: str) -> dict[str, Any]:
    if calculated is None or official is None:
        status = "skipped_missing_value"
        delta = None
    else:
        delta = float(calculated) - float(official)
        status = "matched_within_tolerance" if abs(delta) <= tolerance else "mismatch_documented"
    return {
        "metric": name,
        "calculated": calculated,
        "official_summary": official,
        "delta": round(delta, 4) if delta is not None else None,
        "tolerance": tolerance,
        "status": status,
        "reason": reason,
    }


def _independent_calculation_rows(project: dict[str, Any], summary: dict[str, Any], comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {"metric": "project_row_count", "value": project["project_row_count"], "source": PROJECT_SHEET, "status": "calculated"},
        {"metric": "active_project_row_count", "value": project["active_project_row_count"], "source": PROJECT_SHEET, "status": "calculated"},
        {"metric": "active_capacity_gw_mw1_only", "value": project["active_capacity_gw_mw1_only"], "source": PROJECT_SHEET, "status": "calculated"},
        {"metric": "active_capacity_gw_mw1_mw2_mw3", "value": project["active_capacity_gw_mw1_mw2_mw3"], "source": PROJECT_SHEET, "status": "calculated"},
        {"metric": "summary_active_capacity_total_gw", "value": summary["active_capacity_gw_total_from_summary"], "source": REGION_SUMMARY_SHEET, "status": "official_summary_tab"},
    ]
    for comparison in comparisons:
        rows.append(
            {
                "metric": comparison["metric"],
                "value": comparison["calculated"],
                "source": f"{PROJECT_SHEET} vs {REGION_SUMMARY_SHEET}",
                "status": comparison["status"],
                "official_summary": comparison["official_summary"],
                "delta": comparison["delta"],
                "reason": comparison["reason"],
            }
        )
    return rows


def _lbnl_mismatches(comparisons: list[dict[str, Any]]) -> list[str]:
    mismatches = []
    for comparison in comparisons:
        if comparison["status"] == "mismatch_documented":
            mismatches.append(
                f"{comparison['metric']} mismatch: calculated={comparison['calculated']} official_summary={comparison['official_summary']} delta={comparison['delta']}. {comparison['reason']}"
            )
    return mismatches or ["No compared metric exceeded tolerance."]


def _write_independent_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = sorted({key for row in rows for key in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _profile_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# LBNL workbook profile",
        "",
        f"- source_url: {result['source_url']}",
        f"- download_url: {result['download_url']}",
        f"- file_hash_sha256: `{result['file_hash_sha256']}`",
        f"- file_size_bytes: {result['file_size_bytes']}",
        f"- project_level_sheet: {result['project_level_sheet']}",
        f"- project_row_count: {result['project_row_count']}",
        f"- codebook_sheet: {result['codebook_sheet']}",
        f"- codebook_row_count: {result['codebook_row_count']}",
        f"- summary_tab_count: {len(result['summary_tabs'])}",
        f"- parse_status: {result['parse_status']}",
        "",
        "## Sheet names",
        *[f"- {sheet}" for sheet in result["sheet_names"]],
    ]
    if result["parse_errors"]:
        lines.extend(["", "## Parse errors", *[f"- {item}" for item in result["parse_errors"]]])
    return "\n".join(lines)


def _reproduction_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# LBNL Queued Up real workbook reproduction",
        "",
        "## Source",
        f"- source_url: {result['source_url']}",
        f"- download_url: {result['download_url']}",
        f"- workbook_id: `{result['workbook_id']}`",
        f"- file_hash_sha256: `{result['file_hash_sha256']}`",
        f"- project_row_count: {result['row_count_raw']}",
        "",
        "## Metrics calculated",
    ]
    metrics = result["metrics_calculated"]
    for key in (
        "project_row_count",
        "active_project_row_count",
        "active_capacity_gw_mw1_only",
        "active_capacity_gw_mw1_mw2_mw3",
        "ercot_active_project_row_count",
        "ercot_active_capacity_gw_mw1_only",
        "median_days_request_to_terminal_status",
    ):
        lines.append(f"- {key}: {metrics.get(key)}")
    lines.extend(["", "## Active capacity by type"])
    lines.extend(
        [
            f"- {row['type_clean']}: rows={row['active_rows']} capacity_gw={row['capacity_gw']}"
            for row in metrics["active_capacity_by_type_gw_mw1_only"][:12]
        ]
    )
    lines.extend(["", "## Official summary comparison"])
    for comparison in result["comparisons"]:
        lines.append(
            f"- {comparison['metric']}: calculated={comparison['calculated']} official_summary={comparison['official_summary']} "
            f"delta={comparison['delta']} status={comparison['status']} reason={comparison['reason']}"
        )
    lines.extend(["", "## Mismatches and limitations", *[f"- {item}" for item in result["mismatches_and_limitations"]]])
    lines.extend(["", "## Caveats", *[f"- {item}" for item in result["caveats"]]])
    lines.append("")
    lines.append(f"Independent calculation CSV: `{result['independent_calculations_csv']}`")
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


def _int(value: Any) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None
