# Compute Cost Model

The compute-cost model estimates the compute-side cost of offering a curtailable-load commitment. It is deterministic
and assumption-explicit.

## Inputs

- `peak_mw`
- `average_load_factor`
- `commitment_depth_pct`
- `event_duration_hours`
- `events_per_year`
- `deferrable_workload_fraction`
- `latency_sensitive_fraction`
- `migratable_fraction`
- `gpu_power_kw`
- `gpu_hour_value_usd`
- `deferral_penalty_per_gpu_hour_usd`
- `migration_penalty_per_gpu_hour_usd`
- `dropped_work_penalty_per_gpu_hour_usd`

All constants used in the formula must come from a `compute_cost_assumptions` record or an API request that creates one.

## Formulas

```text
annual_curtailed_mwh =
  peak_mw * commitment_depth_pct / 100 * event_duration_hours * events_per_year

equivalent_gpu_hours =
  annual_curtailed_mwh * 1000 / gpu_power_kw

deferred_gpu_hours =
  equivalent_gpu_hours * deferrable_workload_fraction

migrated_gpu_hours =
  equivalent_gpu_hours * migratable_fraction

dropped_or_unserved_gpu_hours =
  equivalent_gpu_hours - deferred_gpu_hours - migrated_gpu_hours

estimated_compute_cost_usd =
  deferred_gpu_hours * deferral_penalty_per_gpu_hour_usd
  + migrated_gpu_hours * migration_penalty_per_gpu_hour_usd
  + dropped_or_unserved_gpu_hours * dropped_work_penalty_per_gpu_hour_usd
```

Deferrable workloads absorb curtailment first, migratable workloads absorb remaining curtailment second, and remaining
curtailed compute is treated as dropped or unserved.

## Evidence Anchor

The default assumptions cite the Emerald AI / EPRI DCFlex field demonstration paper:

https://arxiv.org/html/2507.00909v1

The public field-demo anchor used by GridQueue is 25 percent load reduction for three hours. If a scenario has
`commitment_depth_pct > 25` or `event_duration_hours > 3`, the output sets `extrapolation_flag = true`.

## Limitations

- The model does not claim actual workload performance.
- GPU power and penalty values are scenario assumptions, not public market facts.
- The model does not account for cluster topology, network bottlenecks, data locality, checkpoint overhead, or SLA
  contract structure.
- It does not estimate utility payments, upgrade costs, or financial returns unless the user supplies explicit
  value-per-day assumptions for scenario scoring.
