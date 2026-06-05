from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import project_root
from app.services.utils import file_sha256, stable_json, utcnow


ERCOT_GIS_PRODUCT_URL = "https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER"
ERCOT_DOC_LIST_URL = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=15933"
ERCOT_DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId="
LBNL_QUEUED_UP_URL = "https://emp.lbl.gov/queues"
LBNL_2026_PUBLICATION_URL = "https://eta.lbl.gov/publications/us-interconnection-queue-data-0"
LBNL_2026_XLSX_URL = "https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx"

PARSER_VERSION = "real_validation_v1"


def real_raw_dir() -> Path:
    return project_root() / "data" / "raw" / "real"


def real_reports_dir() -> Path:
    return project_root() / "reports" / "real_data"


def source_manifest_path() -> Path:
    return real_reports_dir() / "source_manifest.json"


def ensure_real_dirs() -> None:
    for path in (
        real_raw_dir() / "ercot" / "gis",
        real_raw_dir() / "lbnl",
        project_root() / "data" / "processed" / "real",
        real_reports_dir(),
        real_reports_dir() / "ercot",
        real_reports_dir() / "lbnl",
        real_reports_dir() / "entity_resolution_audit",
        real_reports_dir() / "manual_review",
        project_root() / "evals" / "real_cases",
        project_root() / "docs" / "demo_outputs" / "real_data",
    ):
        path.mkdir(parents=True, exist_ok=True)


def clean_payload(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        key_text = str(key).strip() if key is not None else "unnamed"
        if key_text.lower().startswith("unnamed:"):
            key_text = key_text.replace("Unnamed:", "unnamed_")
        if _is_missing(value):
            cleaned[key_text] = None
        elif hasattr(value, "isoformat"):
            cleaned[key_text] = value.isoformat()
        else:
            cleaned[key_text] = value
    return cleaned


def json_safe(value: Any) -> Any:
    return json.loads(stable_json(value))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_markdown(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def load_source_manifest() -> list[dict[str, Any]]:
    path = source_manifest_path()
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
        return payload["sources"]
    if isinstance(payload, list):
        return payload
    return []


def upsert_manifest_entry(entry: dict[str, Any]) -> dict[str, Any]:
    ensure_real_dirs()
    sources = load_source_manifest()
    key = (
        entry.get("source_name"),
        entry.get("file_hash_sha256"),
        entry.get("snapshot_date"),
        entry.get("local_path"),
    )
    filtered = [
        item
        for item in sources
        if (
            item.get("source_name"),
            item.get("file_hash_sha256"),
            item.get("snapshot_date"),
            item.get("local_path"),
        )
        != key
    ]
    filtered.append(entry)
    payload = {
        "manifest_version": PARSER_VERSION,
        "generated_at": utcnow().isoformat(),
        "sources": sorted(
            filtered,
            key=lambda item: (
                str(item.get("source_name") or ""),
                str(item.get("snapshot_date") or ""),
                str(item.get("local_path") or ""),
            ),
        ),
    }
    write_json(source_manifest_path(), payload)
    return payload


def file_manifest_entry(
    *,
    source_name: str,
    source_url: str,
    local_path: str | Path,
    snapshot_date: str | None,
    row_count_raw: int,
    sheet_names: list[str],
    parse_status: str,
    parse_errors: list[str] | None = None,
    retrieved_at: str | None = None,
    user_provided_at: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    display_path = Path(local_path)
    path = display_path if display_path.exists() else project_root() / display_path
    return {
        "source_name": source_name,
        "source_url": source_url,
        "local_path": str(display_path),
        "file_hash_sha256": file_sha256(path),
        "file_size_bytes": path.stat().st_size,
        "retrieved_at": retrieved_at,
        "user_provided_at": user_provided_at,
        "snapshot_date": snapshot_date,
        "row_count_raw": int(row_count_raw),
        "sheet_names": sheet_names,
        "parser_version": PARSER_VERSION,
        "parse_status": parse_status,
        "parse_errors": parse_errors or [],
        "notes": notes,
    }


def workbook_sheet_names(path: str | Path) -> list[str]:
    return list(pd.ExcelFile(path).sheet_names)


def find_header_row(path: str | Path, sheet_name: str, required_labels: list[str], *, max_scan_rows: int = 80) -> int:
    frame = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_scan_rows)
    required = {_clean_label(item) for item in required_labels}
    for idx, row in frame.iterrows():
        row_labels = {_clean_label(value) for value in row.tolist() if not _is_missing(value)}
        if required.issubset(row_labels):
            return int(idx)
    raise ValueError(f"Could not find header row in sheet {sheet_name!r}; required labels={required_labels}")


def read_table_after_header(path: str | Path, sheet_name: str, required_labels: list[str]) -> tuple[pd.DataFrame, int]:
    header_row = find_header_row(path, sheet_name, required_labels)
    frame = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    frame = frame.dropna(how="all")
    return frame, header_row


def month_label(snapshot_date: str | date) -> str:
    if isinstance(snapshot_date, date):
        return snapshot_date.strftime("%Y_%m")
    parsed = pd.to_datetime(snapshot_date, errors="coerce")
    if pd.isna(parsed):
        return str(snapshot_date).replace("-", "_")[:7]
    return parsed.strftime("%Y_%m")


def parse_date(value: Any) -> date | None:
    if _is_missing(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def to_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
    if math.isnan(number):
        return None
    return number


def clean_text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def first_present(row: dict[str, Any], *keys: str) -> Any:
    lookup = {_clean_label(key): key for key in row.keys()}
    for key in keys:
        actual = lookup.get(_clean_label(key))
        if actual is not None and not _is_missing(row.get(actual)):
            return row.get(actual)
    return None


def local_path_for_report(path: str | Path) -> str:
    path_obj = Path(path)
    try:
        return str(path_obj.relative_to(project_root()))
    except ValueError:
        return str(path_obj)


def _clean_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null", "nat"}
