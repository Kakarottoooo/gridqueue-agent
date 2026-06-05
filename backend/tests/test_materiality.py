from __future__ import annotations

from app.services.watcher.materiality import rank_change_events, score_change_event


def test_materiality_scoring_and_ranking_are_deterministic() -> None:
    events = [
        {
            "change_event_id": "a",
            "event_domain": "queue",
            "event_type": "name_changed",
            "entity_or_provision": "Rename",
            "before_json": {},
            "after_json": {"county": "Reeves", "capacity_mw": 10},
            "confidence": 1.0,
            "is_ambiguous": False,
        },
        {
            "change_event_id": "b",
            "event_domain": "queue",
            "event_type": "withdrawn_project",
            "entity_or_provision": "Withdrawn",
            "before_json": {},
            "after_json": {"county": "Reeves", "capacity_mw": 200},
            "confidence": 1.0,
            "is_ambiguous": False,
        },
        {
            "change_event_id": "c",
            "event_domain": "queue",
            "event_type": "ambiguous_match",
            "entity_or_provision": "Ambiguous",
            "before_json": {},
            "after_json": {"county": "Reeves", "capacity_mw": 500},
            "confidence": 0.6,
            "is_ambiguous": True,
        },
    ]

    scores = [score_change_event(event) for event in events]
    ranked_once = rank_change_events(events, top_n=2)
    ranked_twice = rank_change_events(events, top_n=2)

    assert scores == [25.0, 73.0103, 36.9897]
    assert ranked_once["top_events"][0]["change_event_id"] == "b"
    assert ranked_once == ranked_twice
    assert ranked_once["suppressed_events"][0]["change_event_id"] == "c"
