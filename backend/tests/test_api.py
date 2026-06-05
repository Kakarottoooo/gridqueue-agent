from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_api_fixture_to_brief_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRIDQUEUE_DB_PATH", str(tmp_path / "api.duckdb"))
    client = TestClient(app)

    assert client.get("/health").json()["status"] == "ok"
    ingest = client.post("/ingest/fixtures")
    assert ingest.status_code == 200
    assert ingest.json()["row_count"] == 29

    snapshots = client.get("/snapshots").json()["snapshots"]
    assert len(snapshots) == 2

    diff = client.get(f"/diff/{snapshots[0]['snapshot_id']}/{snapshots[1]['snapshot_id']}")
    assert diff.status_code == 200
    assert diff.json()["counts_by_event_type"]["ambiguous_match"] == 2

    brief = client.post(
        "/brief",
        json={
            "market": "ERCOT",
            "project_type": "Battery",
            "county": "Reeves",
            "capacity_mw": 100,
            "target_cod_year": 2028,
            "question": "What public interconnection risks should I know?",
            "min_sample_n": 2,
        },
    )
    assert brief.status_code == 200
    body = brief.json()
    assert body["queue_snapshot"]["matching_records"] >= 1
    assert body["citations"]

