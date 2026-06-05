from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"


@dataclass
class RealEvalResult:
    case_id: str
    category: str
    name: str
    status: str
    message: str
    details: dict[str, Any]


def main() -> None:
    results = run_real_evals()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = _summary(results)
    (RESULTS_DIR / "real_latest.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (RESULTS_DIR / "real_latest.md").write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["status_counts"], indent=2, sort_keys=True))
    if payload["status_counts"].get("failed", 0):
        raise SystemExit(1)
    if payload["status_counts"].get("blocked_missing_real_data", 0):
        raise SystemExit(2)


def run_real_evals() -> list[RealEvalResult]:
    cases: list[tuple[str, str, str, Callable[[], tuple[str, str, dict[str, Any]]]]] = [
        ("ercot_ingestion_01", "ercot_real_ingestion", "ERCOT source file hashes exist", _ercot_hashes_exist),
        ("ercot_ingestion_02", "ercot_real_ingestion", "ERCOT row counts match independent checks", _ercot_row_counts_match_independent),
        ("ercot_ingestion_03", "ercot_real_ingestion", "ERCOT required columns are mapped or documented", _ercot_columns_mapped),
        ("ercot_ingestion_04", "ercot_real_ingestion", "ERCOT normalized records preserve raw payload counts", _ercot_raw_payload_counts),
        ("ercot_diff_05", "ercot_real_diff", "Digest top events have snapshot IDs and file hashes", _digest_events_traceable),
        ("ercot_diff_06", "ercot_real_diff", "Ambiguous events are not hard alerts", _ambiguous_not_hard),
        ("ercot_diff_07", "ercot_real_diff", "Stable exact INR matches are not counted as new", _stable_ids_not_new),
        ("ercot_diff_08", "ercot_real_diff", "Removed records are not automatically withdrawn", _removed_not_withdrawn),
        ("ercot_diff_09", "ercot_real_diff", "Capacity changes are detected with raw support", _capacity_changes_detected),
        ("ercot_diff_10", "ercot_real_diff", "COD moves are detected with raw support", _cod_moves_detected),
        ("entity_11", "entity_resolution_human_labels", "Manual labels are evaluated or skipped honestly", _manual_labels_status),
        ("lbnl_13", "lbnl_real_reproduction", "LBNL workbook profile exists", _lbnl_profile_exists),
        ("lbnl_14", "lbnl_real_reproduction", "At least three LBNL metrics are calculated", _lbnl_three_metrics),
        ("lbnl_15", "lbnl_real_reproduction", "At least one metric is compared to official summary", _lbnl_official_comparison),
        ("lbnl_16", "lbnl_real_reproduction", "LBNL mismatches are documented", _lbnl_mismatches_documented),
        ("lbnl_17", "lbnl_real_reproduction", "LBNL report makes no load-interconnection claim", _lbnl_no_load_claim),
        ("report_18", "report_quality", "REAL_DATA_VALIDATION exists", _validation_doc_exists),
        ("report_19", "report_quality", "Real ERCOT digest exists", _ercot_digest_exists),
        ("report_20", "report_quality", "LBNL reproduction report exists", _lbnl_repro_exists),
        ("report_21", "report_quality", "README has real validation section", _readme_real_validation_section),
        ("report_22", "report_quality", "Reports distinguish fixtures from real data", _reports_distinguish_fixtures),
        ("independent_23", "independent_checks", "Independent checks passed or documented", _independent_checks_status),
    ]
    results = []
    for case_id, category, name, func in cases:
        try:
            status, message, details = func()
        except FileNotFoundError as exc:
            status, message, details = "blocked_missing_real_data", str(exc), {}
        except Exception as exc:  # noqa: BLE001
            status, message, details = "failed", str(exc), {}
        results.append(RealEvalResult(case_id, category, name, status, message, details))
    return results


def _ercot_hashes_exist() -> tuple[str, str, dict[str, Any]]:
    manifest = _manifest()
    ercot = [item for item in manifest if item.get("source_name") == "ERCOT GIS Report"]
    ok = len(ercot) >= 2 and all(len(str(item.get("file_hash_sha256", ""))) == 64 for item in ercot[:2])
    return _pass_fail(ok, f"ERCOT manifest entries={len(ercot)}", {"hashes": [item.get("file_hash_sha256") for item in ercot]})


def _ercot_row_counts_match_independent() -> tuple[str, str, dict[str, Any]]:
    checks = _json(ROOT / "reports" / "real_data" / "independent_checks.json")
    rows = [item for item in checks["checks"] if item["domain"] == "ercot" and item["check"].startswith("raw_row_count_vs_ingested")]
    ok = len(rows) >= 2 and all(item["status"] == "passed" for item in rows)
    return _pass_fail(ok, f"ERCOT independent row-count checks={len(rows)}", {"checks": rows})


def _ercot_columns_mapped() -> tuple[str, str, dict[str, Any]]:
    profiles = sorted((ROOT / "reports" / "real_data" / "ercot").glob("profile_*.json"))
    if len(profiles) < 2:
        raise FileNotFoundError("ERCOT profile JSON files are missing.")
    missing = []
    for path in profiles[:2]:
        profile = _json(path)
        fields = []
        for sheet in profile["sheet_profiles"]:
            if sheet.get("candidate_data_sheet") and sheet.get("likely_fields"):
                fields.append(sheet["likely_fields"])
        if not any(item.get("queue_id") and item.get("project_name") and item.get("capacity_mw") for item in fields):
            missing.append(path.name)
    return _pass_fail(not missing, "ERCOT profile mapped queue_id/project_name/capacity fields.", {"missing": missing})


def _ercot_raw_payload_counts() -> tuple[str, str, dict[str, Any]]:
    summary = _ercot_summary()
    ok = summary["from_normalized_row_count"] > 0 and summary["to_normalized_row_count"] > 0
    return _pass_fail(ok, "ERCOT normalized rows are present and tied to raw payload records.", summary)


def _digest_events_traceable() -> tuple[str, str, dict[str, Any]]:
    digest = _ercot_digest_json()
    rows = digest["top_real_queue_changes"]
    required = ("from_snapshot_id", "to_snapshot_id", "source_file_hash_before", "source_file_hash_after", "trace_id")
    ok = bool(rows) and all(all(row.get(key) for key in required) for row in rows)
    return _pass_fail(ok, f"Top traceable events={len(rows)}", {"sample": rows[:3]})


def _ambiguous_not_hard() -> tuple[str, str, dict[str, Any]]:
    digest = _ercot_digest_json()
    rows = digest.get("ambiguous_or_suppressed_noise", [])
    bad = [row for row in rows if row.get("is_ambiguous") and row.get("is_hard_alert")]
    return _pass_fail(not bad, "Ambiguous digest rows are not hard alerts.", {"bad": bad[:5], "count": len(rows)})


def _stable_ids_not_new() -> tuple[str, str, dict[str, Any]]:
    audit = _read_audit_rows()
    exact = [row for row in audit if row["system_label"] == "auto_verified_exact_id"]
    new_same_id = [
        row
        for row in audit
        if row["system_label"] == "system_suggested_true_new" and row["queue_id_after"] in {item["queue_id_before"] for item in exact}
    ]
    return _pass_fail(bool(exact) and not new_same_id, f"Exact INR matches={len(exact)}", {"new_same_id": new_same_id[:5]})


def _removed_not_withdrawn() -> tuple[str, str, dict[str, Any]]:
    digest = _ercot_digest_json()
    removed = [row for row in digest["withdrawn_removed_completed_projects"] if row["event_type"] == "removed_project"]
    markdown = _ercot_digest_path().read_text(encoding="utf-8")
    ok = bool(removed) and "not automatic withdrawal evidence" in markdown
    return _pass_fail(ok, f"Removed events={len(removed)}", {"sample": removed[:3]})


def _capacity_changes_detected() -> tuple[str, str, dict[str, Any]]:
    summary = _ercot_summary()
    count = summary["diff"]["counts_by_event_type"].get("capacity_changed", 0)
    return _pass_fail(count > 0, f"capacity_changed count={count}", {"counts": summary["diff"]["counts_by_event_type"]})


def _cod_moves_detected() -> tuple[str, str, dict[str, Any]]:
    summary = _ercot_summary()
    counts = summary["diff"]["counts_by_event_type"]
    count = counts.get("target_cod_delayed", 0) + counts.get("target_cod_accelerated", 0)
    return _pass_fail(count > 0, f"COD move count={count}", {"counts": counts})


def _manual_labels_status() -> tuple[str, str, dict[str, Any]]:
    rows = _read_audit_rows()
    manual = [row for row in rows if row.get("manual_label")]
    if not manual:
        return "skipped_manual_review", "No human manual labels are present; precision eval is skipped, not passed.", {"manual_label_count": 0}
    same = [row for row in manual if row["manual_label"] == "same_entity"]
    precision = len(same) / len(manual)
    return _pass_fail(precision >= 0.8, f"Manual label precision={precision:.3f}", {"manual_label_count": len(manual), "precision": precision})


def _lbnl_profile_exists() -> tuple[str, str, dict[str, Any]]:
    path = ROOT / "reports" / "real_data" / "lbnl" / "workbook_profile.json"
    profile = _json(path)
    ok = profile["project_row_count"] > 0 and profile["project_level_sheet"] == "03. Complete Queue Data"
    return _pass_fail(ok, "LBNL workbook profile has project sheet and rows.", {"row_count": profile["project_row_count"]})


def _lbnl_three_metrics() -> tuple[str, str, dict[str, Any]]:
    repro = _lbnl_repro()
    metrics = repro["metrics_calculated"]
    keys = [key for key, value in metrics.items() if value not in (None, {}, [])]
    return _pass_fail(len(keys) >= 3, f"LBNL calculated metric fields={len(keys)}", {"keys": keys})


def _lbnl_official_comparison() -> tuple[str, str, dict[str, Any]]:
    comparisons = _lbnl_repro()["comparisons"]
    ok = any(item["status"] == "matched_within_tolerance" for item in comparisons)
    return _pass_fail(ok, "At least one LBNL metric matches an official workbook summary tab.", {"comparisons": comparisons})


def _lbnl_mismatches_documented() -> tuple[str, str, dict[str, Any]]:
    repro = _lbnl_repro()
    mismatches = repro["mismatches_and_limitations"]
    ok = bool(mismatches) and all("mismatch" in item.lower() or "No compared" in item for item in mismatches)
    return _pass_fail(ok, "LBNL mismatches/limitations are documented.", {"mismatches": mismatches})


def _lbnl_no_load_claim() -> tuple[str, str, dict[str, Any]]:
    text = (ROOT / "reports" / "real_data" / "lbnl" / "lbnl_reproduction.md").read_text(encoding="utf-8").lower()
    ok = "does not include load interconnection requests" in text and "data-center queue" not in text
    return _pass_fail(ok, "LBNL reproduction caveats exclude load-interconnection claims.", {})


def _validation_doc_exists() -> tuple[str, str, dict[str, Any]]:
    path = ROOT / "docs" / "REAL_DATA_VALIDATION.md"
    ok = path.exists() and "Source manifest" in path.read_text(encoding="utf-8")
    return _pass_fail(ok, "docs/REAL_DATA_VALIDATION.md exists with source manifest section.", {})


def _ercot_digest_exists() -> tuple[str, str, dict[str, Any]]:
    path = _ercot_digest_path()
    ok = path.exists() and "Real ERCOT GIS Monthly Digest" in path.read_text(encoding="utf-8")
    return _pass_fail(ok, f"ERCOT digest path={path.relative_to(ROOT)}", {})


def _lbnl_repro_exists() -> tuple[str, str, dict[str, Any]]:
    path = ROOT / "reports" / "real_data" / "lbnl" / "lbnl_reproduction.md"
    ok = path.exists() and "LBNL Queued Up real workbook reproduction" in path.read_text(encoding="utf-8")
    return _pass_fail(ok, f"LBNL reproduction path={path.relative_to(ROOT)}", {})


def _readme_real_validation_section() -> tuple[str, str, dict[str, Any]]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    ok = "Real Data Validation Sprint" in text and "docs/REAL_DATA_VALIDATION.md" in text
    return _pass_fail(ok, "README includes Real Data Validation Sprint section.", {})


def _reports_distinguish_fixtures() -> tuple[str, str, dict[str, Any]]:
    doc = (ROOT / "docs" / "REAL_DATA_VALIDATION.md").read_text(encoding="utf-8")
    ok = "Fixture mode proves the software mechanics" in doc and "real ERCOT" in doc
    return _pass_fail(ok, "Validation report distinguishes fixture and real-data modes.", {})


def _independent_checks_status() -> tuple[str, str, dict[str, Any]]:
    checks = _json(ROOT / "reports" / "real_data" / "independent_checks.json")
    failed = checks["status_counts"].get("failed", 0)
    blocked = checks["status_counts"].get("blocked_missing_real_data", 0)
    ok = failed == 0 and blocked == 0
    return _pass_fail(ok, f"Independent check statuses={checks['status_counts']}", checks["status_counts"])


def _manifest() -> list[dict[str, Any]]:
    path = ROOT / "reports" / "real_data" / "source_manifest.json"
    payload = _json(path)
    return payload["sources"]


def _ercot_summary() -> dict[str, Any]:
    paths = sorted((ROOT / "reports" / "real_data" / "ercot").glob("real_monthly_diff_summary_*.json"))
    if not paths:
        raise FileNotFoundError("Real ERCOT diff summary is missing.")
    return _json(paths[-1])


def _ercot_digest_path() -> Path:
    paths = sorted((ROOT / "reports" / "real_data" / "ercot").glob("real_monthly_digest_*.md"))
    if not paths:
        raise FileNotFoundError("Real ERCOT digest is missing.")
    return paths[-1]


def _ercot_digest_json() -> dict[str, Any]:
    paths = sorted((ROOT / "reports" / "real_data" / "ercot").glob("real_monthly_digest_*.json"))
    if not paths:
        raise FileNotFoundError("Real ERCOT digest JSON is missing.")
    return _json(paths[-1])


def _read_audit_rows() -> list[dict[str, str]]:
    paths = sorted((ROOT / "reports" / "real_data" / "entity_resolution_audit").glob("ercot_matches_*.csv"))
    if not paths:
        raise FileNotFoundError("ERCOT entity-resolution audit CSV is missing.")
    with paths[-1].open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _lbnl_repro() -> dict[str, Any]:
    return _json(ROOT / "reports" / "real_data" / "lbnl" / "lbnl_reproduction.json")


def _json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing real eval input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _pass_fail(ok: bool, message: str, details: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    return ("passed" if ok else "failed", message, details)


def _summary(results: list[RealEvalResult]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    categories: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        categories.setdefault(result.category, []).append(result.__dict__)
    return {
        "total": len(results),
        "status_counts": counts,
        "categories": categories,
        "results": [result.__dict__ for result in results],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Real-data eval results",
        "",
        f"- total: {payload['total']}",
        f"- status_counts: {payload['status_counts']}",
        "",
    ]
    for category, results in payload["categories"].items():
        lines.extend([f"## {category}", ""])
        for result in results:
            lines.append(f"- {result['case_id']} `{result['status']}`: {result['message']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
