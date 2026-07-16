# IoT tasks

`TaskType.IOT` models bounded observation, desired-state configuration, physical actuation, and portable device/edge computation. It is not an alias for HTTP, SSH, or shell execution.

Create tasks with `DagonTask(TaskType.IOT, name, operation=..., provider="mock", completion=...)`. Observation completion must be bounded. Compute requires an artifact, action, or provider executable. Non-idempotent actuation defaults to one attempt; an unknown acknowledgement raises `IoTUnknownOutcomeError` and is not replayed.

Structured fields may contain nested `workflow://` references. `Workflow.make_dependencies()` discovers them; execution stages files beneath `.dagon/inputs` and resolves a deep copy, preserving the logical strings in JSON. Outputs are scratch-relative and traversal-safe. Credential values must never be supplied in specifications; use `credential_ref`. DAGonStar is not a physical safety interlock.

See [providers](iot_providers.md), [checkpointing](iot_checkpointing.md), [CWL](iot_cwl.md), and [compute continuum](compute_continuum.md).
