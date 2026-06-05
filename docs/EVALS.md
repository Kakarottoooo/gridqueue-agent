# Evals

GridQueue uses deterministic evals instead of LLM-output similarity. The goal is to test domain-critical behavior
that should not drift.

## Runner

```powershell
python evals/run_evals.py
```

The runner rebuilds the fixture database, seeds flexibility rules, executes the GridQueue core and Flexibility Strategy
cases, and writes:

- `evals/results/latest.json`
- `evals/results/latest.md`

## Current GridQueue core cases

1. Renamed project should not be counted as new.
2. Queue ID changed but same entity should match.
3. Fuel type reclassification should become `fuel_type_changed`.
4. Capacity change above threshold should emit `capacity_changed`.
5. Target COD delay above threshold should emit `target_cod_delayed`.
6. Ambiguous match should be flagged.
7. Small county plus fuel sample should roll up to broader scope.
8. Insufficient sample should abstain.
9. Brief must include citations.
10. Brief must include formal-study caveat.
11. Data center or large-load question must not misuse generation-only queue data.
12. Latest snapshot should be used for current snapshot output.

Fewer high-quality evals are better than many weak evals because each case guards a concrete domain failure mode.

## Flexibility Strategy cases

1. FERC proposed/pending rule must be contingent, not final eligible.
2. Emerald/EPRI technical evidence must not be treated as a regulatory rule.
3. Every eligibility claim must include a source URL.
4. Missing control/metering criteria must produce ambiguous or unsupported, not eligible.
5. Compute-cost output must expose every assumption used.
6. Commitment above 25 percent or event duration above 3 hours must be marked as extrapolation.
7. Baseline timeline must trace to a GridQueue metric with `sample_n`, `fallback_level`, and confidence.
8. Insufficient baseline must produce `insufficient_baseline` or abstention.
9. Qualitative-only benefits must not produce a hard ROI recommendation.
10. Quantified fixture benefit plus `value_per_day_usd` must choose the maximum `net_benefit_score`.
11. Flexibility Strategy Brief must include the formal caveat.
12. Flexibility Strategy Brief must not claim guaranteed approval or actual grid capacity.
13. Existing 12 GridQueue evals must remain in the core category.
14. Rule statuses must be shown in brief output.

The latest report separates `gridqueue_core` and `flexibility_strategy` categories.
