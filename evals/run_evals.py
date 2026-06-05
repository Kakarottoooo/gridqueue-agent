from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.db import connect
from app.services.brief_generation import generate_brief
from app.services.flexibility import (
    calculate_compute_cost,
    estimate_interconnection_benefit,
    evaluate_eligibility,
    generate_flexibility_brief,
    get_compute_assumption,
    run_tradeoff_sweep,
    seed_flexibility_rules,
)
from app.services.flexibility.brief import FLEXIBILITY_CAVEAT
from app.services.flexibility.compute_cost import ASSUMPTION_FIELDS
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
    category: str = "gridqueue_core"


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_fixture_pipeline(EVAL_DB, reset=True)
    seed_flexibility_rules(EVAL_DB)
    cases = _cases()
    results = []
    for case in cases:
        passed, message, evidence = case.check(EVAL_DB)
        results.append(
            {
                "case_id": case.case_id,
                "description": case.description,
                "query_path": case.query_path,
                "category": case.category,
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
        "categories": _category_summary(results),
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
        EvalCase(
            "flex-ferc-pending-contingent",
            "FERC RM26-4 pending/proposed rule should produce contingent, not final eligible.",
            "evaluate_eligibility(jurisdiction='FERC').eligibility_status",
            _flex_ferc_pending_contingent,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-technical-evidence-not-rule",
            "Emerald/EPRI technical evidence must not be treated as a regulatory rule.",
            "evaluate_eligibility(jurisdiction='EVIDENCE').eligibility_status",
            _flex_technical_evidence_not_rule,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-eligibility-source-urls",
            "Every eligibility claim should include a source URL.",
            "evaluate_eligibility(...).citations.source_url",
            _flex_eligibility_source_urls,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-missing-control-ambiguous",
            "Missing control/metering criteria should produce ambiguous or unsupported, not eligible.",
            "evaluate_eligibility(metering_or_control_capability=None)",
            _flex_missing_control_ambiguous,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-compute-assumptions-exposed",
            "Compute-cost output must expose every assumption used.",
            "calculate_compute_cost(...).assumptions_json",
            _flex_compute_assumptions_exposed,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-extrapolation-flag",
            "Commitment above 25% or duration above 3h must be marked as extrapolation.",
            "calculate_compute_cost(commitment_depth_pct=30)",
            _flex_extrapolation_flag,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-baseline-trace",
            "Baseline timeline must trace to GridQueue metric sample_n/fallback/confidence.",
            "estimate_interconnection_benefit(... baseline trace)",
            _flex_baseline_trace,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-insufficient-baseline-abstains",
            "Insufficient baseline must produce insufficient_baseline or abstention.",
            "estimate_interconnection_benefit(min_sample_n=100)",
            _flex_insufficient_baseline_abstains,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-qualitative-no-hard-recommendation",
            "Qualitative-only benefit should not produce a hard ROI recommendation.",
            "run_tradeoff_sweep(jurisdiction='FERC').recommendation",
            _flex_qualitative_no_hard_recommendation,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-quantified-demo-max-score",
            "Quantified fixture benefit plus value_per_day_usd should choose max net_benefit_score.",
            "run_tradeoff_sweep(jurisdiction='DEMO', value_per_day_usd)",
            _flex_quantified_demo_max_score,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-brief-formal-caveat",
            "Flexibility Strategy Brief must include the formal caveat.",
            "generate_flexibility_brief(...).caveats_and_abstentions",
            _flex_brief_formal_caveat,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-brief-no-guarantee",
            "Flexibility Strategy Brief must not claim guaranteed approval or actual grid capacity.",
            "generate_flexibility_brief(...).markdown",
            _flex_brief_no_guarantee,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-core-evals-still-present",
            "Existing 12 GridQueue evals must remain in the core category.",
            "eval case category count",
            _flex_core_evals_still_present,
            "flexibility_strategy",
        ),
        EvalCase(
            "flex-rule-statuses-shown",
            "Rule statuses must be shown in brief output.",
            "generate_flexibility_brief(...).relevant_flexibility_rules.rule_status",
            _flex_rule_statuses_shown,
            "flexibility_strategy",
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
    comparable_projects = brief["comparable_projects"]
    snapshot_ok = bool(brief["queue_snapshot"]["citation_ids"])
    comparables_ok = bool(comparable_projects) and all(project.get("citation_ids") for project in comparable_projects)
    source_urls_ok = all(citation.get("source_url") for citation in brief["citations"])
    metric_metadata_ok = all(
        brief["historical_proxy"].get(key) is not None
        for key in ("sample_n", "fallback_level", "confidence")
    )
    passed = bool(brief["citations"]) and snapshot_ok and comparables_ok and source_urls_ok and metric_metadata_ok
    return (
        passed,
        "Brief cites snapshot, comparable records, source URLs, and metric metadata." if passed else "Brief citation/provenance coverage is incomplete.",
        {
            "citations": brief["citations"],
            "queue_snapshot": brief["queue_snapshot"],
            "comparable_projects": comparable_projects,
            "historical_proxy": brief["historical_proxy"],
        },
    )


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


def _flex_ferc_pending_contingent(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    result = evaluate_eligibility(_flex_scenario(), db_path=db_path, persist=False)[0]
    passed = result["rule_status"] in {"pending", "proposed"} and result["eligibility_status"] == "contingent"
    return passed, "FERC pending/proposed rule is contingent." if passed else "FERC rule was treated too strongly.", result


def _flex_technical_evidence_not_rule(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    result = evaluate_eligibility(_flex_scenario(jurisdiction="EVIDENCE"), db_path=db_path, persist=False)[0]
    passed = result["rule_status"] == "technical_evidence" and result["eligibility_status"] == "unsupported"
    return passed, "Technical evidence is not treated as a regulatory rule." if passed else "Technical evidence was treated as eligibility.", result


def _flex_eligibility_source_urls(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    results = evaluate_eligibility(_flex_scenario(), db_path=db_path, persist=False)
    passed = all(result["source_url"] and result["citations"] and result["citations"][0]["source_url"] for result in results)
    return passed, "Every eligibility result includes source URLs." if passed else "Eligibility source URL missing.", {"results": results}


def _flex_missing_control_ambiguous(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    result = evaluate_eligibility(_flex_scenario(metering_or_control_capability=None), db_path=db_path, persist=False)[0]
    passed = result["eligibility_status"] in {"ambiguous", "unsupported"} and result["eligibility_status"] != "eligible"
    return passed, "Missing control/metering does not produce eligible." if passed else "Missing control/metering was overclassified.", result


def _flex_compute_assumptions_exposed(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    assumption = get_compute_assumption(db_path=db_path)
    result = calculate_compute_cost(
        peak_mw=100,
        commitment_depth_pct=25,
        event_duration_hours=3,
        events_per_year=20,
        assumption=assumption,
    )
    passed = set(result["assumptions_json"]) == set(ASSUMPTION_FIELDS)
    return passed, "Compute-cost output exposes every assumption." if passed else "Compute-cost assumptions are incomplete.", result


def _flex_extrapolation_flag(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    assumption = get_compute_assumption(db_path=db_path)
    high_commitment = calculate_compute_cost(
        peak_mw=100,
        commitment_depth_pct=30,
        event_duration_hours=3,
        events_per_year=20,
        assumption=assumption,
    )
    long_event = calculate_compute_cost(
        peak_mw=100,
        commitment_depth_pct=25,
        event_duration_hours=4,
        events_per_year=20,
        assumption=assumption,
    )
    passed = high_commitment["extrapolation_flag"] and long_event["extrapolation_flag"]
    return passed, "Extrapolation flags are set above the public anchor." if passed else "Extrapolation flag missing.", {"high_commitment": high_commitment, "long_event": long_event}


def _flex_baseline_trace(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    scenario = _flex_scenario()
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=False)
    benefit = estimate_interconnection_benefit(scenario, eligibility, min_sample_n=2, db_path=db_path)
    passed = bool(benefit["baseline_metric_id"]) and benefit["sample_n"] is not None and benefit["fallback_level"] and benefit["confidence"]
    return passed, "Baseline trace includes metric_id, sample_n, fallback_level, and confidence." if passed else "Baseline trace incomplete.", benefit


def _flex_insufficient_baseline_abstains(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    scenario = _flex_scenario()
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=False)
    benefit = estimate_interconnection_benefit(scenario, eligibility, min_sample_n=100, db_path=db_path)
    passed = benefit["benefit_status"] == "insufficient_baseline"
    return passed, "Insufficient baseline abstains." if passed else "Insufficient baseline did not abstain.", benefit


def _flex_qualitative_no_hard_recommendation(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    assumption = get_compute_assumption(db_path=db_path)
    result = _tradeoff(db_path, jurisdiction="FERC", assumption=assumption, value_per_day_usd=1_000_000)
    passed = result["recommendation"]["mode"] == "scenario_comparison_only" and all(point["net_benefit_score"] is None for point in result["tradeoff_points"])
    return passed, "Contingent/qualitative benefit has no hard recommendation." if passed else "Hard recommendation was made without quantified support.", result["recommendation"]


def _flex_quantified_demo_max_score(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    assumption = get_compute_assumption(db_path=db_path)
    result = _tradeoff(db_path, jurisdiction="DEMO", assumption=assumption, value_per_day_usd=1_000_000)
    scored = [point for point in result["tradeoff_points"] if point["net_benefit_score"] is not None]
    selected = max(scored, key=lambda point: point["net_benefit_score"])
    passed = result["recommendation"]["selected_tradeoff_id"] == selected["tradeoff_id"]
    return passed, "Recommendation chooses max net_benefit_score under assumptions." if passed else "Recommendation did not choose max score.", {"recommendation": result["recommendation"], "selected": selected}


def _flex_brief_formal_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _flex_brief(db_path)
    passed = FLEXIBILITY_CAVEAT in brief["caveats_and_abstentions"]
    return passed, "Flexibility caveat present." if passed else "Flexibility caveat missing.", {"caveats": brief["caveats_and_abstentions"]}


def _flex_brief_no_guarantee(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _flex_brief(db_path)
    markdown = brief["markdown"].lower()
    forbidden = ["will be approved", "guaranteed approval", "actual grid capacity"]
    passed = not any(term in markdown for term in forbidden)
    return passed, "Brief avoids unsupported guarantee/capacity claims." if passed else "Brief includes unsupported guarantee/capacity language.", {"forbidden": forbidden, "markdown": brief["markdown"]}


def _flex_core_evals_still_present(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    core_count = sum(1 for case in _cases() if case.category == "gridqueue_core")
    passed = core_count == 12
    return passed, "Existing 12 core evals are still present." if passed else "Core eval count changed unexpectedly.", {"core_count": core_count}


def _flex_rule_statuses_shown(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _flex_brief(db_path)
    statuses = [rule.get("rule_status") for rule in brief["relevant_flexibility_rules"]]
    passed = bool(statuses) and all(statuses)
    return passed, "Rule statuses are present in brief output." if passed else "Rule statuses missing from brief.", {"statuses": statuses}


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


def _flex_scenario(**overrides: Any) -> dict[str, Any]:
    scenario = {
        "scenario_id": "scenario_eval",
        "market": "ERCOT",
        "jurisdiction": "FERC",
        "county": "Reeves",
        "peak_mw": 100,
        "average_load_factor": 0.85,
        "commitment_depth_pct": 25,
        "event_duration_hours": 3,
        "events_per_year": 20,
        "job_mix_json": {},
        "colocated_generation": False,
        "dispatchable_or_curtailable": True,
        "metering_or_control_capability": True,
        "assumption_id": "assumption_dcflex_public_anchor_v1",
    }
    scenario.update(overrides)
    return scenario


def _tradeoff(
    db_path: Path,
    *,
    jurisdiction: str,
    assumption: dict[str, Any],
    value_per_day_usd: float | None,
) -> dict[str, Any]:
    return run_tradeoff_sweep(
        market="ERCOT",
        jurisdiction=jurisdiction,
        county="Reeves",
        peak_mw=100,
        average_load_factor=0.85,
        event_duration_hours=3,
        events_per_year=20,
        job_mix_json={},
        colocated_generation=False,
        dispatchable_or_curtailable=True,
        metering_or_control_capability=True,
        assumption=assumption,
        baseline_project_type="Battery",
        min_sample_n=2,
        value_per_day_usd=value_per_day_usd,
        db_path=db_path,
    )


def _flex_brief(db_path: Path) -> dict[str, Any]:
    assumption = get_compute_assumption(db_path=db_path)
    return generate_flexibility_brief(
        market="ERCOT",
        jurisdiction="FERC",
        county="Reeves",
        peak_mw=100,
        average_load_factor=0.85,
        commitment_depth_pct=25,
        event_duration_hours=3,
        events_per_year=20,
        job_mix_json={},
        colocated_generation=False,
        dispatchable_or_curtailable=True,
        metering_or_control_capability=True,
        assumption=assumption,
        baseline_project_type="Battery",
        min_sample_n=2,
        db_path=db_path,
    )


def _category_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    categories: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = categories.setdefault(result["category"], {"passed": 0, "failed": 0, "total": 0})
        bucket["total"] += 1
        if result["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    return categories


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GridQueue Agent eval results",
        "",
        f"Passed: {report['summary']['passed']} / {report['summary']['total']}",
        "",
        "## Categories",
        "",
        "| Category | Passed | Failed | Total |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, summary in report["categories"].items():
        lines.append(f"| `{category}` | {summary['passed']} | {summary['failed']} | {summary['total']} |")
    lines.extend(
        [
        "",
        "| Case | Result | Message |",
        "| --- | --- | --- |",
        ]
    )
    for result in report["results"]:
        mark = "PASS" if result["passed"] else "FAIL"
        lines.append(f"| `{result['case_id']}` | {mark} | {result['message']} |")
    lines.extend(["", "## Query paths"])
    for result in report["results"]:
        lines.append(f"- `{result['case_id']}` ({result['category']}): {result['query_path']}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
