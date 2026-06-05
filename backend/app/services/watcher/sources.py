from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility import seed_flexibility_rules
from app.services.utils import utcnow


CURATED_WATCH_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "watch_source_id": "watch_ferc_rm26_4",
        "source_name": "FERC RM26-4 large-load interconnection docket",
        "source_type": "ferc_docket",
        "jurisdiction": "FERC",
        "source_url": "https://www.ferc.gov/rm26-4",
        "parser_type": "ferc_large_load_docket",
        "watch_frequency": "monthly",
        "is_active": True,
        "notes": "Primary docket page. Watcher treats ANOPR/final-rule language as a review signal, not an automatic status change.",
    },
    {
        "watch_source_id": "watch_ferc_large_load_update_2026_04_16",
        "source_name": "FERC April 16 2026 large-load docket update",
        "source_type": "ferc_docket",
        "jurisdiction": "FERC",
        "source_url": "https://www.ferc.gov/news-events/news/ferc-act-large-load-interconnection-docket-june-2026",
        "parser_type": "ferc_news_page",
        "watch_frequency": "monthly",
        "is_active": True,
        "notes": "FERC news page stating planned June 2026 action on the RM26-4 ANOPR proceeding.",
    },
    {
        "watch_source_id": "watch_spp_hill_chill",
        "source_name": "SPP High Impact Large Load / CHILL page",
        "source_type": "iso_rule_page",
        "jurisdiction": "SPP",
        "source_url": "https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/",
        "parser_type": "iso_rule_page",
        "watch_frequency": "monthly",
        "is_active": True,
        "notes": "SPP public HILL/HILLGA/CHILL program page.",
    },
    {
        "watch_source_id": "watch_ferc_spp_hill_concurrence",
        "source_name": "FERC SPP HILL concurrence and acceptance context",
        "source_type": "ferc_docket",
        "jurisdiction": "SPP",
        "source_url": "https://www.ferc.gov/news-events/news/commissioner-rosners-concurrence-order-accepting-tariff-revisions-subject",
        "parser_type": "ferc_news_page",
        "watch_frequency": "monthly",
        "is_active": True,
        "notes": "FERC statement around acceptance of SPP HILL/HILLGA tariff revisions subject to condition.",
    },
    {
        "watch_source_id": "watch_manual_regulatory_fixture",
        "source_name": "Manual fixture regulatory update",
        "source_type": "manual_fixture",
        "jurisdiction": "FERC",
        "source_url": "synthetic://gridqueue-agent/fixtures/watcher/manual-regulatory-update",
        "parser_type": "manual_fixture",
        "watch_frequency": "manual",
        "is_active": True,
        "notes": "Synthetic deterministic fixture source for offline source-diff tests.",
    },
    {
        "watch_source_id": "watch_manual_parse_failure_fixture",
        "source_name": "Manual fixture parser failure",
        "source_type": "manual_fixture",
        "jurisdiction": "FERC",
        "source_url": "synthetic://gridqueue-agent/fixtures/watcher/parse-failure",
        "parser_type": "manual_fixture_failure",
        "watch_frequency": "manual",
        "is_active": True,
        "notes": "Synthetic deterministic fixture source that emits manual-review parse failures.",
    },
)


def seed_watch_sources(db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    seed_flexibility_rules(db_path)
    with connect(db_path) as con:
        for source in CURATED_WATCH_SOURCES:
            _insert_watch_source(con, source)
        flex_rules = con.execute(
            """
            SELECT rule_id, jurisdiction, provision_name, source_url, status
            FROM iso_flexibility_rules
            ORDER BY rule_id
            """
        ).fetchall()
        for rule_id, jurisdiction, provision_name, source_url, status in flex_rules:
            _insert_watch_source(
                con,
                {
                    "watch_source_id": f"watch_flex_{rule_id}",
                    "source_name": f"Flexibility rule: {provision_name}",
                    "source_type": "flexibility_rule",
                    "jurisdiction": jurisdiction,
                    "source_url": source_url,
                    "parser_type": "internal_flex_rule",
                    "watch_frequency": "monthly",
                    "is_active": True,
                    "notes": f"Internal watch source for iso_flexibility_rules.{rule_id}; current seeded status={status}.",
                },
            )
        count = con.execute("SELECT COUNT(*) FROM watch_sources").fetchone()[0]
    return {"status": "seeded", "watch_source_count": int(count)}


def list_watch_sources(
    *,
    active_only: bool = False,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_database(db_path)
    where = "WHERE is_active = TRUE" if active_only else ""
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            SELECT watch_source_id, source_name, source_type, jurisdiction, source_url, parser_type,
                   watch_frequency, is_active, last_snapshot_id, last_content_hash, last_checked_at,
                   notes, created_at, updated_at
            FROM watch_sources
            {where}
            ORDER BY source_type, jurisdiction, source_name
            """
        ).fetchall()
    return [_watch_source_from_row(row) for row in rows]


def _insert_watch_source(con: Any, source: dict[str, Any]) -> None:
    exists = con.execute(
        "SELECT COUNT(*) FROM watch_sources WHERE watch_source_id = ?",
        [source["watch_source_id"]],
    ).fetchone()[0]
    if exists:
        return
    now = utcnow()
    con.execute(
        """
        INSERT INTO watch_sources
        (watch_source_id, source_name, source_type, jurisdiction, source_url, parser_type,
         watch_frequency, is_active, last_snapshot_id, last_content_hash, last_checked_at,
         notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            source["watch_source_id"],
            source["source_name"],
            source["source_type"],
            source["jurisdiction"],
            source["source_url"],
            source["parser_type"],
            source["watch_frequency"],
            source["is_active"],
            None,
            None,
            None,
            source["notes"],
            now,
            now,
        ],
    )


def _watch_source_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "watch_source_id": row[0],
        "source_name": row[1],
        "source_type": row[2],
        "jurisdiction": row[3],
        "source_url": row[4],
        "parser_type": row[5],
        "watch_frequency": row[6],
        "is_active": bool(row[7]),
        "last_snapshot_id": row[8],
        "last_content_hash": row[9],
        "last_checked_at": row[10].isoformat() if hasattr(row[10], "isoformat") else row[10],
        "notes": row[11],
        "created_at": row[12].isoformat() if hasattr(row[12], "isoformat") else row[12],
        "updated_at": row[13].isoformat() if hasattr(row[13], "isoformat") else row[13],
    }
