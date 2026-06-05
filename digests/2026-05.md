# Monthly Regulatory + Queue Change Watcher: 2026-05

## Executive summary
- 7 queue hard-alert changes and 3 regulatory/rule hard-alert changes were selected by deterministic materiality scoring.
- 2 ambiguous queue events were suppressed from hard-alert sections and listed for review.
- 2 source parse failures require manual review; failed content is not summarized as parsed.

## Top queue changes
- `chg_5c61184da9c341a4` withdrawn_project (73.0103, confidence=1.0): Latest snapshot reports the project status as Withdrawn. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_2bb8bddb05514ba1` withdrawn_project (67.7815, confidence=1.0): Latest snapshot reports the project status as Withdrawn. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_edaa602d7e7a4fd8` completed_project (61.9897, confidence=1.0): Latest snapshot reports the project status as Completed. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_6e963f99c8a14d03` target_cod_delayed (61.7609, confidence=1.0): Target COD moved later by 137 days, above the 90-day threshold. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_a8c28c19c9574245` new_project (60.4139, confidence=0.9): Project entity appears in the later snapshot without a non-ambiguous prior match. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_01605e82ed6040cd` capacity_changed (59.5424, confidence=1.0): Capacity changed by more than the configured tolerance of the greater of 5 MW or 2%. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_303012ed4d7040c6` fuel_type_changed (45.7918, confidence=1.0): Normalized fuel type changed for the same resolved project entity. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]

## Top regulatory changes
- `chg_53a7e87c325b4560` rule_source_changed (45.0, confidence=0.9): FERC April 16 2026 large-load docket update content hash changed; no automatic rule status update was made. [source: https://www.ferc.gov/news-events/news/ferc-act-large-load-interconnection-docket-june-2026]
- `chg_7627a8378179426f` rule_source_changed (45.0, confidence=0.9): FERC SPP HILL concurrence and acceptance context content hash changed; no automatic rule status update was made. [source: https://www.ferc.gov/news-events/news/commissioner-rosners-concurrence-order-accepting-tariff-revisions-subject]
- `chg_5d653070875f42d6` rule_source_changed (45.0, confidence=0.9): Flexibility rule: High Impact Large Load / Conditional HILL Service content hash changed; no automatic rule status update was made. [source: https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/]

## Flexibility rule watch
- `chg_5d653070875f42d6` rule_source_changed (45.0, confidence=0.9): Flexibility rule: High Impact Large Load / Conditional HILL Service content hash changed; no automatic rule status update was made. [source: https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/]
- `chg_9e406fd926f24168` rule_source_changed (45.0, confidence=0.9): Flexibility rule: Large Load Interconnection ANOPR content hash changed; no automatic rule status update was made. [source: https://www.ferc.gov/rm26-4]
- `chg_e2a376403d0d4644` rule_source_changed (35.0, confidence=0.9): Flexibility rule: Co-located Load Transmission Service Reform content hash changed; no automatic rule status update was made. [source: https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace]
- `chg_2b94c53ba75c4ef1` rule_source_changed (35.0, confidence=0.9): Flexibility rule: Synthetic quantified flexibility benefit content hash changed; no automatic rule status update was made. [source: synthetic://gridqueue-agent/fixtures/flexibility-quantified-benefit]
- `chg_d541d16af1544118` rule_source_changed (35.0, confidence=0.9): Flexibility rule: Large Load Interconnection Context content hash changed; no automatic rule status update was made. [source: https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf]
- `chg_29767e82de9141d3` rule_source_changed (35.0, confidence=0.9): Flexibility rule: Data center flexibility field demonstration content hash changed; no automatic rule status update was made. [source: https://arxiv.org/html/2507.00909v1]
- `chg_66e14d4ee32d4114` source_unchanged (10.0, confidence=0.9): Flexibility rule: High Impact Large Load / Conditional HILL Service content hash did not change. [source: https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/]
- `chg_03ff4e57635d4efa` source_unchanged (10.0, confidence=0.9): Flexibility rule: Large Load Interconnection ANOPR content hash did not change. [source: https://www.ferc.gov/rm26-4]
- `chg_fe611f9efe1546ae` source_unchanged (0.0, confidence=0.9): Flexibility rule: Co-located Load Transmission Service Reform content hash did not change. [source: https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace]
- `chg_52e4780a8a0c4bd7` source_unchanged (0.0, confidence=0.9): Flexibility rule: Synthetic quantified flexibility benefit content hash did not change. [source: synthetic://gridqueue-agent/fixtures/flexibility-quantified-benefit]

## Ambiguous / suppressed queue noise
- `chg_d5c04ee80ca545d7` ambiguous_match (28.8081, confidence=0.68): The latest record resembles multiple prior projects; GridQueue did not force the match. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]
- `chg_63e82b5f0075467a` ambiguous_match (28.7506, confidence=0.68): The latest record resembles multiple prior projects; GridQueue did not force the match. [source: synthetic://gridqueue-agent/fixtures/ercot-gis-like]

## Parse failures / manual review required
- `chg_e16d3b59ff734583` source_parse_failed (35.0, confidence=0.4): Manual fixture parser failure could not be parsed; manual review is required. [source: synthetic://gridqueue-agent/fixtures/watcher/parse-failure]
- `chg_a9401f987683490d` source_parse_failed (35.0, confidence=0.4): Manual fixture parser failure could not be parsed; manual review is required. [source: synthetic://gridqueue-agent/fixtures/watcher/parse-failure]

## Metrics summary
- {'market': 'ERCOT', 'county': 'Reeves', 'fuel_type': 'Battery', 'sample_n': 3, 'fallback_level': 'county_fuel', 'confidence': 'Low'}

## Citations and source URLs
- Withdrawn Wind Alpha: event=chg_5c61184da9c341a4, source=synthetic://gridqueue-agent/fixtures/ercot-gis-like
- SPP High Impact Large Load / CHILL page: event=chg_085502e567b149b2, source=https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/
- Flexibility rule: Large Load Interconnection ANOPR: event=chg_9e406fd926f24168, source=https://www.ferc.gov/rm26-4
- FERC SPP HILL concurrence and acceptance context: event=chg_7627a8378179426f, source=https://www.ferc.gov/news-events/news/commissioner-rosners-concurrence-order-accepting-tariff-revisions-subject
- FERC April 16 2026 large-load docket update: event=chg_53a7e87c325b4560, source=https://www.ferc.gov/news-events/news/ferc-act-large-load-interconnection-docket-june-2026
- Manual fixture regulatory update: event=chg_cd352039d8744c74, source=synthetic://gridqueue-agent/fixtures/watcher/manual-regulatory-update
- Manual fixture parser failure: event=chg_e16d3b59ff734583, source=synthetic://gridqueue-agent/fixtures/watcher/parse-failure
- Flexibility rule: Co-located Load Transmission Service Reform: event=chg_e2a376403d0d4644, source=https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace
- Flexibility rule: Synthetic quantified flexibility benefit: event=chg_2b94c53ba75c4ef1, source=synthetic://gridqueue-agent/fixtures/flexibility-quantified-benefit
- Flexibility rule: Large Load Interconnection Context: event=chg_d541d16af1544118, source=https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf
- Flexibility rule: Data center flexibility field demonstration: event=chg_29767e82de9141d3, source=https://arxiv.org/html/2507.00909v1

## Reproducibility trace
- queue_adapter: diff_events converted into change_events with ambiguous_match kept non-hard-alert.
- regulatory_snapshot: watch_sources normalized to content_hash before source_snapshots and change_events.
- materiality: deterministic BASE_WEIGHTS plus capacity/timeline/watchlist modifiers, top_n=10.
- digest: every listed event carries change_event_id plus source_url or snapshot id.

## Caveats
- This digest is a public-data monitoring artifact. It does not replace formal interconnection studies, legal review, regulatory counsel, power-flow studies, procurement quotes, or project-specific diligence.