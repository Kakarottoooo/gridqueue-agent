# Evals

GridQueue uses deterministic evals instead of LLM-output similarity. The goal is to test domain-critical behavior
that should not drift.

## Runner

```powershell
python evals/run_evals.py
```

The runner rebuilds the fixture database, executes 12 cases, and writes:

- `evals/results/latest.json`
- `evals/results/latest.md`

## Current cases

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

