# Metrics and Rollups

GridQueue computes historical proxy metrics with sample-size-aware fallback. It does not report precise-looking
rates from narrow samples.

## Metrics

- `active_count`
- `active_mw`
- `completed_count`
- `withdrawn_count`
- `completion_rate`
- `withdrawal_rate`
- `median_duration_days`
- `p75_duration_days`

Durations are computed only when the required request and completion or withdrawal dates are present.
Missing dates are not treated as zero.

## Rollup path

The default fallback path is:

1. county plus fuel type
2. county across all fuel types
3. market plus fuel type
4. market across all fuel types
5. LBNL national plus fuel type, when available
6. LBNL national across all fuel types, when available
7. abstain

## Sample thresholds

The production default is `min_sample_n=30` for rates.
Fixture demos and evals use lower thresholds when explicitly passed so deterministic behavior can be shown with
small offline files.

Confidence labels:

- High: sample_n >= 100
- Medium: sample_n >= 30
- Low: sample_n clears a smaller configured threshold or uses broader fallback
- Insufficient: no meaningful sample reaches the threshold

Every metric response includes `sample_n`, `fallback_level`, `confidence`, and an explanation.

