from __future__ import annotations

import pytest

from app.services.flexibility.compute_cost import ASSUMPTION_FIELDS, calculate_compute_cost


def _assumption(**overrides):
    base = {
        "assumption_id": "assumption_test",
        "peak_mw": 100.0,
        "average_load_factor": 0.85,
        "deferrable_workload_fraction": 0.5,
        "latency_sensitive_fraction": 0.25,
        "migratable_fraction": 0.25,
        "gpu_power_kw": 0.5,
        "gpu_hour_value_usd": 3.0,
        "deferral_penalty_per_gpu_hour_usd": 1.0,
        "migration_penalty_per_gpu_hour_usd": 2.0,
        "dropped_work_penalty_per_gpu_hour_usd": 3.0,
        "default_event_duration_hours": 3.0,
        "default_events_per_year": 20,
        "evidence_anchor_json": {"source_url": "https://arxiv.org/html/2507.00909v1"},
    }
    return {**base, **overrides}


def test_compute_cost_formula_exposes_every_assumption() -> None:
    result = calculate_compute_cost(
        peak_mw=100,
        commitment_depth_pct=10,
        event_duration_hours=2,
        events_per_year=4,
        assumption=_assumption(),
    )

    assert result["annual_curtailed_mwh"] == 80
    assert result["equivalent_gpu_hours"] == 160000
    assert result["deferred_gpu_hours"] == 80000
    assert result["migrated_gpu_hours"] == 40000
    assert result["dropped_or_unserved_gpu_hours"] == 40000
    assert result["estimated_compute_cost_usd"] == 280000
    assert set(result["assumptions_json"]) == set(ASSUMPTION_FIELDS)


def test_compute_cost_uses_penalties_from_assumptions_not_hidden_constants() -> None:
    low_penalty = calculate_compute_cost(
        peak_mw=10,
        commitment_depth_pct=10,
        event_duration_hours=1,
        events_per_year=1,
        assumption=_assumption(
            deferral_penalty_per_gpu_hour_usd=0,
            migration_penalty_per_gpu_hour_usd=0,
            dropped_work_penalty_per_gpu_hour_usd=0,
        ),
    )
    high_penalty = calculate_compute_cost(
        peak_mw=10,
        commitment_depth_pct=10,
        event_duration_hours=1,
        events_per_year=1,
        assumption=_assumption(
            deferral_penalty_per_gpu_hour_usd=10,
            migration_penalty_per_gpu_hour_usd=20,
            dropped_work_penalty_per_gpu_hour_usd=30,
        ),
    )

    assert low_penalty["estimated_compute_cost_usd"] == 0
    assert high_penalty["estimated_compute_cost_usd"] > 0


@pytest.mark.parametrize("commitment,event_hours", [(30, 3), (25, 4)])
def test_compute_cost_marks_extrapolation_above_public_anchor(commitment: float, event_hours: float) -> None:
    result = calculate_compute_cost(
        peak_mw=100,
        commitment_depth_pct=commitment,
        event_duration_hours=event_hours,
        events_per_year=1,
        assumption=_assumption(),
    )

    assert result["extrapolation_flag"] is True
