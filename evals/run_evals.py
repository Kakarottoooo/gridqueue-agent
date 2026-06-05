from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.db import connect
from app.services.brief_generation import generate_brief
from app.services.ingestion import run_fixture_pipeline
from app.services.metrics import compute_metric_rollup


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"
EVAL_DB = RESULTS_DIR / "eval.duckdb"


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    description: str
    query_path: str
    check: Callable[[Path], tuple[bool, str, dict[str, Any]]]


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_fixture_pipeline(EVAL_DB, reset=True)
    cases = _cases()
    results = []
    for case in cases:
        passed, message, evidence = case.check(EVAL_DB)
        results.append(
            {
                "case_id": case.case_id,
                "description": case.description,
                "query_path": case.query_path,
                "passed": passed,
                "message": message,
                "evidence": evidence,
            }
        )

    passed_count = sum(1 for result in results if result["passed"])
    report = {
        "summary": {
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "total": len(results),
        },
        "results": results,
    }
    (RESULTS_DIR / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (RESULTS_DIR / "latest.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    if passed_count != len(results):
        raise SystemExit(1)


def _cases() -> list[EvalCase]:
    return [
        EvalCase(
            "renamed-project-not-new",
            "Renamed Lone Star project should be a name_changed event, not a new_project.",
            "diff_events joined to normalized_project_records.after_record_id",
            _renamed_project_not_new,
        ),
        EvalCase(
            "queue-id-changed-same-entity",
            "Pecos Battery queue ID changes from Q-1002 to Q-2002 but remains one entity.",
            "project_entity_links joined to records WHERE queue_id IN ('Q-1002','Q-2002')",
            _queue_id_changed_same_entity,
        ),
        EvalCase(
            "fuel-reclass-modified",
            "Sunfield Solar to Hybrid reclassification should be fuel_type_changed, not false add/delete.",
            "diff_events WHERE event_type='fuel_type_changed'",
            _fuel_reclass_modified,
        ),
        EvalCase(
            "capacity-threshold",
            "Cedar Creek capacity movement above tolerance should emit capacity_changed.",
            "diff_events WHERE event_type='capacity_changed'",
            _capacity_threshold,
        ),
        EvalCase(
            "target-cod-delay",
            "Blue Mesa target COD delay above 90 days should emit target_cod_delayed.",
            "diff_events WHERE event_type='target_cod_delayed'",
            _target_cod_delay,
        ),
        EvalCase(
            "ambiguous-match-flagged",
            "Twin Buttes candidates should be ambiguous and visible in diff events.",
            "project_entity_links.is_ambiguous and diff_events.event_type='ambiguous_match'",
            _ambiguous_match_flagged,
        ),
        EvalCase(
            "small-sample-rollup",
            "A narrow Comanche Battery query should roll up to market_fuel with a low demo threshold.",
            "compute_metric_rollup(county='Comanche', fuel_type='Battery', min_sample_n=2)",
            _small_sample_rollup,
        ),
        EvalCase(
            "insufficient-sample-abstains",
            "A high sample threshold should abstain from reporting rates.",
            "compute_metric_rollup(county='Comanche', fuel_type='Battery', min_sample_n=100)",
            _insufficient_sample_abstains,
        ),
        EvalCase(
            "brief-citations",
            "Brief should include citations and source-backed queue snapshot metadata.",
            "generate_brief(...).citations and queue_snapshot.citation_ids",
            _brief_citations,
        ),
        EvalCase(
            "brief-formal-study-caveat",
            "Brief must include the formal-study abstention caveat.",
            "generate_brief(...).caveats_and_abstentions",
            _brief_formal_study_caveat,
        ),
        EvalCase(
            "large-load-caveat",
            "A data-center/large-load question must not misuse generation-only queue data.",
            "generate_brief(question includes data center large load).large_load_context",
            _large_load_caveat,
        ),
        EvalCase(
            "latest-snapshot-used",
            "Brief should use the latest available snapshot for current queue snapshot.",
            "generate_brief(...).queue_snapshot.snapshot_id",
            _latest_snapshot_used,
        ),
    ]


def _renamed_project_not_new(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    with connect(db_path) as con:
        new_projects = con.execute(
            """
            SELECT r.project_name
            FROM diff_events e
            LEFT JOIN normalized_project_records r ON r.record_id = e.after_record_id
            WHERE e.event_type = 'new_project'
            """
        ).fetchall()
        name_changed = con.execute(
            """
            SELECT COUNT(*)
            FROM diff_events e
            JOIN normalized_project_records r ON r.record_id = e.after_record_id
            WHERE e.event_type = 'name_changed' AND r.project_name = 'Lone Star Solar Project'
            """
        ).fetchone()[0]
    names = [row[0] for row in new_projects]
    passed = "Lone Star Solar Project" not in names and name_changed == 1
    return passed, "Lone Star rename is handled by entity-resolution." if passed else "Lone Star rename was misclassified.", {"new_projects": names, "name_changed_count": name_changed}


def _queue_id_changed_same_entity(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT r.queue_id, l.entity_id, l.match_method, l.match_score
            FROM project_entity_links l
            JOIN normalized_project_records r ON r.record_id = l.record_id
            WHERE r.queue_id IN ('Q-1002', 'Q-2002')
            ORDER BY r.queue_id
            """
        ).fetchall()
    entity_ids = {row[1] for row in rows}
    passed = len(rows) == 2 and len(entity_ids) == 1
    return passed, "Changed queue ID linked to one stable entity." if passed else "Changed queue ID split into multiple entities.", {"rows": rows}


def _fuel_reclass_modified(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT e.event_type, r.project_name, e.changed_fields_json
            FROM diff_events e
            JOIN normalized_project_records r ON r.record_id = e.after_record_id
            WHERE e.event_type IN ('fuel_type_changed', 'new_project')
            """
        ).fetchall()
    payload = "\n".join(str(row) for row in rows)
    passed = "Sunfield Hybrid" in payload and "fuel_type_changed" in payload
    return passed, "Fuel reclassification is a modification event." if passed else "Fuel reclassification was not detected.", {"rows": rows}


def _capacity_threshold(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    return _event_exists(db_path, "capacity_changed", "Cedar Creek Solar")


def _target_cod_delay(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    return _event_exists(db_path, "target_cod_delayed", "Blue Mesa Wind")


def _ambiguous_match_flagged(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    with connect(db_path) as con:
        ambiguous_links = con.execute("SELECT COUNT(*) FROM project_entity_links WHERE is_ambiguous = TRUE").fetchone()[0]
        ambiguous_events = con.execute("SELECT COUNT(*) FROM diff_events WHERE event_type = 'ambiguous_match'").fetchone()[0]
    passed = ambiguous_links == 2 and ambiguous_events == 2
    return passed, "Ambiguous matches are visible and not forced." if passed else "Ambiguous match counts were unexpected.", {"ambiguous_links": ambiguous_links, "ambiguous_events": ambiguous_events}


def _small_sample_rollup(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    metric = compute_metric_rollup(market="ERCOT", county="Comanche", fuel_type="Battery", min_sample_n=2, db_path=db_path)
    passed = metric["fallback_level"] == "market_fuel" and metric["sample_n"] >= 2 and metric["confidence"] != "Insufficient"
    return passed, "Narrow small sample rolled up to market_fuel." if passed else "Rollup did not choose expected fallback.", metric


def _insufficient_sample_abstains(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    metric = compute_metric_rollup(market="ERCOT", county="Comanche", fuel_type="Battery", min_sample_n=100, db_path=db_path)
    passed = metric["confidence"] == "Insufficient" and metric["completion_rate"] is None and metric["withdrawal_rate"] is None
    return passed, "Insufficient sample abstained from rates." if passed else "Insufficient sample still produced rates.", metric


def _brief_citations(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _brief(db_path)
    passed = bool(brief["citations"]) and bool(brief["queue_snapshot"]["citation_ids"])
    return passed, "Brief has citations and snapshot citation ids." if passed else "Brief is missing citations.", {"citations": brief["citations"], "queue_snapshot": brief["queue_snapshot"]}


def _brief_formal_study_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _brief(db_path)
    caveats = "\n".join(brief["caveats_and_abstentions"])
    passed = "not a formal interconnection study" in caveats
    return passed, "Formal-study caveat present." if passed else "Formal-study caveat missing.", {"caveats": brief["caveats_and_abstentions"]}


def _large_load_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _brief(db_path, question="What about a data center large load?")
    context = brief["large_load_context"]
    passed = context is not None and "generation-resource records" in context["summary"]
    return passed, "Large-load answer is caveated against generation-only queue data." if passed else "Large-load caveat missing.", {"large_load_context": context}


def _latest_snapshot_used(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _brief(db_path)
    snapshot_id = brief["queue_snapshot"]["snapshot_id"]
    passed = snapshot_id == "snap_ercot_2026_02_28"
    return passed, "Brief uses latest snapshot." if passed else "Brief did not use latest snapshot.", {"snapshot_id": snapshot_id}


def _event_exists(db_path: Path, event_type: str, project_name: str) -> tuple[bool, str, dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT e.event_type, r.project_name, e.changed_fields_json
            FROM diff_events e
            JOIN normalized_project_records r ON r.record_id = e.after_record_id
            WHERE e.event_type = ? AND r.project_name = ?
            """,
            [event_type, project_name],
        ).fetchall()
    passed = bool(rows)
    return passed, f"{event_type} exists for {project_name}." if passed else f"{event_type} missing for {project_name}.", {"rows": rows}


def _brief(db_path: Path, question: str = "What public interconnection risks should I know?") -> dict[str, Any]:
    return generate_brief(
        market="ERCOT",
        project_type="Battery",
        county="Reeves",
        capacity_mw=100,
        target_cod_year=2028,
        question=question,
        min_sample_n=2,
        db_path=db_path,
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GridQueue Agent eval results",
        "",
        f"Passed: {report['summary']['passed']} / {report['summary']['total']}",
        "",
        "| Case | Result | Message |",
        "| --- | --- | --- |",
    ]
    for result in report["results"]:
        mark = "PASS" if result["passed"] else "FAIL"
        lines.append(f"| `{result['case_id']}` | {mark} | {result['message']} |")
    lines.extend(["", "## Query paths"])
    for result in report["results"]:
        lines.append(f"- `{result['case_id']}`: {result['query_path']}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()

