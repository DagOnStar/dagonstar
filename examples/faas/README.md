# FaaS examples

These examples invoke already-deployed functions; they do not deploy infrastructure.
Both included programs are local, deterministic, and credential-free.

Run `python3 examples/faas/mock_sync.py` for a Batch → mock FaaS → Batch workflow.
The mock response becomes `outputs/result.json`; staged input descriptors and
sanitized invocation records are under the FaaS task's `.dagon/` directory.

Run `python3 examples/faas/export.py` to write `faas-workflow.json` and
`faas-workflow.cwl`. Cloud adapters require their optional extra, a deployed
function, and provider-standard credentials. Never place credentials, signed URLs,
or function keys in an example or task specification. Cloud invocation may incur
cost; resource deployment and cleanup are the operator's responsibility.

Run `python3 examples/faas/local_http.py` for a standard-library HTTP fixture.
The script starts a loopback function, invokes it through the HTTP adapter,
extracts its request ID, materializes the JSON result, and shuts the server down.
