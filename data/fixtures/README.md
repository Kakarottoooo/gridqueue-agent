# Synthetic fixture data

These CSV files are synthetic ERCOT GIS-like queue snapshots for deterministic local tests and demos.
They are not ERCOT records and must not be used as market facts.

The rows intentionally include messy names, changed queue IDs, status changes, fuel reclassification,
capacity changes, target-COD movement, and ambiguous project names so the entity-resolution and diff
logic can be tested offline.

