from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.db import connect, init_database
from app.services.flexibility import seed_flexibility_rules
from app.services.utils import compact_whitespace, new_id, stable_json, utcnow
from app.services.watcher.events import insert_change_event
from app.services.watcher.sources import seed_watch_sources


FIXTURE_CONTENT: dict[str, dict[str, str]] = {
    "current": {
        "watch_ferc_rm26_4": (
            "FERC RM26-4 ANOPR large load interconnection docket. The proceeding seeks public input on potential "
            "large-load interconnection reforms. Status remains ANOPR proposed pending; no final rule is assumed."
        ),
        "watch_ferc_large_load_update_2026_04_16": (
            "FERC April 16 2026 update says FERC will take action by June 2026 on the ANOPR proceeding. "
            "The update also references PJM co-location work and SPP HILL approval context."
        ),
        "watch_spp_hill_chill": (
            "SPP HILL integration page describes Conditional High Impact Large Load service with quick study "
            "results and possible curtailment during periods of system stress."
        ),
        "watch_ferc_spp_hill_concurrence": (
            "FERC Commissioner statement says the order accepts SPP HILL and HILLGA tariff revisions subject to condition."
        ),
        "watch_manual_regulatory_fixture": (
            "Manual fixture update: public stakeholder calendar changed for the large-load docket. "
            "No final order is represented in this synthetic fixture."
        ),
    },
    "changed": {
        "watch_ferc_rm26_4": (
            "FERC RM26-4 ANOPR large load interconnection docket. The proceeding seeks public input on potential "
            "large-load interconnection reforms. A page excerpt mentions final order language and requires manual review."
        ),
        "watch_manual_regulatory_fixture": (
            "Manual fixture update changed: an added sentence says review staff should check whether new final order "
            "language is present. This is synthetic and does not update any rule status."
        ),
    },
}


def capture_regulatory_snapshots(
    *,
    mode: str = "fixture",
    fixture_variant: str = "current",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    seed_watch_sources(db_path)
    seed_flexibility_rules(db_path)
    created_snapshots: list[dict[str, Any]] = []
    created_events: list[dict[str, Any]] = []
    with connect(db_path) as con:
        sources = con.execute(
            """
            SELECT watch_source_id, source_name, source_type, jurisdiction, source_url, parser_type,
                   last_snapshot_id, last_content_hash
            FROM watch_sources
            WHERE is_active = TRUE
            ORDER BY watch_source_id
            """
        ).fetchall()
        for source in sources:
            result = _snapshot_one_source(con, source, mode=mode, fixture_variant=fixture_variant)
            created_snapshots.append(result["snapshot"])
            created_events.extend(result["events"])
    return {
        "mode": mode,
        "fixture_variant": fixture_variant,
        "source_snapshot_count": len(created_snapshots),
        "change_event_count": len(created_events),
        "source_snapshots": created_snapshots,
        "change_events": created_events,
    }


def _snapshot_one_source(
    con: Any,
    row: tuple[Any, ...],
    *,
    mode: str,
    fixture_variant: str,
) -> dict[str, Any]:
    source = {
        "watch_source_id": row[0],
        "source_name": row[1],
        "source_type": row[2],
        "jurisdiction": row[3],
        "source_url": row[4],
        "parser_type": row[5],
        "last_snapshot_id": row[6],
        "last_content_hash": row[7],
    }
    retrieved_at = utcnow()
    parse_error: str | None = None
    try:
        content_text = _content_for_source(con, source, mode=mode, fixture_variant=fixture_variant)
        normalized_text = compact_whitespace(content_text)
        if not normalized_text:
            raise ValueError("Empty normalized content.")
        parse_status = "unchanged" if source["last_content_hash"] == _hash(normalized_text) else "changed"
    except (OSError, URLError, ValueError) as exc:
        normalized_text = ""
        parse_status = "failed"
        parse_error = str(exc)
    content_hash = _hash(normalized_text or f"failed:{source['watch_source_id']}:{parse_error}")
    snapshot_id = new_id("srcsnap")
    payload = _parse_payload(source, normalized_text, parse_status, parse_error)
    con.execute(
        """
        INSERT INTO source_snapshots
        (source_snapshot_id, watch_source_id, retrieved_at, publication_date, content_hash, content_text,
         raw_payload_json, parse_status, parse_error, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            snapshot_id,
            source["watch_source_id"],
            retrieved_at,
            None,
            content_hash,
            normalized_text,
            stable_json(payload),
            parse_status,
            parse_error,
            retrieved_at,
        ],
    )
    con.execute(
        """
        UPDATE watch_sources
        SET last_snapshot_id = ?, last_content_hash = ?, last_checked_at = ?, updated_at = ?
        WHERE watch_source_id = ?
        """,
        [snapshot_id, content_hash, retrieved_at, retrieved_at, source["watch_source_id"]],
    )
    event = _event_for_snapshot(con, source, snapshot_id, parse_status, parse_error, payload)
    return {
        "snapshot": {
            "source_snapshot_id": snapshot_id,
            "watch_source_id": source["watch_source_id"],
            "source_name": source["source_name"],
            "parse_status": parse_status,
            "parse_error": parse_error,
            "content_hash": content_hash,
            "source_url": source["source_url"],
        },
        "events": [event],
    }


def _content_for_source(
    con: Any,
    source: dict[str, Any],
    *,
    mode: str,
    fixture_variant: str,
) -> str:
    if source["parser_type"] == "manual_fixture_failure":
        raise ValueError("Synthetic parser failure fixture requires manual review.")
    if source["parser_type"] == "internal_flex_rule":
        rule_id = source["watch_source_id"].removeprefix("watch_flex_")
        row = con.execute(
            """
            SELECT rule_id, jurisdiction, provision_name, provision_type, status, granted_benefit_text,
                   quantified_benefit_json, source_url, notes
            FROM iso_flexibility_rules
            WHERE rule_id = ?
            """,
            [rule_id],
        ).fetchone()
        if not row:
            raise ValueError(f"Missing internal flexibility rule: {rule_id}")
        return stable_json(
            {
                "rule_id": row[0],
                "jurisdiction": row[1],
                "provision_name": row[2],
                "provision_type": row[3],
                "status": row[4],
                "granted_benefit_text": row[5],
                "quantified_benefit_json": json.loads(row[6]) if isinstance(row[6], str) else row[6],
                "source_url": row[7],
                "notes": row[8],
            }
        )
    fixture_text = {
        **FIXTURE_CONTENT["current"],
        **FIXTURE_CONTENT.get(fixture_variant, {}),
    }.get(source["watch_source_id"])
    if mode in {"fixture", "manual"}:
        return fixture_text or f"Fixture watch source {source['source_name']} unchanged baseline."
    if mode == "live":
        request = Request(source["source_url"], headers={"User-Agent": "gridqueue-agent-watcher/1.0"})
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported watcher mode: {mode}")


def _event_for_snapshot(
    con: Any,
    source: dict[str, Any],
    snapshot_id: str,
    parse_status: str,
    parse_error: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    before = {"previous_snapshot_id": source["last_snapshot_id"], "previous_content_hash": source["last_content_hash"]}
    after = {"source_snapshot_id": snapshot_id, **payload}
    if parse_status == "failed":
        event_type = "source_parse_failed"
        explanation = f"{source['source_name']} could not be parsed; manual review is required."
        hard_alert = False
    elif parse_status == "unchanged":
        event_type = "source_unchanged"
        explanation = f"{source['source_name']} content hash did not change."
        hard_alert = False
    elif _needs_manual_rule_review(source, payload):
        event_type = "rule_needs_review"
        explanation = f"{source['source_name']} changed and contains status language that requires manual review."
        hard_alert = True
    else:
        event_type = "rule_source_changed"
        explanation = f"{source['source_name']} content hash changed; no automatic rule status update was made."
        hard_alert = True
    return insert_change_event(
        con,
        event_domain="regulatory" if source["source_type"] != "flexibility_rule" else "flexibility_rule",
        event_type=event_type,
        jurisdiction=source["jurisdiction"],
        entity_or_provision=source["source_name"],
        rule_id=source["watch_source_id"].removeprefix("watch_flex_") if source["parser_type"] == "internal_flex_rule" else None,
        source_snapshot_id=snapshot_id,
        source_url=source["source_url"],
        before_json=before,
        after_json=after,
        confidence=0.9 if parse_status != "failed" else 0.4,
        is_ambiguous=parse_status == "failed",
        is_hard_alert_value=hard_alert,
        explanation=explanation,
        citation_ids=[snapshot_id],
    )


def _parse_payload(source: dict[str, Any], content_text: str, parse_status: str, parse_error: str | None) -> dict[str, Any]:
    lowered = content_text.lower()
    status_keywords = [
        keyword
        for keyword in ("anopr", "proposed", "pending", "directed", "approved", "accepted", "final", "order")
        if keyword in lowered
    ]
    return {
        "title": source["source_name"],
        "source_url": source["source_url"],
        "parse_status": parse_status,
        "parse_error": parse_error,
        "status_keywords": status_keywords,
        "diff_excerpt": content_text[:320],
    }


def _needs_manual_rule_review(source: dict[str, Any], payload: dict[str, Any]) -> bool:
    if source["parser_type"] == "internal_flex_rule":
        return False
    keywords = set(payload.get("status_keywords", []))
    return "final" in keywords or ("order" in keywords and source["jurisdiction"] == "FERC")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
