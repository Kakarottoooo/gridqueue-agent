from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility.tradeoff import run_tradeoff_sweep
from app.services.utils import new_id, stable_json, utcnow


FLEXIBILITY_CAVEAT = (
    "This is a public-data scenario analysis, not a formal interconnection study, deliverability study, "
    "power-flow result, legal opinion, financial advice, runtime curtailment controller, or guarantee of interconnection approval."
)


def generate_flexibility_brief(
    *,
    market: str,
    jurisdiction: str,
    county: str | None,
    peak_mw: float,
    average_load_factor: float,
    commitment_depth_pct: float,
    event_duration_hours: float,
    events_per_year: int,
    job_mix_json: dict[str, Any],
    colocated_generation: bool,
    dispatchable_or_curtailable: bool | None,
    metering_or_control_capability: bool | None,
    assumption: dict[str, Any],
    baseline_project_type: str = "Battery",
    min_sample_n: int = 30,
    value_per_day_usd: float | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    sweep = run_tradeoff_sweep(
        market=market,
        jurisdiction=jurisdiction,
        county=county,
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        event_duration_hours=event_duration_hours,
        events_per_year=events_per_year,
        job_mix_json=job_mix_json,
        colocated_generation=colocated_generation,
        dispatchable_or_curtailable=dispatchable_or_curtailable,
        metering_or_control_capability=metering_or_control_capability,
        assumption=assumption,
        baseline_project_type=baseline_project_type,
        min_sample_n=min_sample_n,
        value_per_day_usd=value_per_day_usd,
        commitment_levels=sorted({0, 5, 10, 15, 20, 25, 30, 40, 50, commitment_depth_pct}),
        db_path=db_path,
    )
    selected = _select_point(sweep, commitment_depth_pct)
    citations = _citations(sweep)
    caveats = _caveats(sweep, selected)
    result = {
        "title": "Flexibility Strategy Brief",
        "executive_summary": _executive_summary(sweep, selected),
        "input_scenario": {
            "market": market,
            "jurisdiction": jurisdiction,
            "county": county,
            "peak_mw": peak_mw,
            "average_load_factor": average_load_factor,
            "commitment_depth_pct": commitment_depth_pct,
            "event_duration_hours": event_duration_hours,
            "events_per_year": events_per_year,
            "job_mix_json": job_mix_json,
            "colocated_generation": colocated_generation,
            "dispatchable_or_curtailable": dispatchable_or_curtailable,
            "metering_or_control_capability": metering_or_control_capability,
        },
        "relevant_flexibility_rules": selected["eligibility_results"],
        "eligibility_assessment": selected["eligibility_results"],
        "compute_cost_estimate": selected["compute_cost"],
        "interconnection_benefit_assessment": selected["benefit"],
        "commitment_tradeoff_table": [
            {
                "tradeoff_id": point["tradeoff_id"],
                "commitment_depth_pct": point["commitment_depth_pct"],
                "annual_curtailed_mwh": point["compute_cost"]["annual_curtailed_mwh"],
                "estimated_compute_cost_usd": point["compute_cost"]["estimated_compute_cost_usd"],
                "estimated_timeline_delta_days": point["benefit"]["estimated_timeline_delta_days"],
                "benefit_status": point["benefit"]["benefit_status"],
                "net_benefit_score": point["net_benefit_score"],
            }
            for point in sweep["tradeoff_points"]
        ],
        "recommendation": sweep["recommendation"],
        "assumptions": {
            "compute_cost_assumption": assumption,
            "value_per_day_usd": value_per_day_usd,
            "baseline_project_type": baseline_project_type,
            "min_sample_n": min_sample_n,
        },
        "citations": citations,
        "reproducibility_trace": [
            f"seed_rules: iso_flexibility_rules filtered by jurisdiction={jurisdiction}",
            f"compute_cost: annual_curtailed_mwh = peak_mw * commitment_depth_pct / 100 * event_duration_hours * events_per_year -> {selected['compute_cost']['annual_curtailed_mwh']}",
            f"baseline_metric: metric_id={selected['benefit']['baseline_metric_id']}, sample_n={selected['benefit']['sample_n']}, fallback_level={selected['benefit']['fallback_level']}, confidence={selected['benefit']['confidence']}",
            f"recommendation_mode: {sweep['recommendation']['mode']}",
        ],
        "caveats_and_abstentions": caveats,
    }
    result["markdown"] = _to_markdown(result)
    brief_id = new_id("flexbrief")
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO flexibility_briefs
            (brief_id, scenario_id, selected_tradeoff_id, brief_json, citations_json,
             assumptions_json, reproducibility_trace_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                brief_id,
                sweep["scenario"]["scenario_id"],
                selected["tradeoff_id"],
                stable_json(result),
                stable_json(citations),
                stable_json(result["assumptions"]),
                stable_json(result["reproducibility_trace"]),
                utcnow(),
            ],
        )
    result["brief_id"] = brief_id
    result["scenario_id"] = sweep["scenario"]["scenario_id"]
    return result


def _select_point(sweep: dict[str, Any], commitment_depth_pct: float) -> dict[str, Any]:
    return min(
        sweep["tradeoff_points"],
        key=lambda point: abs(float(point["commitment_depth_pct"]) - float(commitment_depth_pct)),
    )


def _citations(sweep: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    citations = []
    for point in sweep["tradeoff_points"]:
        for result in point["eligibility_results"]:
            for citation in result["citations"]:
                key = citation["source_url"]
                if key not in seen:
                    seen.add(key)
                    citations.append(citation)
    anchor = sweep["assumption"].get("evidence_anchor_json", {})
    if anchor.get("source_url") and anchor["source_url"] not in seen:
        citations.append(
            {
                "citation_label": "Compute flexibility evidence anchor",
                "citation_text": "Assumption anchor for extrapolation flags; scenario economics are user-provided assumptions.",
                "source_url": anchor["source_url"],
            }
        )
    return citations


def _caveats(sweep: dict[str, Any], selected: dict[str, Any]) -> list[str]:
    caveats = [FLEXIBILITY_CAVEAT]
    statuses = {result["rule_status"] for result in selected["eligibility_results"]}
    if statuses - {"approved", "final"}:
        caveats.append("One or more relevant records are proposed, pending, directed, context-only, technical evidence, or otherwise non-final.")
    if selected["compute_cost"]["extrapolation_flag"]:
        caveats.append(selected["compute_cost"]["extrapolation_reason"])
    if selected["benefit"]["benefit_status"] != "quantified":
        caveats.append("Timeline benefit is not quantified because the baseline or rule evidence does not support a bounded estimate.")
    if sweep["recommendation"]["mode"] == "scenario_comparison_only":
        caveats.append("No hard recommendation is made without quantified benefit evidence and a value-per-day assumption.")
    return caveats


def _executive_summary(sweep: dict[str, Any], selected: dict[str, Any]) -> list[str]:
    first_rule = selected["eligibility_results"][0] if selected["eligibility_results"] else None
    summary = [
        f"Scenario offers {selected['commitment_depth_pct']}% curtailable load for {selected['compute_cost']['annual_curtailed_mwh']} annual MWh under explicit assumptions.",
        f"Estimated compute cost is ${selected['compute_cost']['estimated_compute_cost_usd']:,.2f}.",
        f"Baseline trace uses sample_n={selected['benefit']['sample_n']}, fallback_level={selected['benefit']['fallback_level']}, confidence={selected['benefit']['confidence']}.",
    ]
    if first_rule:
        summary.append(
            f"Most relevant rule/evidence status is {first_rule['rule_status']} with eligibility_status={first_rule['eligibility_status']}."
        )
    summary.append(sweep["recommendation"]["message"])
    return summary


def _to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        "## Executive summary",
        *[f"- {item}" for item in result["executive_summary"]],
        "",
        "## Input scenario",
        f"- Jurisdiction: {result['input_scenario']['jurisdiction']}",
        f"- Peak MW: {result['input_scenario']['peak_mw']}",
        f"- Commitment depth: {result['input_scenario']['commitment_depth_pct']}%",
        "",
        "## Relevant flexibility rules",
        *[
            f"- {rule['provision_name']}: status={rule['rule_status']}, eligibility={rule['eligibility_status']}"
            for rule in result["relevant_flexibility_rules"]
        ],
        "",
        "## Compute-cost estimate",
        f"- Annual curtailed MWh: {result['compute_cost_estimate']['annual_curtailed_mwh']}",
        f"- Estimated compute cost: ${result['compute_cost_estimate']['estimated_compute_cost_usd']}",
        "",
        "## Interconnection benefit assessment",
        f"- Benefit status: {result['interconnection_benefit_assessment']['benefit_status']}",
        f"- Baseline sample_n: {result['interconnection_benefit_assessment']['sample_n']}",
        f"- Baseline fallback_level: {result['interconnection_benefit_assessment']['fallback_level']}",
        "",
        "## Caveats and abstentions",
        *[f"- {item}" for item in result["caveats_and_abstentions"]],
        "",
        "## Citations",
        *[f"- {citation['citation_label']}: {citation['source_url']}" for citation in result["citations"]],
    ]
    return "\n".join(lines)
