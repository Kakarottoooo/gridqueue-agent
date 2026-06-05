from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.config import project_root
from app.db import connect, init_database
from app.services.metrics import compute_metric_rollup
from app.services.utils import new_id, stable_json, utcnow
from app.services.watcher.events import change_event_select_sql, insert_change_event, row_to_change_event
from app.services.watcher.materiality import rank_change_events


WATCHER_CAVEAT = (
    "This digest is a public-data monitoring artifact. It does not replace formal interconnection studies, legal "
    "review, regulatory counsel, power-flow studies, procurement quotes, or project-specific diligence."
)


def generate_monthly_digest(
    *,
    period_start: str | date,
    period_end: str | date,
    top_n: int = 10,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    start = _date(period_start)
    end = _date(period_end)
    events = list_change_events(db_path=db_path)
    ranked = rank_change_events(events, top_n=top_n)
    top_events = ranked["top_events"]
    suppressed = [event for event in ranked["suppressed_events"] if event["event_type"] == "ambiguous_match"]
    parse_failures = [event for event in events if event["event_type"] == "source_parse_failed"]
    top_queue = [event for event in top_events if event["event_domain"] == "queue"]
    top_regulatory = [event for event in top_events if event["event_domain"] in {"regulatory", "flexibility_rule"}]
    rule_watch = [event for event in events if event["event_domain"] == "flexibility_rule"]
    metrics_summary = _metrics_summary(db_path)
    citations = _citations_for_digest(events)
    executive_summary = _executive_summary(top_queue, top_regulatory, suppressed, parse_failures)
    digest_id = new_id("digest")
    result = {
        "digest_id": digest_id,
        "digest_type": "monthly_watcher",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "title": f"Monthly Regulatory + Queue Change Watcher: {start:%Y-%m}",
        "executive_summary": executive_summary,
        "top_queue_changes": [_digest_line(event) for event in top_queue],
        "top_regulatory_changes": [_digest_line(event) for event in top_regulatory],
        "flexibility_rule_watch": [_digest_line(event) for event in rule_watch[:top_n]],
        "suppressed_ambiguous": [_digest_line(event) for event in suppressed],
        "parse_failures": [_digest_line(event) for event in parse_failures],
        "metrics_summary": metrics_summary,
        "citations": citations,
        "reproducibility_trace": [
            "queue_adapter: diff_events converted into change_events with ambiguous_match kept non-hard-alert.",
            "regulatory_snapshot: watch_sources normalized to content_hash before source_snapshots and change_events.",
            f"materiality: deterministic BASE_WEIGHTS plus capacity/timeline/watchlist modifiers, top_n={top_n}.",
            "digest: every listed event carries change_event_id plus source_url or snapshot id.",
        ],
        "caveats": [WATCHER_CAVEAT],
        "top_event_ids": [event["change_event_id"] for event in top_events],
    }
    result["markdown"] = _markdown(result)
    markdown_path = _write_digest_markdown(result)
    result["markdown_path"] = str(markdown_path)

    with connect(db_path) as con:
        insert_change_event(
            con,
            event_domain="system",
            event_type="digest_generated",
            entity_or_provision=result["title"],
            before_json={},
            after_json={"digest_id": digest_id, "period_start": result["period_start"], "period_end": result["period_end"]},
            confidence=1.0,
            is_hard_alert_value=False,
            explanation=f"Generated monthly watcher digest {digest_id}.",
            citation_ids=result["top_event_ids"],
        )
        con.execute(
            """
            INSERT INTO digests
            (digest_id, digest_type, period_start, period_end, title, markdown_path, digest_json,
             top_event_ids_json, generated_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                digest_id,
                "monthly_watcher",
                start,
                end,
                result["title"],
                str(markdown_path),
                stable_json(result),
                stable_json(result["top_event_ids"]),
                utcnow(),
                utcnow(),
            ],
        )
    return result


def list_change_events(
    *,
    event_domain: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_database(db_path)
    filters = []
    params: list[Any] = []
    if event_domain:
        filters.append("event_domain = ?")
        params.append(event_domain)
    where = f" WHERE {' AND '.join(filters)}" if filters else ""
    with connect(db_path) as con:
        rows = con.execute(
            f"{change_event_select_sql()} {where} ORDER BY materiality_score DESC, created_at DESC",
            params,
        ).fetchall()
    return [row_to_change_event(row) for row in rows]


def list_digests(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_database(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT digest_id, digest_type, period_start, period_end, title, markdown_path,
                   top_event_ids_json, generated_at, created_at
            FROM digests
            ORDER BY generated_at DESC
            """
        ).fetchall()
    return [
        {
            "digest_id": row[0],
            "digest_type": row[1],
            "period_start": row[2].isoformat() if hasattr(row[2], "isoformat") else row[2],
            "period_end": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
            "title": row[4],
            "markdown_path": row[5],
            "top_event_ids": json.loads(row[6]) if isinstance(row[6], str) else row[6],
            "generated_at": row[7].isoformat() if hasattr(row[7], "isoformat") else row[7],
            "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else row[8],
        }
        for row in rows
    ]


def latest_digest(db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT digest_json, markdown_path
            FROM digests
            WHERE digest_type = 'monthly_watcher'
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    digest = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    digest["markdown_path"] = row[1]
    return digest


def _digest_line(event: dict[str, Any]) -> dict[str, Any]:
    source_trace = event.get("source_url") or event.get("source_snapshot_id") or event.get("to_snapshot_id") or event.get("from_snapshot_id")
    return {
        "change_event_id": event["change_event_id"],
        "event_domain": event["event_domain"],
        "event_type": event["event_type"],
        "entity_or_provision": event.get("entity_or_provision"),
        "materiality_score": event["materiality_score"],
        "confidence": event["confidence"],
        "is_hard_alert": event["is_hard_alert"],
        "is_ambiguous": event["is_ambiguous"],
        "source_url": event.get("source_url"),
        "source_trace": source_trace,
        "explanation": event["explanation"],
    }


def _executive_summary(
    top_queue: list[dict[str, Any]],
    top_regulatory: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    parse_failures: list[dict[str, Any]],
) -> list[str]:
    if not top_queue and not top_regulatory and not parse_failures:
        return ["No material change detected in the selected fixture watcher run."]
    lines = [
        f"{len(top_queue)} queue hard-alert changes and {len(top_regulatory)} regulatory/rule hard-alert changes were selected by deterministic materiality scoring.",
    ]
    if suppressed:
        lines.append(f"{len(suppressed)} ambiguous queue events were suppressed from hard-alert sections and listed for review.")
    if parse_failures:
        lines.append(f"{len(parse_failures)} source parse failures require manual review; failed content is not summarized as parsed.")
    return lines


def _metrics_summary(db_path: str | Path | None) -> dict[str, Any]:
    try:
        metric = compute_metric_rollup(market="ERCOT", county="Reeves", fuel_type="Battery", min_sample_n=2, db_path=db_path)
        return {
            "market": "ERCOT",
            "county": "Reeves",
            "fuel_type": "Battery",
            "sample_n": metric["sample_n"],
            "fallback_level": metric["fallback_level"],
            "confidence": metric["confidence"],
        }
    except ValueError:
        return {"status": "not_available"}


def _citations_for_digest(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []
    seen = set()
    for event in events:
        source_trace = event.get("source_url") or event.get("source_snapshot_id") or event.get("to_snapshot_id") or event.get("from_snapshot_id")
        if not source_trace or source_trace in seen:
            continue
        seen.add(source_trace)
        citations.append(
            {
                "citation_label": event.get("entity_or_provision") or event["event_type"],
                "change_event_id": event["change_event_id"],
                "source_url": event.get("source_url"),
                "source_trace": source_trace,
            }
        )
    return citations


def _write_digest_markdown(result: dict[str, Any]) -> Path:
    digest_dir = project_root() / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    period = result["period_start"][:7]
    period_path = digest_dir / f"{period}.md"
    latest_path = digest_dir / "latest.md"
    period_path.write_text(result["markdown"], encoding="utf-8")
    latest_path.write_text(result["markdown"], encoding="utf-8")
    return latest_path


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        "## Executive summary",
        *[f"- {item}" for item in result["executive_summary"]],
        "",
        "## Top queue changes",
        *_markdown_lines(result["top_queue_changes"]),
        "",
        "## Top regulatory changes",
        *_markdown_lines(result["top_regulatory_changes"]),
        "",
        "## Flexibility rule watch",
        *_markdown_lines(result["flexibility_rule_watch"]),
        "",
        "## Ambiguous / suppressed queue noise",
        *_markdown_lines(result["suppressed_ambiguous"]),
        "",
        "## Parse failures / manual review required",
        *_markdown_lines(result["parse_failures"]),
        "",
        "## Metrics summary",
        f"- {result['metrics_summary']}",
        "",
        "## Citations and source URLs",
        *[
            f"- {citation['citation_label']}: event={citation['change_event_id']}, source={citation['source_url'] or citation['source_trace']}"
            for citation in result["citations"]
        ],
        "",
        "## Reproducibility trace",
        *[f"- {item}" for item in result["reproducibility_trace"]],
        "",
        "## Caveats",
        *[f"- {item}" for item in result["caveats"]],
    ]
    return "\n".join(lines)


def _markdown_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No material change detected."]
    return [
        (
            f"- `{row['change_event_id']}` {row['event_type']} ({row['materiality_score']}, "
            f"confidence={row['confidence']}): {row['explanation']} "
            f"[source: {row['source_url'] or row['source_trace']}]"
        )
        for row in rows
    ]


def _date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
