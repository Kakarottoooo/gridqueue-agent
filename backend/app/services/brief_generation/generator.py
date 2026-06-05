from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.citations import ensure_reference_sources, get_citations_for_records
from app.services.diffing import get_diff_result
from app.services.metrics import compute_metric_rollup


FORMAL_STUDY_CAVEAT = (
    "This is a public-data signal analysis, not a formal interconnection study, "
    "deliverability study, power-flow result, or upgrade-cost estimate."
)


def generate_brief(
    *,
    market: str,
    project_type: str,
    county: str | None,
    capacity_mw: float | None,
    target_cod_year: int | None,
    question: str | None,
    min_sample_n: int = 30,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    ensure_reference_sources(db_path)
    with connect(db_path) as con:
        latest = con.execute(
            """
            SELECT snapshot_id, snapshot_date, source_id
            FROM snapshots
            WHERE market = ?
            ORDER BY snapshot_date DESC, snapshot_id DESC
            LIMIT 1
            """,
            [market],
        ).fetchone()
        if not latest:
            raise ValueError(f"No snapshots are available for {market}. Run fixture or manual ingestion first.")
        previous = con.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE market = ? AND snapshot_date < ?
            ORDER BY snapshot_date DESC, snapshot_id DESC
            LIMIT 1
            """,
            [market, latest[1]],
        ).fetchone()
        source = con.execute(
            "SELECT source_name, source_url FROM sources WHERE source_id = ?",
            [latest[2]],
        ).fetchone()
        queue_rows = _queue_rows(con, latest[0], county, project_type)
        comparables = _comparables(con, latest[0], county, project_type, capacity_mw, target_cod_year)
        source_citation = {
            "citation_id": f"snapshot:{latest[0]}",
            "citation_label": f"{market} snapshot {latest[1]}",
            "citation_text": f"{source[0]} snapshot {latest[1]} with {len(queue_rows)} matching rows in query scope.",
            "source_url": source[1],
        }
        reference_sources = {
            row[0]: {"source_name": row[1], "source_url": row[2], "notes": row[3]}
            for row in con.execute("SELECT source_id, source_name, source_url, notes FROM sources").fetchall()
        }

    metrics = compute_metric_rollup(
        market=market,
        county=county,
        fuel_type=project_type,
        min_sample_n=min_sample_n,
        db_path=db_path,
    )
    diff = get_diff_result(previous[0], latest[0], db_path) if previous else {"counts_by_event_type": {}, "events": []}
    top_comparables = comparables[:5]
    record_citations = get_citations_for_records([row["record_id"] for row in top_comparables], db_path)
    citations_by_record: dict[str, list[str]] = {}
    for citation in record_citations:
        citations_by_record.setdefault(citation["record_id"], []).append(citation["citation_id"])
    for row in top_comparables:
        row["citation_ids"] = citations_by_record.get(row["record_id"], [])
    citation_map = {citation["citation_id"]: citation for citation in [source_citation, *record_citations]}

    active_rows = [row for row in queue_rows if row["normalized_status"] == "Active"]
    active_mw = round(sum(row["capacity_mw"] or 0 for row in active_rows), 2)
    status_counts = dict(Counter(row["normalized_status"] for row in queue_rows))
    diff_counts = diff.get("counts_by_event_type", {})
    large_load_context = _large_load_context(question, reference_sources)

    caveats = [
        FORMAL_STUDY_CAVEAT,
        "Fixture records are synthetic when ingestion_mode=fixture; they demonstrate behavior but are not market facts.",
        "A missing or renamed public queue row is not treated as a confirmed withdrawal unless status/source evidence supports it.",
    ]
    if metrics["confidence"] == "Insufficient":
        caveats.append(metrics["explanation"])
    if large_load_context:
        caveats.append(large_load_context["caveat"])

    reproducibility_trace = [
        f"latest_snapshot: SELECT snapshot_id FROM snapshots WHERE market='{market}' ORDER BY snapshot_date DESC LIMIT 1 -> {latest[0]}",
        f"queue_scope: normalized_project_records WHERE snapshot_id='{latest[0]}' AND county='{county or '*'}' AND normalized_fuel_type='{project_type}'",
        f"metrics: fallback_level={metrics['fallback_level']}, sample_n={metrics['sample_n']}, min_sample_n={min_sample_n}",
        f"diff: from_snapshot_id={previous[0] if previous else 'none'} to_snapshot_id={latest[0]}",
        "entity_resolution: project_entity_links.match_features_json stores the deterministic matching evidence for each linked record.",
    ]

    executive_summary = [
        f"{market} {county or 'market-wide'} {project_type} scope has {len(queue_rows)} matching latest-snapshot records and {len(active_rows)} active records.",
        f"Active capacity in this public queue scope is {active_mw} MW.",
        f"Historical proxy uses fallback_level={metrics['fallback_level']} with sample_n={metrics['sample_n']} and confidence={metrics['confidence']}.",
    ]
    if diff_counts:
        top_changes = ", ".join(f"{key}: {value}" for key, value in sorted(diff_counts.items()))
        executive_summary.append(f"Latest month-over-month diff events include {top_changes}.")
    if large_load_context:
        executive_summary.append(large_load_context["summary"])

    result = {
        "title": "Public Interconnection Risk Brief",
        "inputs": {
            "market": market,
            "project_type": project_type,
            "county": county,
            "capacity_mw": capacity_mw,
            "target_cod_year": target_cod_year,
            "question": question,
            "min_sample_n": min_sample_n,
        },
        "executive_summary": executive_summary,
        "queue_snapshot": {
            "snapshot_id": latest[0],
            "snapshot_date": str(latest[1]),
            "matching_records": len(queue_rows),
            "active_count": len(active_rows),
            "active_mw": active_mw,
            "status_counts": status_counts,
            "citation_ids": [source_citation["citation_id"]],
        },
        "comparable_projects": top_comparables,
        "monthly_changes": {
            "from_snapshot_id": previous[0] if previous else None,
            "to_snapshot_id": latest[0],
            "counts_by_event_type": diff_counts,
            "events": diff.get("events", [])[:12],
        },
        "historical_proxy": metrics,
        "large_load_context": large_load_context,
        "caveats_and_abstentions": caveats,
        "citations": list(citation_map.values()),
        "reproducibility_trace": reproducibility_trace,
    }
    result["markdown"] = _to_markdown(result)
    return result


def _queue_rows(con: Any, snapshot_id: str, county: str | None, project_type: str | None) -> list[dict[str, Any]]:
    filters = ["snapshot_id = ?"]
    params: list[Any] = [snapshot_id]
    if county:
        filters.append("county = ?")
        params.append(county)
    if project_type:
        filters.append("normalized_fuel_type = ?")
        params.append(project_type)
    rows = con.execute(
        f"""
        SELECT record_id, queue_id, project_name, county, normalized_fuel_type, capacity_mw,
               normalized_status, target_cod
        FROM normalized_project_records
        WHERE {" AND ".join(filters)}
        ORDER BY normalized_status, capacity_mw DESC NULLS LAST, project_name
        """,
        params,
    ).fetchall()
    return [
        {
            "record_id": row[0],
            "queue_id": row[1],
            "project_name": row[2],
            "county": row[3],
            "normalized_fuel_type": row[4],
            "capacity_mw": row[5],
            "normalized_status": row[6],
            "target_cod": str(row[7]) if row[7] else None,
        }
        for row in rows
    ]


def _comparables(
    con: Any,
    snapshot_id: str,
    county: str | None,
    project_type: str,
    capacity_mw: float | None,
    target_cod_year: int | None,
) -> list[dict[str, Any]]:
    rows = _queue_rows(con, snapshot_id, county, project_type)
    for row in rows:
        capacity = row["capacity_mw"] or 0
        row["capacity_distance_mw"] = abs(capacity - capacity_mw) if capacity_mw is not None else None
        row["target_cod_year_match"] = bool(row["target_cod"] and target_cod_year and row["target_cod"].startswith(str(target_cod_year)))
        row["citation_ids"] = []
    rows.sort(key=lambda row: ((row["capacity_distance_mw"] if row["capacity_distance_mw"] is not None else 1_000_000), not row["target_cod_year_match"]))
    return rows


def _large_load_context(question: str | None, reference_sources: dict[str, dict[str, str]]) -> dict[str, Any] | None:
    if not question:
        return None
    lowered = question.lower()
    if not any(term in lowered for term in ("data center", "large load", "load", "ai campus")):
        return None
    source = reference_sources.get("src_ercot_large_load_2026_04_09", {})
    return {
        "summary": "The question touches large-load/data-center risk, but the ingested ERCOT queue records here are generation-resource records.",
        "caveat": "Large-load context is cited separately and is not treated as a complete public large-load interconnection queue.",
        "citation": {
            "source_name": source.get("source_name"),
            "source_url": source.get("source_url"),
        },
    }


def _to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        "## Executive summary",
        *[f"- {item}" for item in result["executive_summary"]],
        "",
        "## Queue snapshot",
        f"- Snapshot: {result['queue_snapshot']['snapshot_date']} ({result['queue_snapshot']['snapshot_id']})",
        f"- Matching records: {result['queue_snapshot']['matching_records']}",
        f"- Active records: {result['queue_snapshot']['active_count']}",
        f"- Active MW: {result['queue_snapshot']['active_mw']}",
        "",
        "## Comparable projects",
    ]
    for row in result["comparable_projects"]:
        lines.append(
            f"- {row['project_name']} ({row['queue_id']}): {row['capacity_mw']} MW, "
            f"{row['normalized_status']}, target COD {row['target_cod']}"
        )
    lines.extend(
        [
            "",
            "## Monthly changes",
            f"- Counts by event type: {result['monthly_changes']['counts_by_event_type']}",
            "",
            "## Historical proxy",
            (
                f"- fallback_level={result['historical_proxy']['fallback_level']}, "
                f"sample_n={result['historical_proxy']['sample_n']}, "
                f"confidence={result['historical_proxy']['confidence']}"
            ),
            f"- completion_rate={result['historical_proxy']['completion_rate']}",
            f"- withdrawal_rate={result['historical_proxy']['withdrawal_rate']}",
            "",
            "## Caveats and abstentions",
            *[f"- {item}" for item in result["caveats_and_abstentions"]],
            "",
            "## Citations",
            *[f"- {citation['citation_label']}: {citation['citation_text']} ({citation['source_url']})" for citation in result["citations"]],
            "",
            "## Reproducibility trace",
            *[f"- {item}" for item in result["reproducibility_trace"]],
        ]
    )
    return "\n".join(lines)
