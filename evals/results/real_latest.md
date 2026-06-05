# Real-data eval results

- total: 22
- status_counts: {'passed': 21, 'skipped_manual_review': 1}

## ercot_real_ingestion

- ercot_ingestion_01 `passed`: ERCOT manifest entries=2
- ercot_ingestion_02 `passed`: ERCOT independent row-count checks=2
- ercot_ingestion_03 `passed`: ERCOT profile mapped queue_id/project_name/capacity fields.
- ercot_ingestion_04 `passed`: ERCOT normalized rows are present and tied to raw payload records.

## ercot_real_diff

- ercot_diff_05 `passed`: Top traceable events=20
- ercot_diff_06 `passed`: Ambiguous digest rows are not hard alerts.
- ercot_diff_07 `passed`: Exact INR matches=1996
- ercot_diff_08 `passed`: Removed events=57
- ercot_diff_09 `passed`: capacity_changed count=7
- ercot_diff_10 `passed`: COD move count=81

## entity_resolution_human_labels

- entity_11 `skipped_manual_review`: No human manual labels are present; precision eval is skipped, not passed.

## lbnl_real_reproduction

- lbnl_13 `passed`: LBNL workbook profile has project sheet and rows.
- lbnl_14 `passed`: LBNL calculated metric fields=9
- lbnl_15 `passed`: At least one LBNL metric matches an official workbook summary tab.
- lbnl_16 `passed`: LBNL mismatches/limitations are documented.
- lbnl_17 `passed`: LBNL reproduction caveats exclude load-interconnection claims.

## report_quality

- report_18 `passed`: docs/REAL_DATA_VALIDATION.md exists with source manifest section.
- report_19 `passed`: ERCOT digest path=reports\real_data\ercot\real_monthly_digest_2026_04_to_2026_05.md
- report_20 `passed`: LBNL reproduction path=reports\real_data\lbnl\lbnl_reproduction.md
- report_21 `passed`: README includes Real Data Validation Sprint section.
- report_22 `passed`: Validation report distinguishes fixture and real-data modes.

## independent_checks

- independent_23 `passed`: Independent check statuses={'passed': 14}
