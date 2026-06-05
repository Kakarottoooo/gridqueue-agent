# Post-NTP Lead-Time Scaffold

The Post-NTP Lead-Time scaffold is an early knowledge-base demo, not a procurement product.

It is downstream of GridQueue's queue and flexibility intelligence. Once a project reaches shovel-ready or NTP status,
long-lead electrical equipment can determine how soon it can actually be energized. Public lead-time data is weaker and
less uniform than queue data, so v1 stores cited ranges and recency flags instead of quotes, prices, or precise promises.

## What V1 Does

- Adds lead-time schema tables.
- Seeds one equipment class: Large Power Transformer.
- Stores range-based lead times with `source_url`, `as_of_date`, `source_type`, confidence, and stale flags.
- Flags conflicting ranges rather than collapsing them into one fake number.
- Exposes a minimal API for seed and lookup.

## What V1 Does Not Do

- No firm quotes.
- No prices.
- No OEM ranking.
- No RFQ workflow.
- No guaranteed delivery timeline.
- No project-specific engineering design.
- No bare point estimate presented as fact.

## Large Power Transformer Demo

The seed script is:

```powershell
python scripts/seed_lead_time_kb.py
```

The default row uses the DOE July 2024 Large Power Transformer Resilience Report as a government-report source. It stores
a 36-to-60 month range because the report discusses commonly quoted 36-month lead times and maximum lead times reaching
as much as 60 months. The row is stored as a planning range, not a procurement quote.

## Citation And Recency Discipline

Every row must include:

- `source_url`
- `as_of_date`
- `source_type`
- `confidence`
- `is_stale`
- `stale_threshold_months`

The current scaffold uses an 18-month stale threshold to force review of older public lead-time data.

## Known Limitations

- One equipment class only.
- No project equipment scoping beyond schema placeholders.
- No combined time-to-power estimate yet.
- No price, vendor, RFQ, or delivery commitment.

## Roadmap

- equipment scope model
- procurement critical path
- combined time-to-power brief
- integration with Flexibility Strategy
