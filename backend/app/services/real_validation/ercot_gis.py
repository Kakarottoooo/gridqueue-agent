from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.config import project_root
from app.db import connect, init_database
from app.services.citations import ensure_reference_sources, insert_record_citation
from app.services.diffing.service import diff_snapshots
from app.services.entity_resolution.resolver import (
    AMBIGUITY_DELTA,
    POSSIBLE_MATCH,
    compare_records,
)
from app.services.ingestion.pipeline import _insert_normalized_record
from app.services.normalization.normalizer import normalize_record
from app.services.real_validation.common import (
    ERCOT_DOC_LIST_URL,
    ERCOT_DOWNLOAD_URL,
    ERCOT_GIS_PRODUCT_URL,
    PARSER_VERSION,
    clean_payload,
    clean_text,
    file_manifest_entry,
    first_present,
    json_safe,
    local_path_for_report,
    month_label,
    parse_date,
    read_table_after_header,
    real_raw_dir,
    real_reports_dir,
    to_float,
    upsert_manifest_entry,
    workbook_sheet_names,
    write_json,
    write_markdown,
)
from app.services.utils import file_sha256, new_id, stable_json, utcnow
from app.services.watcher.events import change_event_select_sql, row_to_change_event
from app.services.watcher.queue_adapter import adapt_queue_diff


ERCOT_REQUIRED_CAVEAT = (
    "This digest is based on public ERCOT GIS generation-resource interconnection data. It does not represent a "
    "complete large-load or data-center interconnection queue and does not replace formal interconnection studies, "
    "power-flow studies, or project-specific diligence."
)

PRIMARY_PROJECT_SHEETS = ("Project Details - Large Gen", "Project Details - Small Gen")
SIGNAL_SHEETS = ("Commissioning Update", "Inactive Projects", "Cancellation Update")


def download_latest_ercot_gis_reports(*, count: int = 2) -> dict[str, Any]:
    docs = discover_ercot_gis_documents()
    selected = [doc for doc in docs if _is_gis_report(doc)][:count]
    if len(selected) < count:
        return {
            "status": "manual_required",
            "message": "Automatic ERCOT GIS discovery did not return enough consecutive GIS reports.",
            "instructions": manual_ercot_download_instructions(),
            "documents_found": len(docs),
        }
    output_dir = real_raw_dir() / "ercot" / "gis"
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "GridQueue-Agent/real-validation"}) as client:
        for doc in selected:
            snapshot_date = _snapshot_date_from_friendly_name(doc["FriendlyName"])
            if not snapshot_date:
                continue
            output_path = output_dir / f"ERCOT_GIS_{month_label(snapshot_date)}.xlsx"
            if not output_path.exists():
                response = client.get(f"{ERCOT_DOWNLOAD_URL}{doc['DocID']}")
                response.raise_for_status()
                if not response.content.startswith(b"PK"):
                    raise ValueError(f"ERCOT download for {doc['FriendlyName']} did not return an XLSX file.")
                output_path.write_bytes(response.content)
            downloaded.append(
                {
                    "friendly_name": doc["FriendlyName"],
                    "doc_id": doc["DocID"],
                    "publish_date": doc.get("PublishDate"),
                    "snapshot_date": snapshot_date,
                    "local_path": str(output_path),
                    "file_hash_sha256": file_sha256(output_path),
                    "file_size_bytes": output_path.stat().st_size,
                    "source_url": f"{ERCOT_DOWNLOAD_URL}{doc['DocID']}",
                }
            )
    downloaded.sort(key=lambda item: item["snapshot_date"])
    return {"status": "downloaded", "files": downloaded}


def discover_ercot_gis_documents() -> list[dict[str, Any]]:
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "GridQueue-Agent/real-validation"}) as client:
        response = client.get(ERCOT_DOC_LIST_URL)
        response.raise_for_status()
        payload = response.json()
    documents = payload.get("ListDocsByRptTypeRes", {}).get("DocumentList", [])
    parsed = [item.get("Document", {}) for item in documents if item.get("Document")]
    parsed.sort(key=lambda item: item.get("PublishDate", ""), reverse=True)
    return parsed


def manual_ercot_download_instructions() -> list[str]:
    return [
        f"Go to the ERCOT GIS Report page: {ERCOT_GIS_PRODUCT_URL}",
        "Download two consecutive monthly GIS_Report_*.xlsx files, not the Co-located Battery Identification Report.",
        "Place them under data/raw/real/ercot/gis/ as ERCOT_GIS_YYYY_MM.xlsx.",
        "Run: python scripts/run_real_ercot_pair.py --from-file data/raw/real/ercot/gis/ERCOT_GIS_YYYY_MM.xlsx --from-snapshot-date YYYY-MM-DD --to-file data/raw/real/ercot/gis/ERCOT_GIS_YYYY_MM_PLUS_1.xlsx --to-snapshot-date YYYY-MM-DD",
    ]


def profile_ercot_gis_workbook(path: str | Path, *, snapshot_date: str | None = None) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"ERCOT GIS workbook not found: {file_path}")
    sheets = workbook_sheet_names(file_path)
    sheet_profiles = []
    parse_errors: list[str] = []
    for sheet in sheets:
        profile: dict[str, Any] = {"sheet_name": sheet, "candidate_data_sheet": False}
        try:
            raw_preview = pd.read_excel(file_path, sheet_name=sheet, header=None, nrows=80)
            profile["non_empty_preview_rows"] = int(raw_preview.dropna(how="all").shape[0])
            if sheet in PRIMARY_PROJECT_SHEETS:
                frame, header_row = read_table_after_header(file_path, sheet, ["INR", "Project Name"])
                profile.update(
                    {
                        "candidate_data_sheet": True,
                        "header_row": header_row,
                        "columns": [str(item) for item in frame.columns],
                        "row_count_with_inr": int(_rows_with_inr(frame).shape[0]),
                        "likely_fields": _ercot_likely_fields(frame),
                    }
                )
            elif sheet in SIGNAL_SHEETS:
                frame, header_row = read_table_after_header(file_path, sheet, ["INR", "Project Name"])
                profile.update(
                    {
                        "candidate_data_sheet": True,
                        "header_row": header_row,
                        "columns": [str(item) for item in frame.columns],
                        "row_count_with_inr": int(_rows_with_inr(frame).shape[0]),
                        "likely_fields": _ercot_likely_fields(frame),
                    }
                )
            else:
                profile["columns"] = []
        except Exception as exc:  # noqa: BLE001
            profile["parse_error"] = str(exc)
            parse_errors.append(f"{sheet}: {exc}")
        sheet_profiles.append(profile)

    parsed_rows = 0
    try:
        parsed_rows = len(parse_ercot_project_rows(file_path, snapshot_date=snapshot_date or _snapshot_date_from_filename(file_path) or "unknown")["rows"])
    except Exception as exc:  # noqa: BLE001
        parse_errors.append(f"project row parse: {exc}")
    inferred_snapshot_date = snapshot_date or _snapshot_date_from_filename(file_path)
    result = {
        "source_name": "ERCOT GIS Report",
        "source_url": ERCOT_GIS_PRODUCT_URL,
        "local_path": str(file_path),
        "file_hash_sha256": file_sha256(file_path),
        "file_size_bytes": file_path.stat().st_size,
        "snapshot_date": inferred_snapshot_date,
        "sheet_names": sheets,
        "sheet_profiles": sheet_profiles,
        "row_count_raw": parsed_rows,
        "parser_version": PARSER_VERSION,
        "parse_status": "parsed" if parsed_rows and not parse_errors else ("parsed_with_warnings" if parsed_rows else "failed"),
        "parse_errors": parse_errors,
    }
    label = month_label(inferred_snapshot_date or file_path.stem)
    report_json = real_reports_dir() / "ercot" / f"profile_{label}.json"
    report_md = real_reports_dir() / "ercot" / f"profile_{label}.md"
    write_json(report_json, result)
    write_markdown(report_md, _profile_markdown(result))
    return {**result, "profile_json_path": str(report_json.relative_to(project_root())), "profile_markdown_path": str(report_md.relative_to(project_root()))}


def parse_ercot_project_rows(path: str | Path, *, snapshot_date: str) -> dict[str, Any]:
    file_path = Path(path)
    by_inr: dict[str, dict[str, Any]] = {}
    source_row_count = 0
    parse_errors: list[str] = []
    for sheet in PRIMARY_PROJECT_SHEETS:
        try:
            frame, _ = read_table_after_header(file_path, sheet, ["INR", "Project Name"])
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(f"{sheet}: {exc}")
            continue
        for source_index, row in _rows_with_inr(frame).iterrows():
            raw = clean_payload(row.to_dict())
            inr = clean_text(first_present(raw, "INR"))
            if not inr:
                continue
            source_row_count += 1
            payload = _ercot_primary_payload(raw, sheet, int(source_index) + 2, snapshot_date)
            by_inr.setdefault(inr, payload)

    for sheet in SIGNAL_SHEETS:
        try:
            frame, _ = read_table_after_header(file_path, sheet, ["INR", "Project Name"])
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(f"{sheet}: {exc}")
            continue
        for source_index, row in _rows_with_inr(frame).iterrows():
            raw = clean_payload(row.to_dict())
            inr = clean_text(first_present(raw, "INR"))
            if not inr:
                continue
            source_row_count += 1
            signal_payload = _ercot_signal_payload(raw, sheet, int(source_index) + 2, snapshot_date)
            if not signal_payload:
                continue
            existing = by_inr.get(inr)
            if existing:
                by_inr[inr] = _merge_status_signal(existing, signal_payload)
            else:
                by_inr[inr] = signal_payload

    rows = list(by_inr.values())
    rows.sort(key=lambda item: (str(item.get("Queue ID") or ""), str(item.get("Project Name") or "")))
    missing_required = [
        row.get("Queue ID") or row.get("Project Name")
        for row in rows
        if not row.get("Queue ID") or not row.get("Project Name")
    ]
    if missing_required:
        parse_errors.append(f"{len(missing_required)} parsed rows are missing queue ID or project name.")
    return {"rows": rows, "source_row_count": source_row_count, "parse_errors": parse_errors}


def ingest_ercot_gis_workbook(
    path: str | Path,
    *,
    snapshot_date: str,
    db_path: str | Path | None = None,
    retrieved_at: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    ensure_reference_sources(db_path)
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"ERCOT GIS workbook not found: {file_path}")
    parsed = parse_ercot_project_rows(file_path, snapshot_date=snapshot_date)
    if not parsed["rows"]:
        raise ValueError(f"No ERCOT project rows parsed from {file_path}; run profile_real_ercot_gis.py for diagnostics.")
    file_hash = file_sha256(file_path)
    label = month_label(snapshot_date)
    source_id = f"src_real_ercot_gis_{label}_{file_hash[:8]}"
    snapshot_id = f"snap_real_ercot_gis_{label}_{file_hash[:8]}"
    now = utcnow()
    with connect(db_path) as con:
        _delete_snapshot_payload(con, snapshot_id)
        con.execute(
            """
            INSERT OR REPLACE INTO sources
            (source_id, source_name, source_url, source_type, retrieved_at, publication_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                source_id,
                "ERCOT GIS Report",
                source_url or ERCOT_GIS_PRODUCT_URL,
                "real_ercot_gis_xlsx",
                now,
                snapshot_date,
                f"Real ERCOT GIS workbook {file_path.name}; parser={PARSER_VERSION}.",
            ],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO snapshots
            (snapshot_id, market, source_id, snapshot_date, file_hash, row_count, ingestion_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot_id,
                "ERCOT",
                source_id,
                snapshot_date,
                file_hash,
                len(parsed["rows"]),
                "real_ercot_gis",
                now,
            ],
        )
        inserted = 0
        for row_number, payload in enumerate(parsed["rows"], start=1):
            raw_record_id = new_id("raw")
            con.execute(
                """
                INSERT INTO raw_project_records
                (raw_record_id, snapshot_id, raw_payload_json, row_number, source_sheet, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    raw_record_id,
                    snapshot_id,
                    stable_json(payload),
                    row_number,
                    payload.get("Source Sheet"),
                    now,
                ],
            )
            record = normalize_record(payload, raw_record_id, snapshot_id, "ERCOT")
            flags = list(record["data_quality_flags_json"])
            if payload.get("ERCOT Data Quality Flags"):
                flags.extend(payload["ERCOT Data Quality Flags"])
            record["data_quality_flags_json"] = sorted(set(flags))
            _insert_normalized_record(con, record)
            insert_record_citation(
                con,
                source_id=source_id,
                snapshot_id=snapshot_id,
                record_id=record["record_id"],
                citation_label=f"ERCOT GIS {snapshot_date} row {row_number}",
                citation_text=(
                    f"ERCOT GIS real workbook {file_path.name}, sheet={payload.get('Source Sheet')}, "
                    f"queue_id={record['queue_id'] or 'missing'}, source_hash={file_hash}."
                ),
                source_url=source_url or ERCOT_GIS_PRODUCT_URL,
            )
            inserted += 1

    manifest_entry = file_manifest_entry(
        source_name="ERCOT GIS Report",
        source_url=source_url or ERCOT_GIS_PRODUCT_URL,
        local_path=local_path_for_report(file_path),
        snapshot_date=snapshot_date,
        row_count_raw=int(parsed["source_row_count"]),
        sheet_names=workbook_sheet_names(file_path),
        parse_status="parsed" if not parsed["parse_errors"] else "parsed_with_warnings",
        parse_errors=parsed["parse_errors"],
        retrieved_at=retrieved_at or now.isoformat(),
        notes=f"Normalized {inserted} deduplicated ERCOT project records from real GIS workbook.",
    )
    upsert_manifest_entry(manifest_entry)
    return {
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "file_hash_sha256": file_hash,
        "row_count_raw": int(parsed["source_row_count"]),
        "normalized_row_count": inserted,
        "snapshot_date": snapshot_date,
        "parse_errors": parsed["parse_errors"],
    }


def run_real_ercot_pair(
    *,
    from_file: str | Path,
    from_snapshot_date: str,
    to_file: str | Path,
    to_snapshot_date: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    profile_from = profile_ercot_gis_workbook(from_file, snapshot_date=from_snapshot_date)
    profile_to = profile_ercot_gis_workbook(to_file, snapshot_date=to_snapshot_date)
    ingest_from = ingest_ercot_gis_workbook(from_file, snapshot_date=from_snapshot_date, db_path=db_path)
    ingest_to = ingest_ercot_gis_workbook(to_file, snapshot_date=to_snapshot_date, db_path=db_path)
    resolver = resolve_real_ercot_snapshot_pair(
        from_snapshot_id=ingest_from["snapshot_id"],
        to_snapshot_id=ingest_to["snapshot_id"],
        db_path=db_path,
    )
    diff = diff_snapshots("ERCOT", ingest_from["snapshot_id"], ingest_to["snapshot_id"], db_path)
    adapter = adapt_queue_diff(
        market="ERCOT",
        from_snapshot_id=ingest_from["snapshot_id"],
        to_snapshot_id=ingest_to["snapshot_id"],
        db_path=db_path,
    )
    from app.services.real_validation.entity_resolution_audit import build_ercot_entity_resolution_audit

    audit = build_ercot_entity_resolution_audit(
        from_snapshot_id=ingest_from["snapshot_id"],
        to_snapshot_id=ingest_to["snapshot_id"],
        db_path=db_path,
    )
    digest = generate_ercot_real_digest(
        from_snapshot_id=ingest_from["snapshot_id"],
        to_snapshot_id=ingest_to["snapshot_id"],
        db_path=db_path,
    )
    events_path = _write_diff_events_csv(
        from_snapshot_id=ingest_from["snapshot_id"],
        to_snapshot_id=ingest_to["snapshot_id"],
        db_path=db_path,
    )
    summary = {
        "from_snapshot_id": ingest_from["snapshot_id"],
        "to_snapshot_id": ingest_to["snapshot_id"],
        "from_snapshot_date": from_snapshot_date,
        "to_snapshot_date": to_snapshot_date,
        "from_file_hash_sha256": ingest_from["file_hash_sha256"],
        "to_file_hash_sha256": ingest_to["file_hash_sha256"],
        "from_row_count_raw": ingest_from["row_count_raw"],
        "to_row_count_raw": ingest_to["row_count_raw"],
        "from_normalized_row_count": ingest_from["normalized_row_count"],
        "to_normalized_row_count": ingest_to["normalized_row_count"],
        "resolver": resolver,
        "diff": {key: value for key, value in diff.items() if key != "events"},
        "adapter": {key: value for key, value in adapter.items() if key != "change_events"},
        "audit": audit,
        "digest_path": digest["markdown_path"],
        "events_csv_path": events_path,
        "profiles": [profile_from["profile_markdown_path"], profile_to["profile_markdown_path"]],
    }
    label = f"{month_label(from_snapshot_date)}_to_{month_label(to_snapshot_date)}"
    summary_path = real_reports_dir() / "ercot" / f"real_monthly_diff_summary_{label}.json"
    write_json(summary_path, summary)
    summary["summary_path"] = str(summary_path.relative_to(project_root()))
    return summary


def resolve_real_ercot_snapshot_pair(
    *,
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        con.execute("DELETE FROM project_entity_links WHERE snapshot_id IN (?, ?)", [from_snapshot_id, to_snapshot_id])
        con.execute(
            """
            DELETE FROM project_entities
            WHERE market = 'ERCOT' AND (first_seen_snapshot_id IN (?, ?) OR latest_seen_snapshot_id IN (?, ?))
            """,
            [from_snapshot_id, to_snapshot_id, from_snapshot_id, to_snapshot_id],
        )
        before_records = _records_for_snapshot(con, from_snapshot_id)
        after_records = _records_for_snapshot(con, to_snapshot_id)
        before_candidates = []
        linked = 0
        ambiguous = 0
        new_entities = 0
        now = utcnow()
        for record in before_records:
            entity_id = _create_real_entity(con, record, from_snapshot_id, now)
            new_entities += 1
            _create_real_link(
                con,
                entity_id=entity_id,
                record=record,
                score=1.0,
                method="first_real_snapshot_seed",
                features={"reason": "First real ERCOT snapshot in selected validation pair."},
                is_ambiguous=False,
                created_at=now,
            )
            before_candidates.append({"entity_id": entity_id, "record": record})
            linked += 1

        used_entities: set[str] = set()
        for record in after_records:
            ranked = _rank_real_candidates(record, before_candidates)
            top = ranked[0] if ranked else None
            second = ranked[1] if len(ranked) > 1 else None
            is_ambiguous = bool(
                top
                and top["match"].score >= POSSIBLE_MATCH
                and second
                and top["match"].score - second["match"].score <= AMBIGUITY_DELTA
            )
            if top and top["match"].score >= POSSIBLE_MATCH and not is_ambiguous and top["entity_id"] not in used_entities:
                entity_id = top["entity_id"]
                used_entities.add(entity_id)
                _update_real_entity(con, entity_id, record, to_snapshot_id, now)
                _create_real_link(
                    con,
                    entity_id=entity_id,
                    record=record,
                    score=top["match"].score,
                    method=top["match"].method,
                    features={
                        **top["match"].features,
                        "candidate_record_id": top["record"]["record_id"],
                        "candidate_entity_id": entity_id,
                    },
                    is_ambiguous=False,
                    created_at=now,
                )
                linked += 1
                continue

            entity_id = _create_real_entity(con, record, to_snapshot_id, now)
            new_entities += 1
            if is_ambiguous and top:
                ambiguous += 1
                features = {
                    "reason": "Top candidate scores are too close; real validation pair did not force the match.",
                    "candidate_entities": [
                        {
                            "entity_id": item["entity_id"],
                            "record_id": item["record"]["record_id"],
                            "score": item["match"].score,
                            "method": item["match"].method,
                            "features": item["match"].features,
                        }
                        for item in ranked[:3]
                    ],
                }
                _create_real_link(
                    con,
                    entity_id=entity_id,
                    record=record,
                    score=top["match"].score,
                    method="ambiguous_possible_match",
                    features=features,
                    is_ambiguous=True,
                    created_at=now,
                )
            else:
                _create_real_link(
                    con,
                    entity_id=entity_id,
                    record=record,
                    score=top["match"].score if top else 0.0,
                    method="new_entity",
                    features={
                        "reason": "No prior real ERCOT candidate reached the possible-match threshold.",
                        "best_candidate": _candidate_summary(top) if top else None,
                    },
                    is_ambiguous=False,
                    created_at=now,
                )
            linked += 1
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "before_records": len(before_records),
        "after_records": len(after_records),
        "linked_records": linked,
        "ambiguous_links": ambiguous,
        "entities_created": new_entities,
    }


def generate_ercot_real_digest(
    *,
    from_snapshot_id: str,
    to_snapshot_id: str,
    top_n: int = 20,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    events = _change_events_for_pair(from_snapshot_id, to_snapshot_id, db_path)
    source = _source_context(from_snapshot_id, to_snapshot_id, db_path)
    hard = [event for event in events if event["is_hard_alert"] and not event["is_ambiguous"]]
    hard.sort(key=lambda item: (-float(item["materiality_score"]), item["event_type"], item.get("entity_or_provision") or ""))
    suppressed = [event for event in events if event["is_ambiguous"] or not event["is_hard_alert"]]
    suppressed.sort(key=lambda item: (-float(item["materiality_score"]), item["event_type"]))
    top_events = hard[:top_n]
    event_lines = [_digest_event_line(event, source) for event in events]
    categories = {
        "top_real_queue_changes": [_digest_event_line(event, source) for event in top_events],
        "new_projects": [_digest_event_line(event, source) for event in events if event["event_type"] == "new_project"],
        "withdrawn_removed_completed_projects": [
            _digest_event_line(event, source)
            for event in events
            if event["event_type"] in {"withdrawn_project", "removed_project", "completed_project"}
        ],
        "status_changes": [_digest_event_line(event, source) for event in events if event["event_type"] == "status_changed"],
        "capacity_changes": [_digest_event_line(event, source) for event in events if event["event_type"] == "capacity_changed"],
        "cod_moves": [
            _digest_event_line(event, source)
            for event in events
            if event["event_type"] in {"target_cod_delayed", "target_cod_accelerated"}
        ],
        "fuel_classification_changes": [_digest_event_line(event, source) for event in events if event["event_type"] == "fuel_type_changed"],
        "ambiguous_or_suppressed_noise": [_digest_event_line(event, source) for event in suppressed],
    }
    result = {
        "title": f"Real ERCOT GIS Monthly Digest: {source['from_snapshot_date'][:7]} to {source['to_snapshot_date'][:7]}",
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "source_files": source,
        "executive_summary": [
            f"Parsed {source['from_row_count']} normalized rows from the earlier ERCOT GIS workbook and {source['to_row_count']} from the later workbook.",
            f"Detected {len(events)} queue events, including {len(hard)} hard alerts and {len(suppressed)} ambiguous or suppressed/noise events.",
            "Events are generation-resource GIS signals only; no data-center or large-load queue claims are made from this source.",
        ],
        "all_event_lines": event_lines,
        **categories,
        "data_quality_warnings": _data_quality_warnings(from_snapshot_id, to_snapshot_id, db_path),
        "reproducibility_trace": [
            "profile_real_ercot_gis.py identified workbook sheets, header rows, mapped columns, and row counts.",
            "ingest_real_ercot_gis.py preserved raw row JSON and normalized project records with source hash citations.",
            "resolve_real_ercot_snapshot_pair used deterministic GridQueue entity-resolution scoring for the selected real pair only.",
            "diff_snapshots generated queue events; watcher queue_adapter converted them to materiality-scored change_events.",
            "generate_ercot_real_digest wrote this markdown without LLM facts or fixture substitution.",
        ],
        "caveats": [
            ERCOT_REQUIRED_CAVEAT,
            "A removed_project event means a resolved entity is missing from the later snapshot; it is not labeled withdrawn unless ERCOT status/cancellation evidence supports that label.",
            "Ambiguous matches are listed separately and require human review before being used as hard alerts.",
        ],
    }
    markdown = _ercot_digest_markdown(result)
    label = f"{month_label(source['from_snapshot_date'])}_to_{month_label(source['to_snapshot_date'])}"
    digest_path = real_reports_dir() / "ercot" / f"real_monthly_digest_{label}.md"
    digest_json_path = real_reports_dir() / "ercot" / f"real_monthly_digest_{label}.json"
    write_markdown(digest_path, markdown)
    write_json(digest_json_path, {**result, "markdown_path": str(digest_path.relative_to(project_root()))})
    return {
        **result,
        "markdown": markdown,
        "markdown_path": str(digest_path.relative_to(project_root())),
        "json_path": str(digest_json_path.relative_to(project_root())),
        "hard_alert_count": len(hard),
        "suppressed_event_count": len(suppressed),
        "event_count": len(events),
    }


def _ercot_primary_payload(raw: dict[str, Any], sheet: str, row_number: int, snapshot_date: str) -> dict[str, Any]:
    fuel = _ercot_fuel_label(first_present(raw, "Fuel"), first_present(raw, "Technology"))
    payload = {
        **raw,
        "Queue ID": clean_text(first_present(raw, "INR")),
        "Project Name": clean_text(first_present(raw, "Project Name")),
        "Interconnecting Entity": clean_text(first_present(raw, "Interconnecting Entity")),
        "POI Location": clean_text(first_present(raw, "POI Location")),
        "County": clean_text(first_present(raw, "County")),
        "State": "TX",
        "Fuel Type": fuel,
        "Capacity (MW)": to_float(first_present(raw, "Capacity (MW)", "MW **")),
        "Status": "Active",
        "Target COD": parse_date(first_present(raw, "Projected COD")),
        "Interconnection Agreement Date": parse_date(first_present(raw, "IA Signed")),
        "Last Updated": snapshot_date,
        "GIM Study Phase": clean_text(first_present(raw, "GIM Study Phase")),
        "CDR Reporting Zone": clean_text(first_present(raw, "CDR Reporting Zone")),
        "Source Sheet": sheet,
        "Source Row Number": row_number,
        "ERCOT Data Quality Flags": [],
    }
    if not payload["Fuel Type"]:
        payload["ERCOT Data Quality Flags"].append("missing_fuel_type")
    if payload["Capacity (MW)"] is None:
        payload["ERCOT Data Quality Flags"].append("missing_capacity_mw")
    return payload


def _ercot_signal_payload(raw: dict[str, Any], sheet: str, row_number: int, snapshot_date: str) -> dict[str, Any] | None:
    inr = clean_text(first_present(raw, "INR"))
    project = clean_text(first_present(raw, "Project Name"))
    if not inr or not project:
        return None
    status = "Active"
    withdrawn_date = None
    actual_cod = None
    signal = sheet
    if sheet == "Cancellation Update":
        status = "Withdrawn"
        withdrawn_date = parse_date(first_present(raw, "Cancel Date"))
        signal = "developer_cancelled"
    elif sheet == "Inactive Projects":
        status = "Inactive"
        withdrawn_date = parse_date(first_present(raw, "Inactive Date"))
        signal = "inactive_project"
    elif sheet == "Commissioning Update":
        category = clean_text(first_present(raw, "Commissioning Category")) or ""
        if "commercial operation" not in category.lower():
            return None
        status = "Completed"
        actual_cod = parse_date(first_present(raw, "Approval Date *", "Approval Date"))
        signal = "commercial_operation_approved"
    return {
        **raw,
        "Queue ID": inr,
        "Project Name": project,
        "County": clean_text(first_present(raw, "County")),
        "State": "TX",
        "Fuel Type": _ercot_fuel_label(first_present(raw, "Fuel"), first_present(raw, "Technology")),
        "Capacity (MW)": to_float(first_present(raw, "Capacity (MW)", "MW **")),
        "Status": status,
        "Withdrawn Date": withdrawn_date,
        "Actual COD": actual_cod,
        "Last Updated": snapshot_date,
        "Source Sheet": sheet,
        "Source Row Number": row_number,
        "ERCOT Status Signal": signal,
        "ERCOT Data Quality Flags": [f"status_signal:{signal}"],
    }


def _merge_status_signal(primary: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    status_priority = {"Completed": 3, "Withdrawn": 3, "Inactive": 2, "Active": 1}
    merged = {**primary}
    if status_priority.get(str(signal.get("Status")), 0) >= status_priority.get(str(primary.get("Status")), 0):
        for key in ("Status", "Withdrawn Date", "Actual COD", "ERCOT Status Signal"):
            if signal.get(key) is not None:
                merged[key] = signal[key]
    for key in ("Fuel Type", "Capacity (MW)", "County"):
        if not merged.get(key) and signal.get(key):
            merged[key] = signal[key]
    merged["ERCOT Data Quality Flags"] = sorted(
        set((primary.get("ERCOT Data Quality Flags") or []) + (signal.get("ERCOT Data Quality Flags") or []))
    )
    merged["Source Sheet"] = f"{primary.get('Source Sheet')} + {signal.get('Source Sheet')}"
    return merged


def _ercot_fuel_label(fuel: Any, technology: Any) -> str | None:
    joined = " ".join(str(item) for item in (fuel, technology) if item is not None).strip()
    text = joined.upper()
    if "BA" in text or "BESS" in text or "BAT" in text or "STORAGE" in text:
        return "Battery Storage"
    if "SOL" in text or "PV" in text or "SOLAR" in text:
        return "Solar"
    if "WIN" in text or "WIND" in text or "WT" in text:
        return "Wind"
    if "GAS" in text or "CC" in text or "GT" in text:
        return "Gas"
    if "OIL" in text:
        return "Fuel Oil"
    if joined:
        return joined
    return None


def _rows_with_inr(frame: pd.DataFrame) -> pd.DataFrame:
    if "INR" not in frame.columns:
        return frame.iloc[0:0]
    mask = frame["INR"].astype(str).str.contains(r"\d{2}INR", case=False, regex=True, na=False)
    return frame[mask].copy()


def _ercot_likely_fields(frame: pd.DataFrame) -> dict[str, str | None]:
    columns = {str(column).lower(): str(column) for column in frame.columns}

    def find(*names: str) -> str | None:
        for name in names:
            for column_lower, original in columns.items():
                if name.lower() in column_lower:
                    return original
        return None

    return {
        "project_name": find("project name"),
        "queue_id": find("inr"),
        "county": find("county"),
        "fuel_or_technology": find("fuel") or find("technology"),
        "capacity_mw": find("capacity") or find("mw"),
        "status": find("gim study phase") or find("commissioning category"),
        "target_cod": find("projected cod"),
        "interconnection_agreement_date": find("ia signed"),
        "point_of_interconnection": find("poi"),
        "tsp": find("tsp") or find("transmission"),
    }


def _records_for_snapshot(con: Any, snapshot_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT record_id, snapshot_id, market, queue_id, project_name, normalized_project_name,
               interconnecting_entity, county, state, point_of_interconnection, transmission_owner,
               fuel_type, normalized_fuel_type, capacity_mw, status, normalized_status,
               request_date, target_cod, actual_cod, withdrawn_date, interconnection_agreement_date,
               last_updated_date, raw_record_id
        FROM normalized_project_records
        WHERE snapshot_id = ?
        ORDER BY queue_id NULLS LAST, project_name
        """,
        [snapshot_id],
    ).fetchall()
    columns = [
        "record_id",
        "snapshot_id",
        "market",
        "queue_id",
        "project_name",
        "normalized_project_name",
        "interconnecting_entity",
        "county",
        "state",
        "point_of_interconnection",
        "transmission_owner",
        "fuel_type",
        "normalized_fuel_type",
        "capacity_mw",
        "status",
        "normalized_status",
        "request_date",
        "target_cod",
        "actual_cod",
        "withdrawn_date",
        "interconnection_agreement_date",
        "last_updated_date",
        "raw_record_id",
    ]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _rank_real_candidates(record: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        ranked.append(
            {
                "entity_id": candidate["entity_id"],
                "record": candidate["record"],
                "match": compare_records(candidate["record"], record),
            }
        )
    ranked.sort(key=lambda item: item["match"].score, reverse=True)
    return ranked


def _create_real_entity(con: Any, record: dict[str, Any], snapshot_id: str, created_at: Any) -> str:
    entity_id = new_id("ent")
    con.execute(
        """
        INSERT INTO project_entities
        (entity_id, market, canonical_name, canonical_county, canonical_state, canonical_fuel_type,
         first_seen_snapshot_id, latest_seen_snapshot_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            entity_id,
            record["market"],
            record["project_name"],
            record["county"],
            record["state"],
            record["normalized_fuel_type"],
            snapshot_id,
            snapshot_id,
            created_at,
            created_at,
        ],
    )
    return entity_id


def _update_real_entity(con: Any, entity_id: str, record: dict[str, Any], snapshot_id: str, updated_at: Any) -> None:
    con.execute(
        """
        UPDATE project_entities
        SET canonical_name = ?, canonical_county = ?, canonical_state = ?, canonical_fuel_type = ?,
            latest_seen_snapshot_id = ?, updated_at = ?
        WHERE entity_id = ?
        """,
        [record["project_name"], record["county"], record["state"], record["normalized_fuel_type"], snapshot_id, updated_at, entity_id],
    )


def _create_real_link(
    con: Any,
    *,
    entity_id: str,
    record: dict[str, Any],
    score: float,
    method: str,
    features: dict[str, Any],
    is_ambiguous: bool,
    created_at: Any,
) -> None:
    con.execute(
        """
        INSERT INTO project_entity_links
        (link_id, entity_id, record_id, snapshot_id, match_score, match_method, match_features_json,
         is_ambiguous, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [new_id("link"), entity_id, record["record_id"], record["snapshot_id"], score, method, stable_json(features), is_ambiguous, created_at],
    )


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {
        "entity_id": candidate["entity_id"],
        "record_id": candidate["record"]["record_id"],
        "score": candidate["match"].score,
        "method": candidate["match"].method,
    }


def _delete_snapshot_payload(con: Any, snapshot_id: str) -> None:
    con.execute("DELETE FROM change_events WHERE from_snapshot_id = ? OR to_snapshot_id = ?", [snapshot_id, snapshot_id])
    con.execute("DELETE FROM diff_events WHERE from_snapshot_id = ? OR to_snapshot_id = ?", [snapshot_id, snapshot_id])
    con.execute("DELETE FROM citations WHERE snapshot_id = ?", [snapshot_id])
    con.execute("DELETE FROM project_entity_links WHERE snapshot_id = ?", [snapshot_id])
    con.execute(
        "DELETE FROM project_entities WHERE first_seen_snapshot_id = ? OR latest_seen_snapshot_id = ?",
        [snapshot_id, snapshot_id],
    )
    con.execute("DELETE FROM normalized_project_records WHERE snapshot_id = ?", [snapshot_id])
    con.execute("DELETE FROM raw_project_records WHERE snapshot_id = ?", [snapshot_id])
    con.execute("DELETE FROM snapshots WHERE snapshot_id = ?", [snapshot_id])


def _change_events_for_pair(from_snapshot_id: str, to_snapshot_id: str, db_path: str | Path | None) -> list[dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            {change_event_select_sql()}
            WHERE event_domain = 'queue' AND from_snapshot_id = ? AND to_snapshot_id = ?
            ORDER BY materiality_score DESC, event_type, entity_or_provision
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
    return [row_to_change_event(row) for row in rows]


def _source_context(from_snapshot_id: str, to_snapshot_id: str, db_path: str | Path | None) -> dict[str, Any]:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT sn.snapshot_id, sn.snapshot_date, sn.file_hash, sn.row_count, s.source_name, s.source_url
            FROM snapshots sn
            JOIN sources s ON s.source_id = sn.source_id
            WHERE sn.snapshot_id IN (?, ?)
            ORDER BY sn.snapshot_date
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
    lookup = {row[0]: row for row in rows}
    before = lookup[from_snapshot_id]
    after = lookup[to_snapshot_id]
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "from_snapshot_date": before[1].isoformat() if hasattr(before[1], "isoformat") else str(before[1]),
        "to_snapshot_date": after[1].isoformat() if hasattr(after[1], "isoformat") else str(after[1]),
        "from_file_hash": before[2],
        "to_file_hash": after[2],
        "from_row_count": int(before[3]),
        "to_row_count": int(after[3]),
        "source_name": after[4],
        "source_url": after[5],
    }


def _digest_event_line(event: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    before = event.get("before_json") or {}
    after = event.get("after_json") or {}
    changed = after.get("changed_fields_json") or before.get("changed_fields_json") or {}
    return {
        "trace_id": event["change_event_id"],
        "event_type": event["event_type"],
        "project_or_entity_name": event.get("entity_or_provision") or after.get("project_name") or before.get("project_name"),
        "capacity_mw": after.get("capacity_mw") if after.get("capacity_mw") is not None else before.get("capacity_mw"),
        "county_or_region": after.get("county") or before.get("county"),
        "before_after": changed,
        "from_snapshot_id": source["from_snapshot_id"],
        "to_snapshot_id": source["to_snapshot_id"],
        "source_file_hash_before": source["from_file_hash"],
        "source_file_hash_after": source["to_file_hash"],
        "source_url": source["source_url"],
        "confidence": event["confidence"],
        "materiality_score": event["materiality_score"],
        "is_hard_alert": event["is_hard_alert"],
        "is_ambiguous": event["is_ambiguous"],
        "explanation": event["explanation"],
    }


def _data_quality_warnings(from_snapshot_id: str, to_snapshot_id: str, db_path: str | Path | None) -> list[str]:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT snapshot_id, data_quality_flags_json, COUNT(*)
            FROM normalized_project_records
            WHERE snapshot_id IN (?, ?)
            GROUP BY snapshot_id, data_quality_flags_json
            ORDER BY snapshot_id, COUNT(*) DESC
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
    warnings = []
    for snapshot_id, flags_json, count in rows:
        flags = json_safe(flags_json)
        if flags:
            warnings.append(f"{snapshot_id}: {count} rows with flags {flags}")
    return warnings or ["No row-level data quality flags beyond normal optional-field gaps were emitted."]


def _ercot_digest_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        "## Source files",
        f"- From snapshot: `{result['from_snapshot_id']}` date={result['source_files']['from_snapshot_date']} hash={result['source_files']['from_file_hash']} rows={result['source_files']['from_row_count']}",
        f"- To snapshot: `{result['to_snapshot_id']}` date={result['source_files']['to_snapshot_date']} hash={result['source_files']['to_file_hash']} rows={result['source_files']['to_row_count']}",
        f"- Source URL: {result['source_files']['source_url']}",
        "",
        "## Executive summary",
        *[f"- {item}" for item in result["executive_summary"]],
        "",
        "## Top real queue changes",
        *_event_markdown_lines(result["top_real_queue_changes"]),
        "",
        "## New projects",
        *_event_markdown_lines(result["new_projects"]),
        "",
        "## Withdrawn / removed / completed projects",
        *_event_markdown_lines(result["withdrawn_removed_completed_projects"]),
        "",
        "## Status changes",
        *_event_markdown_lines(result["status_changes"]),
        "",
        "## Capacity changes",
        *_event_markdown_lines(result["capacity_changes"]),
        "",
        "## COD delays / accelerations",
        *_event_markdown_lines(result["cod_moves"]),
        "",
        "## Fuel / classification changes",
        *_event_markdown_lines(result["fuel_classification_changes"]),
        "",
        "## Ambiguous or suppressed entity-resolution noise",
        *_event_markdown_lines(result["ambiguous_or_suppressed_noise"]),
        "",
        "## Data quality warnings",
        *[f"- {item}" for item in result["data_quality_warnings"]],
        "",
        "## Reproducibility trace",
        *[f"- {item}" for item in result["reproducibility_trace"]],
        "",
        "## Caveats",
        *[f"- {item}" for item in result["caveats"]],
    ]
    return "\n".join(lines)


def _event_markdown_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None detected in this real ERCOT pair."]
    lines = []
    for row in rows:
        lines.append(
            "- "
            f"trace_id=`{row['trace_id']}` event_type=`{row['event_type']}` "
            f"project=`{row.get('project_or_entity_name')}` capacity_mw={row.get('capacity_mw')} "
            f"county={row.get('county_or_region')} before_after={row.get('before_after')} "
            f"from_snapshot_id=`{row['from_snapshot_id']}` to_snapshot_id=`{row['to_snapshot_id']}` "
            f"source_hash_before=`{row['source_file_hash_before']}` source_hash_after=`{row['source_file_hash_after']}` "
            f"confidence={row['confidence']} materiality_score={row['materiality_score']} "
            f"hard_alert={row['is_hard_alert']} ambiguous={row['is_ambiguous']} "
            f"source_url={row['source_url']} explanation={row['explanation']}"
        )
    return lines


def _write_diff_events_csv(
    *,
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None,
) -> str:
    events = _change_events_for_pair(from_snapshot_id, to_snapshot_id, db_path)
    source = _source_context(from_snapshot_id, to_snapshot_id, db_path)
    rows = [_digest_event_line(event, source) for event in events]
    label = f"{month_label(source['from_snapshot_date'])}_to_{month_label(source['to_snapshot_date'])}"
    path = real_reports_dir() / "ercot" / f"real_monthly_diff_events_{label}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "trace_id",
        "event_type",
        "project_or_entity_name",
        "capacity_mw",
        "county_or_region",
        "before_after",
        "from_snapshot_id",
        "to_snapshot_id",
        "source_file_hash_before",
        "source_file_hash_after",
        "source_url",
        "confidence",
        "materiality_score",
        "is_hard_alert",
        "is_ambiguous",
        "explanation",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: stable_json(row[key]) if key == "before_after" else row.get(key, "") for key in columns})
    return str(path.relative_to(project_root()))


def _profile_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# ERCOT GIS workbook profile: {Path(result['local_path']).name}",
        "",
        "## Source",
        f"- source_url: {result['source_url']}",
        f"- file_hash_sha256: `{result['file_hash_sha256']}`",
        f"- file_size_bytes: {result['file_size_bytes']}",
        f"- snapshot_date: {result.get('snapshot_date')}",
        f"- row_count_raw: {result['row_count_raw']}",
        f"- parse_status: {result['parse_status']}",
        "",
        "## Sheets",
    ]
    for sheet in result["sheet_profiles"]:
        lines.append(
            f"- {sheet['sheet_name']}: candidate={sheet.get('candidate_data_sheet')} "
            f"header_row={sheet.get('header_row')} row_count_with_inr={sheet.get('row_count_with_inr')}"
        )
        if sheet.get("likely_fields"):
            lines.append(f"  likely_fields={sheet['likely_fields']}")
        if sheet.get("parse_error"):
            lines.append(f"  parse_error={sheet['parse_error']}")
    if result["parse_errors"]:
        lines.extend(["", "## Parse warnings", *[f"- {item}" for item in result["parse_errors"]]])
    return "\n".join(lines)


def _is_gis_report(doc: dict[str, Any]) -> bool:
    friendly = str(doc.get("FriendlyName") or "")
    return friendly.startswith("GIS_Report_") and str(doc.get("Extension") or "").lower() == "xlsx"


def _snapshot_date_from_friendly_name(friendly_name: str) -> str | None:
    match = re.search(r"GIS_Report_?([A-Za-z]+)(20\d{2})", friendly_name)
    if not match:
        return None
    month_name, year = match.groups()
    try:
        parsed = pd.to_datetime(f"{month_name} {year}", format="%B %Y")
    except ValueError:
        parsed = pd.to_datetime(f"{month_name} {year}", errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_period("M").end_time.date().isoformat()


def _snapshot_date_from_filename(file_path: Path) -> str | None:
    match = re.search(r"(20\d{2})[_-](\d{2})", file_path.stem)
    if not match:
        return None
    year, month = match.groups()
    parsed = pd.Period(f"{year}-{month}", freq="M").end_time.date()
    return parsed.isoformat()
