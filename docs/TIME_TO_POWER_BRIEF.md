# Time-to-Power Brief

The Time-to-Power Brief is the Phase 4 integration layer for GridQueue Agent. It combines the existing public queue
baseline, Flexibility Strategy Layer, Monthly Watcher context, and Post-NTP Lead-Time scaffold into one planning
artifact for large-load and generation-adjacent project scenarios.

It is not a new standalone product. It reuses the same deterministic services, citations, source metadata,
sample-aware rollups, abstention behavior, fixture strategy, and eval discipline already used by GridQueue Core.

## What It Does

- Computes a baseline interconnection range from GridQueue sample-aware metric rollups.
- Computes a flexibility-adjusted scenario only when existing flexibility evidence supports it.
- Builds a planning-level equipment scope from transparent deterministic rules or preserved manual input.
- Maps scoped equipment to cited lead-time ranges and identifies the procurement critical path.
- Combines interconnection, procurement, commissioning, and energization-buffer assumptions into serial and overlap
  Time-to-Power ranges.
- Generates a markdown brief with assumptions, citations, caveats, and reproducibility trace.

## What It Does Not Do

This Time-to-Power Brief is a public-data planning artifact. It is not a formal interconnection study, deliverability
study, power-flow result, legal opinion, engineering design, procurement quote, OEM RFQ, commissioning plan, financial
forecast, or guarantee of energization.

It does not submit queue requests, estimate upgrade costs, price equipment, rank vendors, run RFQs, perform EPC design,
or promise that a project can be energized by a date.

## How It Connects Existing Layers

1. GridQueue Core provides the no-flexibility interconnection baseline through `metric_rollups`.
2. Flexibility Strategy provides rule status, eligibility, compute-cost assumptions, and benefit status.
3. Post-NTP Lead-Time provides cited equipment lead-time ranges.
4. Time-to-Power combines those components into serial and overlap ranges.

## Uncertainty Handling

The brief carries uncertainty instead of hiding it:

- insufficient baseline samples produce `insufficient_interconnection_baseline`;
- proposed or pending flexibility rules remain `contingent`;
- technical evidence is not treated as regulation;
- missing lead-time rows produce procurement caveats or abstention;
- stale lead-time rows trigger stale warnings;
- conflicting lead-time ranges are preserved and flagged;
- no bare lead-time point estimates are emitted.

## Why Ranges

Interconnection timelines and equipment lead times are not precise public facts. GridQueue therefore reports low/high
ranges and the provenance for each component. Lead-time months are converted to days with the explicit assumption
`days_per_month = 30.4375`, stored in `assumptions_json`.

## Serial vs Overlap

`post_ntp_serial` is the conservative default. Procurement starts after interconnection approval / NTP:

```text
interconnection + procurement + commissioning + energization_buffer
```

`at_risk_overlap` is optional and heavily caveated. Procurement starts before final NTP at user risk:

```text
max(interconnection, procurement) + commissioning + energization_buffer
```

Overlap can shorten a planning range but can also strand spend if interconnection outcomes change.

## Evals

The eval suite checks that the brief does not overclaim. It validates baseline provenance, contingent flexibility,
technical-evidence treatment, lead-time ranges and source metadata, stale/conflict flags, serial and overlap math,
at-risk caveats, required caveat text, and end-to-end fixture demo generation.
