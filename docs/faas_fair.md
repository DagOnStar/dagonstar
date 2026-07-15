# FaaS and FAIR provenance

When FAIR recording is enabled, a FaaS task adds sanitized execution metadata to
its normal task activity: provider, function, invocation mode, timeout, request
identifier, attempt records, and only provider fields actually returned. Declared
materialized outputs are recorded with size, media type, and local SHA-256.

RO-Crate represents the task as a `CreateAction` whose `instrument` is a
provider-neutral `SoftwareApplication`/`Service` entity for the deployed function.
The activity remains separate from the deployment: the metadata substantiates an
invocation, not publication, validation, or infrastructure creation. PROV-like
output keeps the task as an activity and workflow edges as usage relationships.

Authorization headers, identity tokens, API/function keys, passwords, credentials,
and secret-bearing provider fields are never written. Environment-variable names
may appear in portable configuration, but values may not. Retry attempt records
contain normalized error categories rather than raw SDK exceptions.

