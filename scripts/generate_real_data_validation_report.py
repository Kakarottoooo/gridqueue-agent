from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    report = build_report()
    output = ROOT / "docs" / "REAL_DATA_VALIDATION.md"
    output.write_text(report, encoding="utf-8")
    print(output)


def build_report() -> str:
    manifest = _optional_json(ROOT / "reports" / "real_data" / "source_manifest.json") or {"sources": []}
    ercot_summary = _latest_json(ROOT / "reports" / "real_data" / "ercot", "real_monthly_diff_summary_*.json")
    ercot_digest = _latest_path(ROOT / "reports" / "real_data" / "ercot", "real_monthly_digest_*.md")
    lbnl = _optional_json(ROOT / "reports" / "real_data" / "lbnl" / "lbnl_reproduction.json")
    independent = _optional_json(ROOT / "reports" / "real_data" / "independent_checks.json")
    real_evals = _optional_json(ROOT / "evals" / "results" / "real_latest.json")
    audit_rows = _latest_audit_rows()
    if not ercot_summary or not lbnl:
        _write_blocked_doc()
    lines = [
        "# Real Data Validation",
        "",
        "Fixture mode proves the software mechanics. Real-data validation proves the parser, normalization, entity-resolution, diffing, and reporting logic against public source files.",
        "",
        "## Summary",
        f"- Did real ERCOT data run? {'yes' if ercot_summary else 'no'}",
        f"- ERCOT months: {_ercot_months(ercot_summary) if ercot_summary else 'not available'}",
        f"- Did real LBNL data run? {'yes' if lbnl else 'no'}",
        "- Validated slice: ERCOT GIS month-over-month generation-resource diff plus LBNL Queued Up workbook reproduction checks.",
        "- This is a real-data validated slice, not a claim that the full platform is production-ready.",
        "- What remains unverified: human entity-resolution labels, additional ERCOT months, other markets, and large-load/data-center queues.",
        "",
        "## Source manifest",
        *_manifest_lines(manifest.get("sources", [])),
        "",
        "## ERCOT ingestion results",
        *_ercot_ingestion_lines(ercot_summary),
        "",
        "## ERCOT real monthly diff",
        *_ercot_diff_lines(ercot_summary, ercot_digest),
        "",
        "## Entity-resolution audit",
        *_audit_lines(ercot_summary, audit_rows),
        "",
        "## LBNL workbook validation",
        *_lbnl_lines(lbnl),
        "",
        "## Independent checks",
        *_independent_lines(independent),
        "",
        "## Real-data eval results",
        *_real_eval_lines(real_evals),
        "",
        "## Known limitations",
        "- ERCOT GIS is generation-resource interconnection data, not a full load or data-center queue.",
        "- LBNL Queued Up excludes load interconnection requests, distribution-connected projects, and behind-the-meter projects.",
        "- Entity resolution still needs human spot-checking. The generated CSV has system labels only unless a reviewer fills manual_label.",
        "- LBNL summary tabs can include derived or filtered values that project-level raw component sums do not reproduce exactly.",
        "- Real output is public-data signal analysis, not formal diligence, power-flow study, legal advice, or project-specific verification.",
        "",
        "## Next validation target",
        "- Expand to three to six consecutive ERCOT months.",
        "- Hand-label 50 to 100 entity-resolution cases from the manual review CSV.",
        "- Add PJM/MISO only after ERCOT real validation is stable.",
        "- Re-run after each ERCOT monthly release.",
        "",
        "## Validation conclusion",
        _conclusion(ercot_summary, lbnl, independent),
    ]
    return "\n".join(lines)


def _manifest_lines(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return ["- No real source manifest entries were generated."]
    lines = []
    for item in sources:
        lines.append(
            f"- source_name={item.get('source_name')} snapshot_date={item.get('snapshot_date')} "
            f"local_path={item.get('local_path')} hash=`{item.get('file_hash_sha256')}` "
            f"size_bytes={item.get('file_size_bytes')} row_count_raw={item.get('row_count_raw')} "
            f"parse_status={item.get('parse_status')} source_url={item.get('source_url')}"
        )
        if item.get("parse_errors"):
            lines.append(f"  parse_errors={item.get('parse_errors')}")
    return lines


def _ercot_ingestion_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return ["- Real ERCOT ingestion did not run."]
    return [
        f"- from_snapshot_id: `{summary['from_snapshot_id']}`",
        f"- to_snapshot_id: `{summary['to_snapshot_id']}`",
        f"- from file hash: `{summary['from_file_hash_sha256']}`",
        f"- to file hash: `{summary['to_file_hash_sha256']}`",
        f"- raw parsed source rows: from={summary['from_row_count_raw']} to={summary['to_row_count_raw']}",
        f"- normalized deduplicated rows: from={summary['from_normalized_row_count']} to={summary['to_normalized_row_count']}",
        f"- profiles: {summary['profiles']}",
        "- Sheets parsed include Project Details - Large Gen, Project Details - Small Gen, Commissioning Update, Inactive Projects, and Cancellation Update.",
        "- Optional fields such as permits and detailed milestone dates are preserved in raw payload JSON but not all are normalized into first-class columns.",
    ]


def _ercot_diff_lines(summary: dict[str, Any] | None, digest_path: Path | None) -> list[str]:
    if not summary:
        return ["- Real ERCOT diff did not run."]
    counts = summary["diff"]["counts_by_event_type"]
    return [
        f"- total diff events including unchanged: {summary['diff']['event_count']}",
        f"- event counts: {counts}",
        f"- watcher-adapted material events: {summary['adapter']['adapted_event_count']}",
        f"- real digest: `{_rel(digest_path) if digest_path else summary.get('digest_path')}`",
        f"- event CSV: `{summary['events_csv_path']}`",
        "- Hard alerts and suppressed events are separated in the digest. removed_project means missing from later snapshot, not automatic withdrawal.",
        "- Required caveat is present in the digest: ERCOT GIS is generation-resource data and is not a complete large-load/data-center queue.",
    ]


def _audit_lines(summary: dict[str, Any] | None, rows: list[dict[str, str]]) -> list[str]:
    if not summary:
        return ["- Entity-resolution audit did not run."]
    audit = summary["audit"]
    manual_labels = [row for row in rows if row.get("manual_label")]
    return [
        f"- audit CSV: `{audit['matches_path']}`",
        f"- ambiguous CSV: `{audit['ambiguous_path']}`",
        f"- manual review template: `{audit['manual_review_path']}`",
        f"- exact-ID matches: {audit['exact_matches']}",
        f"- strong fuzzy matches: {audit['fuzzy_matches']}",
        f"- ambiguous matches: {audit['ambiguous_matches']}",
        f"- true additions suggested by system: {audit['true_additions']}",
        f"- true removals/missing suggested by system: {audit['true_removals_or_missing']}",
        f"- true withdrawals suggested by system: {audit['true_withdrawals']}",
        f"- true completions suggested by system: {audit['true_completed']}",
        f"- manual labels available? {'yes' if manual_labels else 'no'}",
        "- Precision/recall is not reported because no human manual labels are present yet.",
        "- System labels are not called manual verification. `auto_verified_exact_id` only means conservative exact INR match.",
    ]


def _lbnl_lines(lbnl: dict[str, Any] | None) -> list[str]:
    if not lbnl:
        return ["- LBNL reproduction did not run."]
    lines = [
        f"- workbook_id: `{lbnl['workbook_id']}`",
        f"- workbook hash: `{lbnl['file_hash_sha256']}`",
        f"- row_count_raw: {lbnl['row_count_raw']}",
        f"- sheets parsed: {len(lbnl['sheets_parsed'])}",
        f"- reproduction report: `{lbnl['markdown_path']}`",
        f"- independent calculations CSV: `{lbnl['independent_calculations_csv']}`",
        "- Metrics calculated:",
    ]
    metrics = lbnl["metrics_calculated"]
    for key in (
        "active_project_row_count",
        "active_capacity_gw_mw1_only",
        "active_capacity_gw_mw1_mw2_mw3",
        "ercot_active_project_row_count",
        "ercot_active_capacity_gw_mw1_only",
        "median_days_request_to_terminal_status",
    ):
        lines.append(f"  - {key}: {metrics.get(key)}")
    lines.append("- Official summary comparisons:")
    for comparison in lbnl["comparisons"]:
        lines.append(
            f"  - {comparison['metric']}: calculated={comparison['calculated']} official_summary={comparison['official_summary']} "
            f"status={comparison['status']} delta={comparison['delta']}"
        )
    lines.append("- Mismatches / limitations:")
    for item in lbnl["mismatches_and_limitations"]:
        lines.append(f"  - {item}")
    return lines


def _independent_lines(independent: dict[str, Any] | None) -> list[str]:
    if not independent:
        return ["- Independent checks did not run."]
    lines = [
        f"- report: `reports/real_data/independent_checks.md`",
        f"- status_counts: {independent['status_counts']}",
    ]
    for check in independent["checks"]:
        lines.append(f"- {check['domain']} {check['check']}: {check['status']} ({check.get('details')})")
    return lines


def _real_eval_lines(real_evals: dict[str, Any] | None) -> list[str]:
    if not real_evals:
        return ["- Real evals have not been run yet."]
    return [
        f"- report: `evals/results/real_latest.md`",
        f"- total: {real_evals['total']}",
        f"- status_counts: {real_evals['status_counts']}",
        "- skipped_manual_review is expected until a human reviewer fills manual labels.",
    ]


def _conclusion(ercot_summary: dict[str, Any] | None, lbnl: dict[str, Any] | None, independent: dict[str, Any] | None) -> str:
    if not ercot_summary or not lbnl:
        return "Blocked: the repository does not yet contain both a real ERCOT diff and a real LBNL reproduction report."
    failed_independent = (independent or {}).get("status_counts", {}).get("failed", 0)
    blocked_independent = (independent or {}).get("status_counts", {}).get("blocked_missing_real_data", 0)
    if failed_independent or blocked_independent:
        return "Partially validated: real outputs exist, but independent checks still have failed or blocked items."
    return "Validated slice achieved: the repository contains two real ERCOT GIS monthly reports ingested, a real month-over-month diff and digest, an entity-resolution audit, and a real LBNL workbook reproduction report with documented mismatches."


def _write_blocked_doc() -> None:
    path = ROOT / "docs" / "REAL_DATA_BLOCKED.md"
    lines = [
        "# Real Data Validation Blocked",
        "",
        "Real validation cannot be marked complete until real source files are present and parsed.",
        "",
        "## ERCOT manual steps",
        "- Go to https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er",
        "- Download two consecutive monthly GIS_Report_*.xlsx files.",
        "- Place them under data/raw/real/ercot/gis/ as ERCOT_GIS_YYYY_MM.xlsx.",
        "- Run python scripts/run_real_ercot_pair.py with explicit --from-file/--to-file and snapshot dates.",
        "",
        "## LBNL manual steps",
        "- Go to https://emp.lbl.gov/queues",
        "- Download the Data File XLSX.",
        "- Place it under data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx.",
        "- Run python scripts/run_lbnl_reproduction.py.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _latest_json(directory: Path, pattern: str) -> dict[str, Any] | None:
    path = _latest_path(directory, pattern)
    return _optional_json(path) if path else None


def _latest_path(directory: Path, pattern: str) -> Path | None:
    paths = sorted(directory.glob(pattern))
    return paths[-1] if paths else None


def _optional_json(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_audit_rows() -> list[dict[str, str]]:
    path = _latest_path(ROOT / "reports" / "real_data" / "entity_resolution_audit", "ercot_matches_*.csv")
    if not path:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _ercot_months(summary: dict[str, Any]) -> str:
    return f"{summary['from_snapshot_date']} to {summary['to_snapshot_date']}"


def _rel(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
