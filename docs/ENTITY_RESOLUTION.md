# Entity Resolution

GridQueue links normalized records across snapshots into stable `project_entities`. The algorithm is deterministic
and explainable by design.

## Features

Each latest-snapshot record is compared with prior-snapshot candidate records using:

- exact queue ID match
- normalized project-name similarity
- interconnecting-entity similarity
- county and state match
- compatible fuel transition, such as Solar to Hybrid
- capacity tolerance, using the greater of 5 MW or 2 percent
- point-of-interconnection similarity
- target COD proximity within 180 days

## Scoring

The MVP weights are:

- exact queue ID: 0.38
- name similarity above 0.90: 0.22
- name similarity from 0.75 to 0.90: 0.14
- interconnecting entity similarity above 0.85: 0.10
- county match: 0.09
- state match: 0.04
- compatible fuel: 0.10
- capacity within tolerance: 0.10
- similar POI: 0.07
- target COD within 180 days: 0.04

Scores are capped at 1.0. A high-confidence match is `>= 0.76`; possible match is `>= 0.58`.
If the top two candidates are within 0.05, the match is flagged ambiguous.

## Ambiguity policy

Ambiguous matches are not forced into an existing entity. The latest row gets a new entity link marked
`is_ambiguous=true`, and `match_features_json` stores the top candidate evidence. The monthly diff engine emits
an `ambiguous_match` event so the UI and brief can surface uncertainty.

## Why row diff is not enough

Naive row diff would misclassify several common queue behaviors:

- a renamed project as a new project
- a queue ID change as a withdrawal plus addition
- a Solar to Hybrid reclassification as a deletion plus addition
- two similarly named projects as a confident match when the evidence is tied

GridQueue tests these cases in synthetic fixtures and deterministic evals.

## Limitations

The algorithm is intentionally deterministic and does not use embeddings. That makes it auditable but imperfect.
Future versions could add supervised calibration, market-specific tuning, and human review queues while preserving
the current evidence trail.

