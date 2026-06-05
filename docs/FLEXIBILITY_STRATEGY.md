# Flexibility Strategy Layer

The Flexibility Strategy Layer is a Phase 2 extension to GridQueue Agent. It evaluates public-data, citation-grounded
curtailable-load scenarios for large loads such as AI data centers.

It answers six planning questions:

- What curtailment commitment could the load offer?
- What would that commitment cost in compute terms under explicit assumptions?
- Which public FERC, ISO, or RTO provisions might be relevant?
- Is each provision final, approved, proposed, pending, superseded, contextual, or technical evidence only?
- How does the flexibility scenario compare with the no-flexibility GridQueue baseline?
- Should the system abstain because rules are non-final, eligibility is ambiguous, or the baseline sample is too weak?

## What It Does

- Seeds a small rule/evidence database from public source metadata.
- Computes annual curtailed MWh, equivalent GPU-hours, and compute-side penalty cost.
- Evaluates eligibility with deterministic criteria and conservative rule-status handling.
- Reuses GridQueue metric rollups as the no-flexibility baseline.
- Produces a Flexibility Strategy Brief with assumptions, citations, status labels, caveats, and reproducibility trace.

## Why It Belongs In GridQueue

GridQueue already tracks public interconnection queue signals, baseline metrics, citations, and deterministic briefs.
Flexibility strategy is the upstream decision layer for large-load planning: before a site team can decide whether a
runtime flexibility controller is worth building, it needs a grounded scenario analysis of public rule status, possible
eligibility, and compute-side cost.

## What It Does Not Do

- It is not a runtime curtailment controller.
- It does not schedule GPU workloads.
- It does not submit interconnection filings.
- It is not a formal interconnection study, deliverability study, power-flow result, legal opinion, financial advice, or
  guarantee of interconnection approval.
- It does not estimate actual grid capacity or upgrade costs.
- It does not treat proposed rules as guaranteed benefits.

## Baseline Reuse

The benefit model calls the existing GridQueue metric rollup service. Every baseline trace includes:

- `baseline_metric_id`
- `baseline_timeline_days`
- `sample_n`
- `fallback_level`
- `confidence`
- `source_snapshot_id`

If the baseline is insufficient or lacks a duration proxy, the benefit model returns `insufficient_baseline` and does
not estimate timeline savings.

## Why Rule Status Matters

Rule status is load-bearing. A pending ANOPR, directed reform, or context-only public update can shape planning but
cannot support a final eligibility conclusion or quantified timeline benefit. GridQueue therefore uses conservative
statuses:

- proposed/pending/directed/needs_review: contingent or ambiguous.
- context_only/technical_evidence/superseded: unsupported for regulatory eligibility.
- approved/final: eligible only if deterministic criteria match; quantified only if cited quantified benefits are
  seeded.

## Why Compute Assumptions Are Exposed

The compute-cost model is deterministic, but its economics depend on user assumptions. Every output exposes the
assumptions used for GPU power, workload mix, event duration, events per year, and penalty values. The default demo
assumption is anchored to public technical evidence for extrapolation checks, but the penalty values are scenario
assumptions, not public market facts.
