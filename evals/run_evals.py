from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
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
from app.services.procurement import list_lead_times, seed_lead_time_kb
from app.services.time_to_power import generate_time_to_power_brief, generate_time_to_power_estimate, seed_time_to_power_fixtures
from app.services.time_to_power.brief import TIME_TO_POWER_CAVEAT
from app.services.watcher import (
    capture_regulatory_snapshots,
    latest_digest,
    rank_change_events,
    run_monthly_watcher,
    seed_watch_sources,
)
from app.services.watcher.digest import WATCHER_CAVEAT, list_change_events


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evals" / "results"
EVAL_DB = RESULTS_DIR / "eval.duckdb"
_WATCHER_RUN_DBS: set[str] = set()
_TTP_SEEDED_DBS: set[str] = set()
_TTP_ESTIMATE_CACHE: dict[str, dict[str, Any]] = {}
_TTP_BRIEF_CACHE: dict[str, dict[str, Any]] = {}


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
    seed_watch_sources(EVAL_DB)
    seed_lead_time_kb(EVAL_DB)
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
        EvalCase(
            "watcher-digest-lines-trace",
            "Every digest line traces to a change_event and source_url or snapshot id.",
            "run_monthly_watcher(...).digest sections",
            _watcher_digest_lines_trace,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-ambiguous-not-hard-alert",
            "Ambiguous entity-resolution event does not become a hard new/withdrawn alert.",
            "change_events WHERE event_type='ambiguous_match'",
            _watcher_ambiguous_not_hard_alert,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-materiality-deterministic",
            "Materiality ranking is deterministic for a fixed event set.",
            "rank_change_events(fixed events)",
            _watcher_materiality_deterministic,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-parse-failure-manual-review",
            "Parse failure produces manual-review flag instead of fabricated summary.",
            "change_events WHERE event_type='source_parse_failed'",
            _watcher_parse_failure_manual_review,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-source-hash-change-review",
            "Regulatory source hash change produces rule_source_changed or rule_needs_review.",
            "capture_regulatory_snapshots(fixture_variant='changed')",
            _watcher_source_hash_change_review,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-no-fabricated-change",
            "Digest does not fabricate project/provision/capacity/rule changes outside change_events.",
            "digest sections joined to change_events",
            _watcher_no_fabricated_change,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-rule-status-remains-pending",
            "Rule status remains proposed/pending unless source diff supports review.",
            "iso_flexibility_rules.status plus rule_needs_review event",
            _watcher_rule_status_remains_pending,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-top-n-materiality",
            "Top N events are selected by deterministic materiality score.",
            "digest.top_event_ids ordered by change_events.materiality_score",
            _watcher_top_n_materiality,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-suppressed-visible",
            "Suppressed ambiguous/noise events appear in the suppressed section.",
            "digest.suppressed_ambiguous",
            _watcher_suppressed_visible,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-required-caveat",
            "Digest includes required public-data monitoring caveat.",
            "digest.caveats",
            _watcher_required_caveat,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-core-evals-still-pass",
            "Existing 12 GridQueue evals remain in the core category.",
            "eval case category count",
            _watcher_core_evals_still_pass,
            "monthly_watcher",
        ),
        EvalCase(
            "watcher-flex-evals-still-pass",
            "Existing 14 Flexibility Strategy evals remain in the flexibility category.",
            "eval case category count",
            _watcher_flex_evals_still_pass,
            "monthly_watcher",
        ),
        EvalCase(
            "lead-time-source-urls",
            "Every lead-time figure has source_url.",
            "list_lead_times().source_url",
            _lead_time_source_urls,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-as-of-date",
            "Every lead-time figure has as_of_date.",
            "list_lead_times().as_of_date",
            _lead_time_as_of_date,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-range-not-point",
            "Lead-time output is a range, not a bare point claim.",
            "equipment_lead_times low/high months",
            _lead_time_range_not_point,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-stale-warning",
            "Stale source triggers is_stale or warning.",
            "list_lead_times(today=2026-06-05).is_stale",
            _lead_time_stale_warning,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-conflicts-not-collapsed",
            "Conflicting sources are not collapsed into one fake precise number.",
            "insert conflicting fixture row then list_lead_times",
            _lead_time_conflicts_not_collapsed,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-no-fabricated-equipment",
            "No fabricated equipment item appears in seeded scaffold output.",
            "list_lead_times().equipment_class",
            _lead_time_no_fabricated_equipment,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-no-quote-language",
            "Lead-time output avoids procurement quote language.",
            "list_lead_times().caveats and notes",
            _lead_time_no_quote_language,
            "lead_time_scaffold",
        ),
        EvalCase(
            "lead-time-docs-label-scaffold",
            "README/docs clearly label lead-time layer as scaffold.",
            "README.md and docs/POST_NTP_LEAD_TIME.md",
            _lead_time_docs_label_scaffold,
            "lead_time_scaffold",
        ),
        EvalCase(
            "ttp-baseline-provenance",
            "Baseline timeline includes metric_id, sample_n, fallback_level, and confidence.",
            "generate_time_to_power_estimate().baseline",
            _ttp_baseline_provenance,
            "time_to_power",
        ),
        EvalCase(
            "ttp-insufficient-baseline-abstains",
            "Insufficient baseline sample triggers insufficient_interconnection_baseline.",
            "generate_time_to_power_estimate(min_sample_n=100)",
            _ttp_insufficient_baseline_abstains,
            "time_to_power",
        ),
        EvalCase(
            "ttp-proposed-flex-contingent",
            "Proposed/pending flexibility rule produces contingent status, not final timeline improvement.",
            "generate_time_to_power_estimate(jurisdiction='FERC').flexibility_adjusted",
            _ttp_proposed_flex_contingent,
            "time_to_power",
        ),
        EvalCase(
            "ttp-technical-evidence-not-regulation",
            "Technical evidence is not treated as a regulatory rule.",
            "generate_time_to_power_estimate(jurisdiction='EVIDENCE').flexibility_adjusted",
            _ttp_technical_evidence_not_regulation,
            "time_to_power",
        ),
        EvalCase(
            "ttp-flex-no-procurement-reduction",
            "Flexibility does not reduce procurement lead time by default.",
            "generate_time_to_power_estimate(jurisdiction='DEMO') procurement component",
            _ttp_flex_no_procurement_reduction,
            "time_to_power",
        ),
        EvalCase(
            "ttp-procurement-ranges",
            "Procurement lead times are ranges, never bare point claims.",
            "estimate.procurement_critical_path.lead_time_rows",
            _ttp_procurement_ranges,
            "time_to_power",
        ),
        EvalCase(
            "ttp-procurement-source-metadata",
            "Every procurement lead time has source_url and as_of_date.",
            "estimate.procurement_critical_path.lead_time_rows source fields",
            _ttp_procurement_source_metadata,
            "time_to_power",
        ),
        EvalCase(
            "ttp-stale-warning",
            "Stale lead-time source triggers stale warning.",
            "estimate.procurement_critical_path.stale_flag",
            _ttp_stale_warning,
            "time_to_power",
        ),
        EvalCase(
            "ttp-conflict-warning",
            "Conflicting lead-time sources trigger conflict flag and are not collapsed into fake precision.",
            "estimate.procurement_critical_path.conflict_flag and rows",
            _ttp_conflict_warning,
            "time_to_power",
        ),
        EvalCase(
            "ttp-binding-high-end",
            "Critical path chooses binding equipment by highest high-end lead time.",
            "estimate.procurement_critical_path.binding_equipment_class",
            _ttp_binding_high_end,
            "time_to_power",
        ),
        EvalCase(
            "ttp-serial-math",
            "Serial timeline math is correct.",
            "estimate serial component arithmetic",
            _ttp_serial_math,
            "time_to_power",
        ),
        EvalCase(
            "ttp-overlap-math",
            "Overlap timeline math is correct.",
            "estimate overlap component arithmetic",
            _ttp_overlap_math,
            "time_to_power",
        ),
        EvalCase(
            "ttp-at-risk-caveat",
            "At-risk overlap strategy includes explicit caveat.",
            "generate_time_to_power_estimate(procurement_strategy='at_risk_overlap').caveats",
            _ttp_at_risk_caveat,
            "time_to_power",
        ),
        EvalCase(
            "ttp-required-caveat",
            "Time-to-Power Brief includes required caveat.",
            "generate_time_to_power_brief().caveats_and_abstentions",
            _ttp_required_caveat,
            "time_to_power",
        ),
        EvalCase(
            "ttp-key-number-provenance",
            "Every key number in the brief has provenance.",
            "brief baseline/procurement/commissioning citations and assumptions",
            _ttp_key_number_provenance,
            "time_to_power",
        ),
        EvalCase(
            "ttp-no-guarantee-language",
            "Brief does not claim guaranteed energization or interconnection approval.",
            "brief.markdown",
            _ttp_no_guarantee_language,
            "time_to_power",
        ),
        EvalCase(
            "ttp-demo-end-to-end",
            "Fixture demo runs end-to-end.",
            "generate_time_to_power_brief()",
            _ttp_demo_end_to_end,
            "time_to_power",
        ),
        EvalCase(
            "ttp-core-evals-still-pass",
            "Existing GridQueue core evals still pass.",
            "eval case category count",
            _ttp_core_evals_still_pass,
            "time_to_power",
        ),
        EvalCase(
            "ttp-flex-evals-still-pass",
            "Existing Flexibility Strategy evals still pass.",
            "eval case category count",
            _ttp_flex_evals_still_pass,
            "time_to_power",
        ),
        EvalCase(
            "ttp-watcher-evals-still-pass",
            "Existing Watcher evals still pass.",
            "eval case category count",
            _ttp_watcher_evals_still_pass,
            "time_to_power",
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


def _watcher_digest_lines_trace(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    lines = _digest_lines(digest)
    passed = bool(lines) and all(line.get("change_event_id") and (line.get("source_url") or line.get("source_trace")) for line in lines)
    return passed, "Every digest line has event and source trace." if passed else "Digest line trace missing.", {"line_count": len(lines), "lines": lines[:5]}


def _watcher_ambiguous_not_hard_alert(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    _watcher_digest(db_path)
    events = [event for event in list_change_events(db_path=db_path) if event["event_type"] == "ambiguous_match"]
    passed = bool(events) and all(event["is_ambiguous"] and not event["is_hard_alert"] for event in events)
    return passed, "Ambiguous events are visible but non-hard-alert." if passed else "Ambiguous event became hard alert.", {"events": events[:5]}


def _watcher_materiality_deterministic(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    events = [
        {"change_event_id": "a", "event_domain": "queue", "event_type": "new_project", "entity_or_provision": "A", "before_json": {}, "after_json": {"capacity_mw": 25, "county": "Reeves"}, "confidence": 1.0, "is_ambiguous": False},
        {"change_event_id": "b", "event_domain": "queue", "event_type": "withdrawn_project", "entity_or_provision": "B", "before_json": {}, "after_json": {"capacity_mw": 100, "county": "Reeves"}, "confidence": 1.0, "is_ambiguous": False},
        {"change_event_id": "c", "event_domain": "queue", "event_type": "ambiguous_match", "entity_or_provision": "C", "before_json": {}, "after_json": {"capacity_mw": 500, "county": "Reeves"}, "confidence": 0.5, "is_ambiguous": True},
    ]
    once = rank_change_events(events, top_n=2)
    twice = rank_change_events(events, top_n=2)
    passed = once == twice and once["top_events"][0]["change_event_id"] == "b" and once["suppressed_events"][0]["change_event_id"] == "c"
    return passed, "Materiality ranking is deterministic." if passed else "Materiality ranking drifted.", {"ranked": once}


def _watcher_parse_failure_manual_review(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    failures = digest["parse_failures"]
    markdown = digest["markdown"].lower()
    passed = bool(failures) and "could not be parsed" in failures[0]["explanation"].lower() and "failed content is not summarized as parsed" in markdown
    return passed, "Parse failure is manual review only." if passed else "Parse failure was not handled conservatively.", {"failures": failures}


def _watcher_source_hash_change_review(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    _watcher_digest(db_path)
    changed = capture_regulatory_snapshots(mode="fixture", fixture_variant="changed", db_path=db_path)
    event_types = {event["event_type"] for event in changed["change_events"]}
    passed = bool(event_types & {"rule_source_changed", "rule_needs_review"})
    return passed, "Changed source emitted source-change or review event." if passed else "Changed source emitted no reviewable event.", {"event_types": sorted(event_types)}


def _watcher_no_fabricated_change(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    event_ids = {event["change_event_id"] for event in list_change_events(db_path=db_path)}
    lines = _digest_lines(digest)
    passed = all(line["change_event_id"] in event_ids for line in lines) and "fictional" not in digest["markdown"].lower()
    return passed, "Digest only lists persisted change_events." if passed else "Digest contains unbacked line.", {"line_count": len(lines)}


def _watcher_rule_status_remains_pending(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    _watcher_digest(db_path)
    capture_regulatory_snapshots(mode="fixture", fixture_variant="changed", db_path=db_path)
    with connect(db_path) as con:
        status = con.execute("SELECT status FROM iso_flexibility_rules WHERE rule_id='rule_ferc_rm26_4_anopr'").fetchone()[0]
        review_count = con.execute("SELECT COUNT(*) FROM change_events WHERE event_type='rule_needs_review'").fetchone()[0]
    passed = status in {"pending", "proposed"} and review_count >= 1
    return passed, "Rule status remains conservative and review event exists." if passed else "Rule status changed silently.", {"status": status, "review_count": review_count}


def _watcher_top_n_materiality(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    top_ids = digest["top_event_ids"]
    scores = []
    with connect(db_path) as con:
        for event_id in top_ids:
            row = con.execute("SELECT materiality_score FROM change_events WHERE change_event_id = ?", [event_id]).fetchone()
            scores.append(row[0])
    passed = bool(scores) and scores == sorted(scores, reverse=True)
    return passed, "Top event ids follow descending materiality." if passed else "Top N ordering is not materiality sorted.", {"scores": scores}


def _watcher_suppressed_visible(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    passed = bool(digest["suppressed_ambiguous"]) and all(not row["is_hard_alert"] for row in digest["suppressed_ambiguous"])
    return passed, "Suppressed ambiguous events are visible." if passed else "Suppressed section missing ambiguity.", {"suppressed": digest["suppressed_ambiguous"][:5]}


def _watcher_required_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    digest = _watcher_digest(db_path)
    passed = WATCHER_CAVEAT in digest["caveats"]
    return passed, "Watcher caveat present." if passed else "Watcher caveat missing.", {"caveats": digest["caveats"]}


def _watcher_core_evals_still_pass(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    core_count = sum(1 for case in _cases() if case.category == "gridqueue_core")
    passed = core_count == 12
    return passed, "Existing core eval category remains intact." if passed else "Core eval category count changed.", {"core_count": core_count}


def _watcher_flex_evals_still_pass(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    flex_count = sum(1 for case in _cases() if case.category == "flexibility_strategy")
    passed = flex_count == 14
    return passed, "Existing flexibility eval category remains intact." if passed else "Flex eval category count changed.", {"flex_count": flex_count}


def _lead_time_source_urls(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    passed = bool(rows) and all(row["source_url"] for row in rows)
    return passed, "Lead-time rows include source URLs." if passed else "Lead-time source URL missing.", {"rows": rows}


def _lead_time_as_of_date(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    passed = bool(rows) and all(row["as_of_date"] for row in rows)
    return passed, "Lead-time rows include as_of_date." if passed else "Lead-time as_of_date missing.", {"rows": rows}


def _lead_time_range_not_point(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    passed = bool(rows) and all(row["lead_time_low_months"] < row["lead_time_high_months"] for row in rows)
    return passed, "Lead-time outputs are ranges." if passed else "Lead-time output collapsed to a point.", {"rows": rows}


def _lead_time_stale_warning(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    passed = bool(rows) and any(row["is_stale"] for row in rows)
    return passed, "Staleness is flagged for older public-source rows." if passed else "No stale flag found.", {"rows": rows}


def _lead_time_conflicts_not_collapsed(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    _insert_lead_time_conflict(db_path)
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    lpt_rows = [row for row in rows if row["equipment_class"] == "Large Power Transformer"]
    ranges = {(row["lead_time_low_months"], row["lead_time_high_months"]) for row in lpt_rows}
    passed = len(lpt_rows) >= 2 and len(ranges) >= 2 and all(row["has_conflict"] for row in lpt_rows)
    return passed, "Conflicting ranges stay separate and flagged." if passed else "Conflicting ranges were collapsed.", {"ranges": sorted(ranges)}


def _lead_time_no_fabricated_equipment(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    equipment = {row["equipment_class"] for row in rows}
    passed = equipment == {"Large Power Transformer"}
    return passed, "Only the seeded LPT equipment class appears." if passed else "Unexpected equipment class found.", {"equipment": sorted(equipment)}


def _lead_time_no_quote_language(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))
    text = json.dumps(rows).lower()
    forbidden = ["this is a firm quote", "binding quote", "will deliver by", "is an oem commitment"]
    passed = not any(term in text for term in forbidden) and "not a procurement quote" in text
    return passed, "Lead-time output avoids quote language." if passed else "Quote-like language found.", {"forbidden": forbidden}


def _lead_time_docs_label_scaffold(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc_path = ROOT / "docs" / "POST_NTP_LEAD_TIME.md"
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    passed = "Post-NTP Lead-Time scaffold is an early knowledge-base demo" in readme and "scaffold" in doc_text.lower()
    return passed, "Docs label lead-time layer as scaffold." if passed else "Lead-time scaffold positioning missing.", {"doc_exists": doc_path.exists()}


def _ttp_baseline_provenance(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    baseline = _ttp_estimate(db_path)["baseline"]
    passed = all(baseline.get(key) for key in ["metric_id", "sample_n", "fallback_level", "confidence"])
    return passed, "Baseline includes metric_id/sample_n/fallback/confidence." if passed else "Baseline provenance missing.", baseline


def _ttp_insufficient_baseline_abstains(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    estimate = _ttp_estimate(db_path, min_sample_n=100)
    passed = estimate["status"] == "insufficient_interconnection_baseline" and estimate["baseline"]["baseline_low_days"] is None
    return passed, "Insufficient baseline abstains." if passed else "Insufficient baseline did not abstain.", {"status": estimate["status"], "baseline": estimate["baseline"]}


def _ttp_proposed_flex_contingent(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    flex = _ttp_estimate(db_path, jurisdiction="FERC")["flexibility_adjusted"]
    passed = flex["rule_status"] in {"pending", "proposed"} and flex["benefit_status"] == "contingent" and flex["interconnection_with_flex_low_days"] is None
    return passed, "Proposed/pending flex remains contingent without days-saved math." if passed else "Proposed flex was overclaimed.", flex


def _ttp_technical_evidence_not_regulation(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    flex = _ttp_estimate(db_path, jurisdiction="EVIDENCE")["flexibility_adjusted"]
    passed = flex["rule_status"] == "technical_evidence" and flex["benefit_status"] == "unsupported"
    return passed, "Technical evidence is not regulation." if passed else "Technical evidence was treated as regulatory support.", flex


def _ttp_flex_no_procurement_reduction(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    estimate = _ttp_estimate(db_path, jurisdiction="DEMO", commitment_depth_pct=20)
    procurement = estimate["procurement_critical_path"]
    no_flex_minus_flex = round(estimate["no_flex_serial_low_days"] - estimate["flex_serial_low_days"], 2)
    baseline_minus_flex = round(
        estimate["baseline"]["baseline_low_days"] - estimate["flexibility_adjusted"]["interconnection_with_flex_low_days"],
        2,
    )
    passed = procurement["procurement_low_days"] == procurement["procurement_low_days"] and no_flex_minus_flex == baseline_minus_flex
    return passed, "Flex benefit changes interconnection component only; procurement range is unchanged." if passed else "Flex affected procurement path.", {"estimate": estimate}


def _ttp_procurement_ranges(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = _ttp_estimate(db_path)["procurement_critical_path"]["lead_time_rows"]
    passed = bool(rows) and all(row["lead_time_low_months"] < row["lead_time_high_months"] for row in rows)
    return passed, "Procurement lead-time rows are ranges." if passed else "Procurement row collapsed to a point.", {"rows": rows}


def _ttp_procurement_source_metadata(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    rows = _ttp_estimate(db_path)["procurement_critical_path"]["lead_time_rows"]
    passed = bool(rows) and all(row.get("source_url") and row.get("as_of_date") for row in rows)
    return passed, "Every procurement row has source_url and as_of_date." if passed else "Procurement source metadata missing.", {"rows": rows}


def _ttp_stale_warning(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    critical = _ttp_estimate(db_path)["procurement_critical_path"]
    passed = critical["stale_flag"] and any("stale" in caveat.lower() for caveat in critical["caveats"])
    return passed, "Stale lead-time source is flagged." if passed else "Stale warning missing.", critical


def _ttp_conflict_warning(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    critical = _ttp_estimate(db_path)["procurement_critical_path"]
    ranges = {(row["equipment_class"], row["lead_time_low_months"], row["lead_time_high_months"]) for row in critical["lead_time_rows"]}
    passed = critical["conflict_flag"] and len(ranges) > 1 and any("conflict" in caveat.lower() for caveat in critical["caveats"])
    return passed, "Conflicting ranges are preserved and flagged." if passed else "Conflict warning missing or collapsed.", {"critical": critical}


def _ttp_binding_high_end(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    critical = _ttp_estimate(db_path)["procurement_critical_path"]
    max_high = max(row["lead_time_high_months"] for row in critical["lead_time_rows"])
    passed = critical["binding_lead_time_high_months"] == max_high and critical["binding_equipment_class"] == "Large Power Transformer"
    return passed, "Binding equipment follows highest high-end lead time." if passed else "Binding equipment selection is wrong.", critical


def _ttp_serial_math(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    estimate = _ttp_estimate(db_path)
    expected = round(
        estimate["baseline"]["baseline_low_days"]
        + estimate["procurement_critical_path"]["procurement_low_days"]
        + estimate["commissioning_assumption"]["default_commissioning_low_days"]
        + estimate["commissioning_assumption"]["energization_buffer_low_days"],
        2,
    )
    passed = estimate["no_flex_serial_low_days"] == expected
    return passed, "Serial timeline math is correct." if passed else "Serial math mismatch.", {"expected": expected, "actual": estimate["no_flex_serial_low_days"]}


def _ttp_overlap_math(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    estimate = _ttp_estimate(db_path)
    expected = round(
        max(estimate["baseline"]["baseline_high_days"], estimate["procurement_critical_path"]["procurement_high_days"])
        + estimate["commissioning_assumption"]["default_commissioning_high_days"]
        + estimate["commissioning_assumption"]["energization_buffer_high_days"],
        2,
    )
    passed = estimate["no_flex_overlap_high_days"] == expected
    return passed, "Overlap timeline math is correct." if passed else "Overlap math mismatch.", {"expected": expected, "actual": estimate["no_flex_overlap_high_days"]}


def _ttp_at_risk_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    estimate = _ttp_estimate(db_path, procurement_strategy="at_risk_overlap")
    passed = estimate["selected_case"] == "no_flex_overlap" and any("At-risk overlap" in caveat for caveat in estimate["caveats"])
    return passed, "At-risk overlap selected case is caveated." if passed else "At-risk caveat missing.", {"selected_case": estimate["selected_case"], "caveats": estimate["caveats"]}


def _ttp_required_caveat(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _ttp_brief(db_path)
    passed = TIME_TO_POWER_CAVEAT in brief["caveats_and_abstentions"] and TIME_TO_POWER_CAVEAT in brief["markdown"]
    return passed, "Required Time-to-Power caveat present." if passed else "Required caveat missing.", {"caveats": brief["caveats_and_abstentions"]}


def _ttp_key_number_provenance(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _ttp_brief(db_path)
    estimate = brief["estimate"]
    passed = (
        bool(estimate["baseline"]["metric_id"])
        and bool(estimate["baseline"]["source_snapshot_id"])
        and bool(estimate["procurement_critical_path"]["citations"])
        and estimate["assumptions"]["procurement_assumptions"]["days_per_month"] == 30.4375
        and bool(estimate["commissioning_assumption"]["source_url"])
        and bool(estimate["reproducibility_trace"])
    )
    return passed, "Key numbers have metric/source/assumption provenance." if passed else "Key number provenance missing.", {"estimate": estimate}


def _ttp_no_guarantee_language(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    markdown = _ttp_brief(db_path)["markdown"].lower()
    forbidden = ["will be energized", "guaranteed energization", "guaranteed interconnection approval", "will receive interconnection approval"]
    passed = not any(term in markdown for term in forbidden)
    return passed, "Brief avoids guarantee language." if passed else "Guarantee language found.", {"forbidden": forbidden}


def _ttp_demo_end_to_end(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    brief = _ttp_brief(db_path)
    path = Path(brief["markdown_path"])
    passed = brief["title"].startswith("Time-to-Power Brief") and path.exists() and bool(brief["citations"])
    return passed, "Fixture demo generated a complete brief artifact." if passed else "Fixture demo failed.", {"markdown_path": str(path), "brief_id": brief["brief_id"]}


def _ttp_core_evals_still_pass(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    core_count = sum(1 for case in _cases() if case.category == "gridqueue_core")
    passed = core_count == 12
    return passed, "Existing core eval category remains intact." if passed else "Core eval category count changed.", {"core_count": core_count}


def _ttp_flex_evals_still_pass(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    flex_count = sum(1 for case in _cases() if case.category == "flexibility_strategy")
    passed = flex_count == 14
    return passed, "Existing flexibility eval category remains intact." if passed else "Flex eval category count changed.", {"flex_count": flex_count}


def _ttp_watcher_evals_still_pass(db_path: Path) -> tuple[bool, str, dict[str, Any]]:
    watcher_count = sum(1 for case in _cases() if case.category == "monthly_watcher")
    passed = watcher_count == 12
    return passed, "Existing watcher eval category remains intact." if passed else "Watcher eval category count changed.", {"watcher_count": watcher_count}


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


def _watcher_digest(db_path: Path) -> dict[str, Any]:
    key = str(db_path)
    if key not in _WATCHER_RUN_DBS:
        run_monthly_watcher(
            mode="fixture",
            period_start="2026-05-01",
            period_end="2026-05-31",
            top_n=10,
            db_path=db_path,
        )
        _WATCHER_RUN_DBS.add(key)
    digest = latest_digest(db_path)
    if not digest:
        raise AssertionError("Watcher digest was not generated.")
    return digest


def _digest_lines(digest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *digest["top_queue_changes"],
        *digest["top_regulatory_changes"],
        *digest["flexibility_rule_watch"],
        *digest["suppressed_ambiguous"],
        *digest["parse_failures"],
    ]


def _insert_lead_time_conflict(db_path: Path) -> None:
    with connect(db_path) as con:
        exists = con.execute(
            "SELECT COUNT(*) FROM equipment_lead_times WHERE lead_time_id = 'lead_eval_conflict'"
        ).fetchone()[0]
        if exists:
            return
        con.execute(
            """
            INSERT INTO lead_time_sources
            (lead_time_source_id, source_name, source_url, source_type, publication_date,
             retrieved_at, content_hash, notes, created_at)
            VALUES ('lead_src_eval_conflict', 'Synthetic eval conflict source',
                    'synthetic://gridqueue-agent/evals/lead-time-conflict', 'manual_fixture',
                    '2026-01-01', CURRENT_TIMESTAMP, 'eval-hash',
                    'Eval-only conflicting range to verify non-collapse behavior.', CURRENT_TIMESTAMP)
            """
        )
        con.execute(
            """
            INSERT INTO equipment_lead_times
            (lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
             lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
             is_stale, stale_threshold_months, notes, created_at, updated_at)
            VALUES ('lead_eval_conflict', 'Large Power Transformer',
                    'Transmission-class / high-voltage recovery transformer', 30, 48,
                    '2026-01-01', 'lead_src_eval_conflict',
                    'synthetic://gridqueue-agent/evals/lead-time-conflict', 'manual_fixture',
                    'low', FALSE, 18, 'Eval-only conflicting range.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )


def _ensure_ttp_seeded(db_path: Path) -> None:
    key = str(db_path)
    if key not in _TTP_SEEDED_DBS:
        seed_time_to_power_fixtures(reset_core=False, db_path=db_path)
        _TTP_SEEDED_DBS.add(key)


def _ttp_estimate(db_path: Path, **overrides: Any) -> dict[str, Any]:
    _ensure_ttp_seeded(db_path)
    key = f"{db_path}|estimate|{json.dumps(overrides, sort_keys=True, default=str)}"
    if key not in _TTP_ESTIMATE_CACHE:
        _TTP_ESTIMATE_CACHE[key] = generate_time_to_power_estimate(db_path=db_path, **overrides)
    return _TTP_ESTIMATE_CACHE[key]


def _ttp_brief(db_path: Path, **overrides: Any) -> dict[str, Any]:
    _ensure_ttp_seeded(db_path)
    key = f"{db_path}|brief|{json.dumps(overrides, sort_keys=True, default=str)}"
    if key not in _TTP_BRIEF_CACHE:
        _TTP_BRIEF_CACHE[key] = generate_time_to_power_brief(db_path=db_path, **overrides)
    return _TTP_BRIEF_CACHE[key]


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
