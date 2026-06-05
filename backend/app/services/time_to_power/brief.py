from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.time_to_power.estimate import generate_time_to_power_estimate
from app.services.utils import new_id, stable_json, utcnow


TIME_TO_POWER_CAVEAT = (
    "This Time-to-Power Brief is a public-data planning artifact. It is not a formal interconnection study, "
    "deliverability study, power-flow result, legal opinion, engineering design, procurement quote, OEM RFQ, "
    "commissioning plan, financial forecast, or guarantee of energization."
)


def generate_time_to_power_brief(*, output_dir: str | Path | None = None, db_path: str | Path | None = None, **kwargs: Any) -> dict[str, Any]:
    init_database(db_path)
    estimate = generate_time_to_power_estimate(db_path=db_path, **kwargs)
    brief_id = new_id("ttp_brief")
    title = f"Time-to-Power Brief: {estimate['scenario']['scenario_name']}"
    brief = {
        "brief_id": brief_id,
        "title": title,
        "executive_summary": _executive_summary(estimate),
        "project_scenario": estimate["scenario"],
        "interconnection_baseline": estimate["baseline"],
        "flexibility_adjusted_scenario": estimate["flexibility_adjusted"],
        "procurement_critical_path": estimate["procurement_critical_path"],
        "energization_timeline": _timeline_section(estimate),
        "scenario_comparison_table": _comparison_rows(estimate),
        "binding_constraints": {
            "selected_case": estimate["selected_case"],
            "binding_constraint": estimate["binding_constraint"],
            "status": estimate["status"],
            "status_explanation": estimate["status_explanation"],
        },
        "assumptions": estimate["assumptions"],
        "citations": estimate["citations"],
        "reproducibility_trace": estimate["reproducibility_trace"],
        "caveats_and_abstentions": [TIME_TO_POWER_CAVEAT, *estimate["caveats"]],
        "estimate": estimate,
    }
    brief["markdown"] = _to_markdown(brief)
    markdown_path = _write_markdown(brief["markdown"], output_dir)
    brief["markdown_path"] = str(markdown_path)
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO time_to_power_briefs
            (brief_id, scenario_id, estimate_id, title, brief_json, markdown_path, citations_json,
             assumptions_json, caveats_json, reproducibility_trace_json, generated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                brief_id,
                estimate["scenario"]["scenario_id"],
                estimate["estimate_id"],
                title,
                stable_json(brief),
                str(markdown_path),
                stable_json(brief["citations"]),
                stable_json(brief["assumptions"]),
                stable_json(brief["caveats_and_abstentions"]),
                stable_json(brief["reproducibility_trace"]),
                utcnow(),
                utcnow(),
            ],
        )
    return brief


def latest_time_to_power_brief(db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT brief_json
            FROM time_to_power_briefs
            ORDER BY generated_at DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return _json(row[0]) if row else None


def get_time_to_power_brief(brief_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT brief_json FROM time_to_power_briefs WHERE brief_id = ?", [brief_id]).fetchone()
    return _json(row[0]) if row else None


def _executive_summary(estimate: dict[str, Any]) -> list[str]:
    serial = _range(estimate.get("no_flex_serial_low_days"), estimate.get("no_flex_serial_high_days"))
    overlap = _range(estimate.get("no_flex_overlap_low_days"), estimate.get("no_flex_overlap_high_days"))
    flex_status = estimate["flexibility_adjusted"]["benefit_status"]
    return [
        f"Baseline interconnection proxy uses metric_id={estimate['baseline'].get('metric_id')} with sample_n={estimate['baseline'].get('sample_n')}, fallback_level={estimate['baseline'].get('fallback_level')}, confidence={estimate['baseline'].get('confidence')}.",
        f"Post-NTP serial no-flex Time-to-Power range is {serial}.",
        f"At-risk overlap no-flex comparison range is {overlap}; overlap requires explicit user risk acceptance.",
        f"Flexibility benefit_status={flex_status}; procurement lead time is unchanged by default.",
        f"Binding constraint under selected strategy is {estimate['binding_constraint']}; estimate status={estimate['status']}.",
    ]


def _timeline_section(estimate: dict[str, Any]) -> dict[str, Any]:
    return {
        "serial_assumption": "Procurement starts after interconnection approval / NTP.",
        "overlap_assumption": "Procurement starts before final NTP at user risk.",
        "no_flex_serial_range_days": [estimate.get("no_flex_serial_low_days"), estimate.get("no_flex_serial_high_days")],
        "flex_serial_range_days": [estimate.get("flex_serial_low_days"), estimate.get("flex_serial_high_days")],
        "no_flex_overlap_range_days": [estimate.get("no_flex_overlap_low_days"), estimate.get("no_flex_overlap_high_days")],
        "flex_overlap_range_days": [estimate.get("flex_overlap_low_days"), estimate.get("flex_overlap_high_days")],
    }


def _comparison_rows(estimate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"case": "no_flex_serial", "low_days": estimate.get("no_flex_serial_low_days"), "high_days": estimate.get("no_flex_serial_high_days"), "assumption": "post-NTP serial"},
        {"case": "flex_serial", "low_days": estimate.get("flex_serial_low_days"), "high_days": estimate.get("flex_serial_high_days"), "assumption": "post-NTP serial with quantified flex only"},
        {"case": "no_flex_overlap", "low_days": estimate.get("no_flex_overlap_low_days"), "high_days": estimate.get("no_flex_overlap_high_days"), "assumption": "at-risk procurement overlap"},
        {"case": "flex_overlap", "low_days": estimate.get("flex_overlap_low_days"), "high_days": estimate.get("flex_overlap_high_days"), "assumption": "at-risk overlap with quantified flex only"},
    ]


def _to_markdown(brief: dict[str, Any]) -> str:
    estimate = brief["estimate"]
    baseline = brief["interconnection_baseline"]
    flex = brief["flexibility_adjusted_scenario"]
    procurement = brief["procurement_critical_path"]
    lines = [
        f"# {brief['title']}",
        "",
        "## Executive summary",
        *[f"- {item}" for item in brief["executive_summary"]],
        "",
        "## Project scenario",
        f"- Market / jurisdiction: {brief['project_scenario']['market']} / {brief['project_scenario']['jurisdiction']}",
        f"- Project type: {brief['project_scenario']['project_type']}",
        f"- County / region: {brief['project_scenario']['county'] or 'NA'} / {brief['project_scenario']['region'] or 'NA'}",
        f"- Peak load: {brief['project_scenario']['peak_mw']} MW",
        f"- Interconnection voltage: {brief['project_scenario']['interconnection_voltage_kv']} kV",
        f"- Procurement strategy: {brief['project_scenario']['procurement_strategy']}",
        "",
        "## Interconnection baseline",
        f"- Range: {_range(baseline.get('baseline_low_days'), baseline.get('baseline_high_days'))}",
        f"- metric_id: {baseline.get('metric_id')}",
        f"- sample_n: {baseline.get('sample_n')}",
        f"- fallback_level: {baseline.get('fallback_level')}",
        f"- confidence: {baseline.get('confidence')}",
        f"- source_snapshot_id: {baseline.get('source_snapshot_id')}",
        "",
        "## Flexibility-adjusted scenario",
        f"- rule_status: {flex.get('rule_status')}",
        f"- eligibility_status: {flex.get('eligibility_status')}",
        f"- benefit_status: {flex.get('benefit_status')}",
        f"- interconnection_with_flex_range: {_range(flex.get('interconnection_with_flex_low_days'), flex.get('interconnection_with_flex_high_days'))}",
        "- Procurement path impact: unchanged by default.",
        "",
        "## Procurement critical path",
        f"- Binding equipment: {procurement.get('binding_equipment_class')}",
        f"- Binding lead-time range: {_range(procurement.get('binding_lead_time_low_months'), procurement.get('binding_lead_time_high_months'), 'months')}",
        f"- Procurement days range: {_range(procurement.get('procurement_low_days'), procurement.get('procurement_high_days'))}",
        f"- stale_flag: {procurement.get('stale_flag')}",
        f"- conflict_flag: {procurement.get('conflict_flag')}",
        f"- unsupported_flag: {procurement.get('unsupported_flag')}",
        "",
        "## Energization timeline",
        "- Serial post-NTP: procurement starts after interconnection approval / NTP.",
        "- At-risk overlap: procurement starts before final NTP and can strand spend if outcomes change.",
        *[
            f"- {row['case']}: {_range(row['low_days'], row['high_days'])} ({row['assumption']})"
            for row in brief["scenario_comparison_table"]
        ],
        "",
        "## Scenario comparison table",
        "| case | low_days | high_days | assumption |",
        "| --- | ---: | ---: | --- |",
        *[
            f"| {row['case']} | {row['low_days'] if row['low_days'] is not None else 'NA'} | {row['high_days'] if row['high_days'] is not None else 'NA'} | {row['assumption']} |"
            for row in brief["scenario_comparison_table"]
        ],
        "",
        "## Binding constraints",
        f"- selected_case: {estimate['selected_case']}",
        f"- binding_constraint: {estimate['binding_constraint']}",
        f"- status: {estimate['status']}",
        f"- status_explanation: {estimate['status_explanation']}",
        "",
        "## Assumptions",
        f"- serial_formula: {brief['assumptions']['serial_formula']}",
        f"- overlap_formula: {brief['assumptions']['overlap_formula']}",
        f"- days_per_month: {brief['assumptions']['procurement_assumptions'].get('days_per_month')}",
        "",
        "## Citations",
        *[f"- {citation.get('citation_label')}: {citation.get('source_url')}" for citation in brief["citations"]],
        "",
        "## Reproducibility trace",
        *[f"- {item}" for item in brief["reproducibility_trace"]],
        "",
        "## Caveats and abstentions",
        *[f"- {item}" for item in brief["caveats_and_abstentions"]],
    ]
    return "\n".join(lines)


def _write_markdown(markdown: str, output_dir: str | Path | None) -> Path:
    root = Path(output_dir) if output_dir is not None else Path.cwd() / "briefs" / "time_to_power"
    root.mkdir(parents=True, exist_ok=True)
    latest = root / "latest.md"
    latest.write_text(markdown, encoding="utf-8")
    return latest


def _range(low: Any, high: Any, unit: str = "days") -> str:
    if low is None or high is None:
        return "not computed"
    return f"{float(low):.2f}-{float(high):.2f} {unit}"


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
