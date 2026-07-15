# Lesson 18: run a local mock FaaS task

Prerequisite: an editable DAGonStar installation. Run
`python3 examples/faas/mock_sync.py`. The example constructs a Batch → FaaS →
Batch graph with `provider="mock"`; no account, network, or credentials are used.

Inspect the FaaS scratch directory. `inputs/` contains staged producer data,
`outputs/result.json` is the materialized function result, and `.dagon/faas_*.json`
contains the portable specification, request envelope, normalized response, and
sanitized provider metadata. Change the mock response value and rerun as an
exercise. Remove the generated scratch directories when finished. A missing
required output reports `output_missing`; an invalid relative path is rejected
before execution.
