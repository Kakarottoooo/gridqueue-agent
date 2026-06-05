# Eval cases

GridQueue evals are deterministic Python checks over fixture data. They focus on a small
set of high-value failure modes instead of broad text similarity:

- entity-resolution false positives and false negatives
- monthly diff semantics
- sample-aware metric rollups and abstentions
- citation and caveat requirements in generated briefs

The executable source of truth is `evals/run_evals.py`; generated reports are written to
`evals/results/latest.json` and `evals/results/latest.md`.

