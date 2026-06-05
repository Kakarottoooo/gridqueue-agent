# LBNL Queued Up real workbook reproduction

## Source
- source_url: https://eta.lbl.gov/publications/us-interconnection-queue-data-0
- download_url: https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx
- workbook_id: `lbnl_queued_up_2026_794582d3`
- file_hash_sha256: `794582d3281c6a305e9615fcfec3fae9dc85be2165216d33760b677e976a08b6`
- project_row_count: 38201

## Metrics calculated
- project_row_count: 38201
- active_project_row_count: 8513
- active_capacity_gw_mw1_only: 1744.7481
- active_capacity_gw_mw1_mw2_mw3: 1864.7698
- ercot_active_project_row_count: 1796
- ercot_active_capacity_gw_mw1_only: 408.0021
- median_days_request_to_terminal_status: 651.0

## Active capacity by type
- Solar+Battery: rows=1716 capacity_gw=403.7582
- Solar: rows=2742 capacity_gw=396.6147
- Battery: rows=2078 capacity_gw=385.3298
- Gas: rows=622 capacity_gw=240.0239
- Wind: rows=751 capacity_gw=177.7638
- Other: rows=166 capacity_gw=33.0213
- Offshore Wind: rows=23 capacity_gw=23.4268
- Wind+Battery: rows=53 capacity_gw=15.9497
- Nuclear: rows=47 capacity_gw=10.393
- Solar+Wind+Battery: rows=27 capacity_gw=8.661
- Other+Battery: rows=63 capacity_gw=8.6553
- Other Storage: rows=15 capacity_gw=6.1215

## Official summary comparison
- ERCOT active capacity GW: calculated=408.0021 official_summary=408.0 delta=0.0021 status=matched_within_tolerance reason=Project-level mw_1 capacity for active ERCOT rows rounds to workbook summary tab capacity.
- ERCOT active request count: calculated=1796 official_summary=1527 delta=269.0 status=mismatch_documented reason=Count differs; workbook summary appears to apply a summary-specific ERCOT count method while capacity matches.
- All-region active capacity GW: calculated=1744.7481 official_summary=2061.5 delta=-316.7519 status=mismatch_documented reason=Mismatch expected because summary tabs include derived/estimated hybrid storage capacity and possibly summary-specific filters.

## Mismatches and limitations
- ERCOT active request count mismatch: calculated=1796 official_summary=1527 delta=269.0. Count differs; workbook summary appears to apply a summary-specific ERCOT count method while capacity matches.
- All-region active capacity GW mismatch: calculated=1744.7481 official_summary=2061.5 delta=-316.7519. Mismatch expected because summary tabs include derived/estimated hybrid storage capacity and possibly summary-specific filters.

## Caveats
- The LBNL Queued Up workbook includes generation and storage requests seeking transmission-grid interconnection; it does not include load interconnection requests, distribution-connected projects, or behind-the-meter projects.
- Workbook summary tabs may include derived/estimated hybrid storage capacity and summary-specific filters; project-level raw component sums are not forced to match when the workbook method is not encoded in the project sheet.

Independent calculation CSV: `reports\real_data\lbnl\lbnl_independent_calculations.csv`