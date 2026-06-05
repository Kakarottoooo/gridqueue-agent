# Flexibility Rules

The rule database stores public FERC, ISO, RTO, ERCOT context, and technical-evidence records used by the Flexibility
Strategy Layer.

## Tables

- `iso_flexibility_rules`: rule/evidence metadata, eligibility criteria, status, benefit text, optional quantified
  benefit JSON, and source URL.
- `flexibility_rule_sources`: citation rows for each rule/evidence record.

Every rule or evidence record must include a `source_url`. Eligibility claims use the citation rows, not uncited text.

## Seeded Records

The seed script is:

```powershell
python scripts/seed_flexibility_rules.py
```

Seed records are conservative demo data and must be manually verified before real-world use.

| Jurisdiction | Provision | Status | Treatment |
| --- | --- | --- | --- |
| FERC | RM26-4 Large Load Interconnection ANOPR | `pending` | Contingent. Not final, not quantified. |
| SPP | High Impact Large Load / Conditional HILL Service | `approved` | Eligibility can be evaluated, but benefits remain qualitative unless quantified benefit JSON is seeded. |
| PJM | Co-located Load Transmission Service Reform | `directed` | Reform pending; no final tariff benefit is assumed. |
| ERCOT | Large Load Interconnection Context | `context_only` | Context only; not a curtailable-load fast-track rule. |
| EVIDENCE | Emerald AI / EPRI DCFlex field demonstration | `technical_evidence` | Evidence anchor for compute flexibility; not a regulatory rule. |
| DEMO | Synthetic quantified flexibility benefit | `final` | Synthetic fixture only for recommendation/eval math. |

## Status Values

Allowed statuses:

- `proposed`
- `pending`
- `directed`
- `approved`
- `final`
- `superseded`
- `context_only`
- `technical_evidence`
- `needs_review`

The eligibility matcher never treats `proposed`, `pending`, `directed`, `context_only`, `technical_evidence`, or
`needs_review` records as final actionable eligibility.

## Eligibility Matching

Criteria are stored as sparse JSON because real-world rules do not share one schema. Supported demo criteria include:

- `peak_mw_threshold`
- `commitment_depth_pct_min`
- `dispatchability_required`
- `curtailability_required`
- `colocation_required`
- `onsite_generation_required`
- `metering_or_control_required`
- `market_or_jurisdiction`
- `service_type`

If a required criterion is missing from the scenario, the matcher returns `ambiguous`. If a criterion is present and
fails, it returns `not_eligible`. If rule status is non-final, it returns `contingent` or `unsupported`.

## Limitations

- Seed records are not a legal or tariff interpretation.
- Public pages can change; statuses should be reverified before production use.
- SPP/PJM/FERC records are not given quantified day-saved values unless a cited source supports that exact value.
- Technical evidence is useful for compute assumptions and extrapolation flags, but it is not treated as an ISO/RTO rule.
