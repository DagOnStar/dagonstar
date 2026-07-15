# FaaS tasks

`TaskType.FAAS` invokes an already-deployed function as a workflow node. It does
not build, deploy, publish, or delete cloud infrastructure. Unlike `WEB`, the
task records function identity, invocation mode, retries, provider request IDs,
declared outputs, and provider-neutral execution provenance.

```python
invoke = DagonTask(
    TaskType.FAAS, "classify", provider="mock", function="classifier",
    inputs={"document": "workflow:///prepare/outputs/input.json", "threshold": 0.8},
    outputs={"classification": "classification.json"},
    retry={"max_attempts": 3, "backoff": "exponential"},
)
```

`provider` and `function` are required. `invocation` is `sync` (the default) or
`async`; an adapter must report support for the selected mode. `timeout` is a
positive number of seconds. Retryable categories default to throttling,
provider unavailability, and transport failures. Retries retain one deterministic
idempotency key and record distinct attempt numbers.

Inputs are JSON values. A `workflow://` reference may occur in nested mappings
or lists; it infers a dependency, copies the producer file into `inputs/`, and
becomes an artifact descriptor containing a task-relative path, size, media type,
and SHA-256. The current automatic transport is `local-file` for mock/local HTTP
execution. Remote providers must receive inline data or an externally accessible
object reference; automatic object-store upload is not implemented and inaccessible
local paths must not be sent to remote functions.

Declared output paths are relative to `outputs/`. Direct JSON output values are
written atomically; `{ "path": "..." }` responses copy a task-local file. Required
missing outputs and checksum mismatches fail the task. Runtime records are written
to `.dagon/faas_spec.json`, `faas_request.json`, `faas_response.json`, and
`faas_provider_metadata.json` with credential values excluded.

Provider options may reference secrets only through names ending in `_env`.
Output traversal is rejected, TLS remains enabled, and portable JSON retains
logical references rather than resolved host paths. See [providers](faas_providers.md),
[FAIR mapping](faas_fair.md), [CWL export](faas_cwl.md), and the
[local example](../examples/faas/README.md).

