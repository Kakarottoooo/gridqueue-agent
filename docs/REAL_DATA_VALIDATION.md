# Real Data Validation

Fixture mode proves the software mechanics. Real-data validation proves the parser, normalization, entity-resolution, diffing, and reporting logic against public source files.

## Summary
- Did real ERCOT data run? yes
- ERCOT months: 2026-04-30 to 2026-05-31
- Did real LBNL data run? yes
- Validated slice: ERCOT GIS month-over-month generation-resource diff plus LBNL Queued Up workbook reproduction checks.
- This is a real-data validated slice, not a claim that the full platform is production-ready.
- What remains unverified: human entity-resolution labels, additional ERCOT months, other markets, and large-load/data-center queues.

## Source manifest
- source_name=ERCOT GIS Report snapshot_date=2026-04-30 local_path=data\raw\real\ercot\gis\ERCOT_GIS_2026_04.xlsx hash=`bf97215d9749e3d796b554e032a2d4bb5718c42ceccfa444b96bb1e69afc75fd` size_bytes=685461 row_count_raw=2067 parse_status=parsed source_url=https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER
- source_name=ERCOT GIS Report snapshot_date=2026-05-31 local_path=data\raw\real\ercot\gis\ERCOT_GIS_2026_05.xlsx hash=`31f2b596c69c64af537e0653beb9a2ab64bdd2a01e03e4a818b33cbafc5c88cc` size_bytes=676810 row_count_raw=2034 parse_status=parsed source_url=https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER
- source_name=LBNL Queued Up 2026 Data File snapshot_date=2025-12-31 local_path=data\raw\real\lbnl\LBNL_Queued_Up_2026_Data_File.xlsx hash=`794582d3281c6a305e9615fcfec3fae9dc85be2165216d33760b677e976a08b6` size_bytes=15571236 row_count_raw=38201 parse_status=parsed source_url=https://eta.lbl.gov/publications/us-interconnection-queue-data-0

## ERCOT ingestion results
- from_snapshot_id: `snap_real_ercot_gis_2026_04_bf97215d`
- to_snapshot_id: `snap_real_ercot_gis_2026_05_31f2b596`
- from file hash: `bf97215d9749e3d796b554e032a2d4bb5718c42ceccfa444b96bb1e69afc75fd`
- to file hash: `31f2b596c69c64af537e0653beb9a2ab64bdd2a01e03e4a818b33cbafc5c88cc`
- raw parsed source rows: from=2067 to=2034
- normalized deduplicated rows: from=2053 to=2022
- profiles: ['reports\\real_data\\ercot\\profile_2026_04.md', 'reports\\real_data\\ercot\\profile_2026_05.md']
- Sheets parsed include Project Details - Large Gen, Project Details - Small Gen, Commissioning Update, Inactive Projects, and Cancellation Update.
- Optional fields such as permits and detailed milestone dates are preserved in raw payload JSON but not all are normalized into first-class columns.

## ERCOT real monthly diff
- total diff events including unchanged: 2083
- event counts: {'capacity_changed': 7, 'completed_project': 12, 'fuel_type_changed': 3, 'name_changed': 2, 'new_project': 26, 'removed_project': 57, 'status_changed': 10, 'target_cod_accelerated': 4, 'target_cod_delayed': 77, 'unchanged': 1873, 'withdrawn_project': 12}
- watcher-adapted material events: 210
- real digest: `reports\real_data\ercot\real_monthly_digest_2026_04_to_2026_05.md`
- event CSV: `reports\real_data\ercot\real_monthly_diff_events_2026_04_to_2026_05.csv`
- Hard alerts and suppressed events are separated in the digest. removed_project means missing from later snapshot, not automatic withdrawal.
- Required caveat is present in the digest: ERCOT GIS is generation-resource data and is not a complete large-load/data-center queue.

## Entity-resolution audit
- audit CSV: `reports\real_data\entity_resolution_audit\ercot_matches_2026_04_to_2026_05.csv`
- ambiguous CSV: `reports\real_data\entity_resolution_audit\ercot_ambiguous_2026_04_to_2026_05.csv`
- manual review template: `reports\real_data\manual_review\ercot_manual_review_template_2026_04_to_2026_05.csv`
- exact-ID matches: 1996
- strong fuzzy matches: 0
- ambiguous matches: 0
- true additions suggested by system: 26
- true removals/missing suggested by system: 57
- true withdrawals suggested by system: 12
- true completions suggested by system: 12
- manual labels available? no
- Precision/recall is not reported because no human manual labels are present yet.
- System labels are not called manual verification. `auto_verified_exact_id` only means conservative exact INR match.

## LBNL workbook validation
- workbook_id: `lbnl_queued_up_2026_794582d3`
- workbook hash: `794582d3281c6a305e9615fcfec3fae9dc85be2165216d33760b677e976a08b6`
- row_count_raw: 38201
- sheets parsed: 43
- reproduction report: `reports\real_data\lbnl\lbnl_reproduction.md`
- independent calculations CSV: `reports\real_data\lbnl\lbnl_independent_calculations.csv`
- Metrics calculated:
  - active_project_row_count: 8513
  - active_capacity_gw_mw1_only: 1744.7481
  - active_capacity_gw_mw1_mw2_mw3: 1864.7698
  - ercot_active_project_row_count: 1796
  - ercot_active_capacity_gw_mw1_only: 408.0021
  - median_days_request_to_terminal_status: 651.0
- Official summary comparisons:
  - ERCOT active capacity GW: calculated=408.0021 official_summary=408.0 status=matched_within_tolerance delta=0.0021
  - ERCOT active request count: calculated=1796 official_summary=1527 status=mismatch_documented delta=269.0
  - All-region active capacity GW: calculated=1744.7481 official_summary=2061.5 status=mismatch_documented delta=-316.7519
- Mismatches / limitations:
  - ERCOT active request count mismatch: calculated=1796 official_summary=1527 delta=269.0. Count differs; workbook summary appears to apply a summary-specific ERCOT count method while capacity matches.
  - All-region active capacity GW mismatch: calculated=1744.7481 official_summary=2061.5 delta=-316.7519. Mismatch expected because summary tabs include derived/estimated hybrid storage capacity and possibly summary-specific filters.

## Independent checks
- report: `reports/real_data/independent_checks.md`
- status_counts: {'passed': 14}
- ercot raw_row_count_vs_ingested:ERCOT_GIS_2026_04.xlsx: passed (snapshot_id=snap_real_ercot_gis_2026_04_bf97215d hash=bf97215d9749e3d796b554e032a2d4bb5718c42ceccfa444b96bb1e69afc75fd)
- ercot missing_key_fields:ERCOT_GIS_2026_04.xlsx: passed (Rows missing INR or project name under minimal independent parse.)
- ercot status_count_presence:ERCOT_GIS_2026_04.xlsx: passed (Independent status buckets are not expected to exactly match normalized buckets but both should be populated.)
- ercot active_capacity_by_fuel_presence:ERCOT_GIS_2026_04.xlsx: passed (Independent fuel buckets are raw ERCOT fuel labels; app buckets are normalized fuel labels.)
- ercot raw_row_count_vs_ingested:ERCOT_GIS_2026_05.xlsx: passed (snapshot_id=snap_real_ercot_gis_2026_05_31f2b596 hash=31f2b596c69c64af537e0653beb9a2ab64bdd2a01e03e4a818b33cbafc5c88cc)
- ercot missing_key_fields:ERCOT_GIS_2026_05.xlsx: passed (Rows missing INR or project name under minimal independent parse.)
- ercot status_count_presence:ERCOT_GIS_2026_05.xlsx: passed (Independent status buckets are not expected to exactly match normalized buckets but both should be populated.)
- ercot active_capacity_by_fuel_presence:ERCOT_GIS_2026_05.xlsx: passed (Independent fuel buckets are raw ERCOT fuel labels; app buckets are normalized fuel labels.)
- ercot exact_queue_id_overlap_between_months: passed (Exact INR overlap should exist for consecutive ERCOT GIS months.)
- lbnl raw_row_count_vs_ingested: passed (hash=794582d3281c6a305e9615fcfec3fae9dc85be2165216d33760b677e976a08b6)
- lbnl active_capacity_total_mw1_gw: passed (Direct pandas sum of active project-level mw_1.)
- lbnl capacity_by_type_available: passed (Direct pandas type_clean capacity aggregation.)
- lbnl outcome_status_counts_available: passed (Direct pandas q_status counts.)
- lbnl duration_metric_available: passed (Direct pandas median duration for operational/withdrawn rows.)

## Real-data eval results
- report: `evals/results/real_latest.md`
- total: 22
- status_counts: {'passed': 21, 'skipped_manual_review': 1}
- skipped_manual_review is expected until a human reviewer fills manual labels.

## Known limitations
- ERCOT GIS is generation-resource interconnection data, not a full load or data-center queue.
- LBNL Queued Up excludes load interconnection requests, distribution-connected projects, and behind-the-meter projects.
- Entity resolution still needs human spot-checking. The generated CSV has system labels only unless a reviewer fills manual_label.
- LBNL summary tabs can include derived or filtered values that project-level raw component sums do not reproduce exactly.
- Real output is public-data signal analysis, not formal diligence, power-flow study, legal advice, or project-specific verification.

## Next validation target
- Expand to three to six consecutive ERCOT months.
- Hand-label 50 to 100 entity-resolution cases from the manual review CSV.
- Add PJM/MISO only after ERCOT real validation is stable.
- Re-run after each ERCOT monthly release.

## Validation conclusion
Validated slice achieved: the repository contains two real ERCOT GIS monthly reports ingested, a real month-over-month diff and digest, an entity-resolution audit, and a real LBNL workbook reproduction report with documented mismatches.