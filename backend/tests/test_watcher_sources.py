from __future__ import annotations

from app.db import reset_database
from app.services.watcher import list_watch_sources, seed_watch_sources


def test_watch_sources_seed_idempotently_with_urls(tmp_path) -> None:
    db_path = tmp_path / "watch_sources.duckdb"
    reset_database(db_path)

    first = seed_watch_sources(db_path)
    second = seed_watch_sources(db_path)
    sources = list_watch_sources(db_path=db_path)

    assert first["watch_source_count"] == second["watch_source_count"]
    assert len(sources) >= 6
    assert all(source["source_url"] for source in sources)
    assert {"ferc_docket", "iso_rule_page", "flexibility_rule", "manual_fixture"} <= {
        source["source_type"] for source in sources
    }
