# Time-to-Power Brief: Fixture Time-to-Power Scenario

## Executive summary
- Baseline interconnection proxy uses metric_id=met_635db26eb8ed4a15 with sample_n=3, fallback_level=county_fuel, confidence=Low.
- Post-NTP serial no-flex Time-to-Power range is 2547.75-3315.25 days.
- At-risk overlap no-flex comparison range is 1452.00-1900.25 days; overlap requires explicit user risk acceptance.
- Flexibility benefit_status=contingent; procurement lead time is unchanged by default.
- Binding constraint under selected strategy is procurement; estimate status=conflicting_procurement_data.

## Project scenario
- Market / jurisdiction: ERCOT / FERC
- Project type: AI data center load
- County / region: Reeves / NA
- Peak load: 300.0 MW
- Interconnection voltage: 345.0 kV
- Procurement strategy: post_ntp_serial

## Interconnection baseline
- Range: 1415.00-1415.00 days
- metric_id: met_635db26eb8ed4a15
- sample_n: 3
- fallback_level: county_fuel
- confidence: Low
- source_snapshot_id: snap_ercot_2026_02_28

## Flexibility-adjusted scenario
- rule_status: pending
- eligibility_status: contingent
- benefit_status: contingent
- interconnection_with_flex_range: not computed
- Procurement path impact: unchanged by default.

## Procurement critical path
- Binding equipment: Large Power Transformer
- Binding lead-time range: 36.00-60.00 months
- Procurement days range: 1095.75-1826.25 days
- stale_flag: True
- conflict_flag: True
- unsupported_flag: False

## Energization timeline
- Serial post-NTP: procurement starts after interconnection approval / NTP.
- At-risk overlap: procurement starts before final NTP and can strand spend if outcomes change.
- no_flex_serial: 2547.75-3315.25 days (post-NTP serial)
- flex_serial: not computed (post-NTP serial with quantified flex only)
- no_flex_overlap: 1452.00-1900.25 days (at-risk procurement overlap)
- flex_overlap: not computed (at-risk overlap with quantified flex only)

## Scenario comparison table
| case | low_days | high_days | assumption |
| --- | ---: | ---: | --- |
| no_flex_serial | 2547.75 | 3315.25 | post-NTP serial |
| flex_serial | NA | NA | post-NTP serial with quantified flex only |
| no_flex_overlap | 1452.0 | 1900.25 | at-risk procurement overlap |
| flex_overlap | NA | NA | at-risk overlap with quantified flex only |

## Binding constraints
- selected_case: no_flex_serial
- binding_constraint: procurement
- status: conflicting_procurement_data
- status_explanation: Lead-time sources conflict; ranges are preserved and flagged.

## Assumptions
- serial_formula: interconnection + procurement + commissioning + energization_buffer
- overlap_formula: max(interconnection, procurement) + commissioning + energization_buffer
- days_per_month: 30.4375

## Citations
- Interconnection baseline metric source: synthetic://gridqueue-agent/fixtures/ercot-gis-like
- Large Power Transformer lead-time source: https://www.energy.gov/sites/default/files/2024-10/EXEC-2022-001242%20-%20Large%20Power%20Transformer%20Resilience%20Report%20signed%20by%20Secretary%20Granholm%20on%207-10-24.pdf
- HV Switchgear / GIS lead-time source: synthetic://gridqueue-agent/fixtures/time-to-power-lead-times
- HV Switchgear / GIS lead-time source: synthetic://gridqueue-agent/fixtures/time-to-power-lead-times
- Medium-Voltage Switchgear lead-time source: synthetic://gridqueue-agent/fixtures/time-to-power-lead-times
- Large Load Interconnection ANOPR: https://www.ferc.gov/rm26-4
- Compute flexibility evidence anchor: https://arxiv.org/html/2507.00909v1
- Commissioning and energization buffer assumption: synthetic://gridqueue-agent/fixtures/time-to-power-commissioning

## Reproducibility trace
- scenario_id=ttp_scenario_239ec5d2413147e6
- baseline_metric_id=met_635db26eb8ed4a15, sample_n=3, fallback_level=county_fuel, confidence=Low
- critical_path_id=crit_4c2310a371b94790, binding_equipment_class=Large Power Transformer
- flexibility_status: rule_status=pending, benefit_status=contingent
- timeline_math: ranges are computed in days; lead-time months use days_per_month=30.4375.

## Caveats and abstentions
- This Time-to-Power Brief is a public-data planning artifact. It is not a formal interconnection study, deliverability study, power-flow result, legal opinion, engineering design, procurement quote, OEM RFQ, commissioning plan, financial forecast, or guarantee of energization.
- This Time-to-Power estimate is a public-data planning artifact, not a formal study, procurement quote, engineering design, or guarantee.
- Baseline is a sample-aware historical proxy from public queue records, not a formal interconnection study.
- Large-load scenarios use generation-queue proxy records where no verified large-load queue fixture is available.
- Procurement critical path is a public-data planning proxy only. It is not a procurement quote, OEM RFQ, supplier commitment, price, engineering design, or delivery guarantee.
- One or more lead-time sources are stale under the configured threshold and require manual review.
- Multiple sourced lead-time ranges conflict; GridQueue preserves all rows and flags the conflict instead of collapsing precision.
- No lead-time KB row exists for: Commissioning / Testing Package, Interconnection Facilities, Protection / Control / Metering Package.
- Flexibility does not reduce procurement lead time by default.
- No quantified day-saved timeline math is applied because the flexibility evidence is contingent, qualitative-only, unsupported, or insufficient.
- Rule status is pending; proposed or pending benefits remain contingent and are not treated as final.
- Equipment scope is a planning-level model only. It is not a stamped engineering design, EPC scope, OEM RFQ, or guarantee that these are the exact project facilities.