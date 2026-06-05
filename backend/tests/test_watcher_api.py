from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_watcher_api_fixture_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRIDQUEUE_DB_PATH", str(tmp_path / "watcher_api.duckdb"))
    client = TestClient(app)

    assert client.post("/ingest/fixtures").status_code == 200
    seed = client.post("/watcher/sources/seed")
    assert seed.status_code == 200
    assert seed.json()["watch_source_count"] >= 6

    sources = client.get("/watcher/sources")
    assert sources.status_code == 200
    assert all(source["source_url"] for source in sources.json()["sources"])

    run = client.post(
        "/watcher/run",
        json={
            "mode": "fixture",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "top_n": 5,
        },
    )
    assert run.status_code == 200
    assert run.json()["digest"]["title"].startswith("Monthly Regulatory + Queue Change Watcher")

    latest = client.get("/watcher/digests/latest")
    assert latest.status_code == 200
    assert latest.json()["top_queue_changes"]

    events = client.get("/watcher/change-events")
    assert events.status_code == 200
    assert events.json()["change_events"]
