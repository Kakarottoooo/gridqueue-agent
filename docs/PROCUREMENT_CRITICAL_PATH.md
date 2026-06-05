# Procurement Critical Path

The procurement critical-path layer maps a planning-level equipment scope to cited lead-time ranges. It is a public-data
planning scaffold, not a procurement product.

## Equipment Scope Model

`backend/app/services/time_to_power/equipment_scope.py` supports:

- AI data center load;
- generic large load;
- battery storage;
- solar + storage.

Generated items include explanations and are labeled as deterministic planning-model output. Manual scope input is
preserved as `manual_user_selected`. If required inputs are missing or the project type is unsupported, the model
returns `insufficient_data` instead of inventing a scope.

## Lead-Time KB

The critical path reads `equipment_lead_times` rows. Each usable row must include:

- equipment class;
- low and high lead-time months;
- source URL;
- as-of date;
- confidence;
- stale threshold.

The existing DOE Large Power Transformer row remains a public-source planning proxy. Time-to-Power fixture rows for
HV switchgear, medium-voltage switchgear, and GSU transformers are synthetic and clearly labeled as demo data.

## Critical Path Calculation

For each scoped equipment class:

1. collect all matching lead-time rows;
2. discard or flag rows missing source URL or as-of date;
3. preserve all conflicting ranges;
4. derive class low months from the minimum low range;
5. derive class high months from the maximum high range;
6. choose the binding item by highest high-end lead time;
7. convert months to days using `days_per_month = 30.4375`.

The output includes `binding_equipment_class`, low/high months, low/high days, stale/conflict/unsupported flags,
citations, assumptions, and caveats.

## Staleness And Conflicts

Staleness is not hidden. Public lead-time rows older than the configured threshold are still shown but flagged.

Conflicting ranges are not collapsed into fake precision. GridQueue preserves the source rows and sets
`conflict_flag = true`.

## Caveats

The procurement critical path is not a quote, price, supplier commitment, OEM RFQ, engineering design, EPC scope, or
delivery guarantee. It is only a planning signal until project-specific procurement evidence exists.
