# FaaS providers

The portable task owns lifecycle, dependencies, retry, output validation, and
provenance. Adapters own endpoint resolution, standard credential chains,
invocation, provider error normalization, request identifiers, capabilities,
and metadata sanitization.

- `mock` is deterministic, in-process, credential-free, and intended for CI,
  examples, and local development.
- `http` posts the DAGonStar JSON envelope. Headers are populated from the
  environment using `header_env`; literal secrets are rejected.
- `knative` uses the HTTP adapter and can emit CloudEvents binary headers with
  `provider_options={"knative": {"endpoint": ..., "cloudevents": True}}`.
- `aws` invokes Lambda through boto3's default credential chain. Install
  `dagonstar[faas-aws]`; `region`, `profile`, and `qualifier` are optional.
- `azure` invokes an HTTP-triggered function with `DefaultAzureCredential`, or a
  token named by `token_env`. Install `dagonstar[faas-azure]`.
- `gcp` invokes a Cloud Run function with an audience-aware identity token from
  Application Default Credentials, or `token_env`. Install `dagonstar[faas-gcp]`.

Named profiles use `[faas.<provider>.<profile>]`; explicit `provider_options`
override profile values. Profiles contain endpoints, regions, audiences, and
environment-variable names—not credential values. Provider deployments and IAM
remain external prerequisites. Object-store upload/download adapters are not yet
implemented; use direct JSON or an already accessible, policy-approved object URI.

New adapters extend `FaaSProvider`, report `ProviderCapabilities`, implement
`invoke`, sanitize metadata, and register through `register_provider`. Optional
SDKs must be imported only at invocation time.

