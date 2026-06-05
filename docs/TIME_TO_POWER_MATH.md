# Time-to-Power Math

Time-to-Power uses deterministic range arithmetic. Each component carries provenance through source rows, metric rows,
rule rows, or assumption rows.

## Baseline Interconnection Timeline

The baseline adapter calls the existing GridQueue metric rollup service.

```text
baseline_low_days = median_duration_days
baseline_high_days = max(p75_duration_days, median_duration_days)
```

If no fallback scope reaches `min_sample_n` or no duration proxy is available:

```text
status = insufficient_interconnection_baseline
```

The output includes `metric_id`, `sample_n`, `fallback_level`, `confidence`, `source_snapshot_id`, and citation metadata.

## Flexibility-Adjusted Timeline

Flexibility can reduce the interconnection timeline only when the existing Flexibility Strategy Layer returns a
supported quantified benefit.

```text
interconnection_with_flex_low_days = baseline_low_days - quantified_delta_days
interconnection_with_flex_high_days = baseline_high_days - quantified_delta_days
```

The values are bounded at zero. If the benefit is contingent, qualitative-only, unsupported, or based on technical
evidence, no day-saved math is applied.

Flexibility does not reduce procurement lead time by default.

## Procurement Critical Path

For each equipment class:

```text
class_low_months = min(supported_low_months)
class_high_months = max(supported_high_months)
```

Binding equipment is the class with the highest `class_high_months`. Months become days through:

```text
days_per_month = 30.4375
procurement_low_days = binding_low_months * days_per_month
procurement_high_days = binding_high_months * days_per_month
```

The constant is stored in assumptions.

## Commissioning And Energization Buffer

The fixture assumption is:

```text
commissioning_low_days = 30
commissioning_high_days = 60
energization_buffer_low_days = 7
energization_buffer_high_days = 14
```

API callers can override those assumptions. They remain planning assumptions, not a commissioning plan.

## Serial Strategy

Post-NTP serial procurement starts after interconnection approval / NTP.

```text
no_flex_serial_low_days =
  interconnection_baseline_low_days
  + procurement_low_days
  + commissioning_low_days
  + energization_buffer_low_days

no_flex_serial_high_days =
  interconnection_baseline_high_days
  + procurement_high_days
  + commissioning_high_days
  + energization_buffer_high_days
```

The flex serial case replaces the baseline interconnection component only when quantified flex support exists.

## Overlap Strategy

At-risk overlap assumes procurement starts before final NTP.

```text
no_flex_overlap_low_days =
  max(interconnection_baseline_low_days, procurement_low_days)
  + commissioning_low_days
  + energization_buffer_low_days

no_flex_overlap_high_days =
  max(interconnection_baseline_high_days, procurement_high_days)
  + commissioning_high_days
  + energization_buffer_high_days
```

The flex overlap case replaces the interconnection component only when quantified flex support exists.

## Uncertainty Propagation

- Missing baseline -> insufficient interconnection baseline.
- Unsupported procurement data -> insufficient procurement data.
- Stale procurement data -> stale procurement data status with caveated range.
- Conflicting procurement data -> conflicting procurement data status with preserved rows.
- Contingent flex -> flex range not computed.
- Qualitative-only flex -> flex range not computed.
