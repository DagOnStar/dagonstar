# Lesson 21: configure a cloud FaaS profile safely

Prerequisite: a function deployed independently of DAGonStar and permission to
invoke it. Install only the selected adapter: `dagonstar[faas-aws]`,
`dagonstar[faas-azure]`, or `dagonstar[faas-gcp]`.

```ini
[faas.aws.production]
region = eu-west-1
```

Select it with `provider="aws", profile="production"`. AWS uses the boto3 default
credential chain; Azure uses `DefaultAzureCredential`; Google uses Application
Default Credentials and an audience-aware identity token. Endpoint/profile data
may be configured, but credentials and function keys must not be stored in the
workflow, INI sample, source, or exports. HTTP authentication may name environment
variables with `header_env`/`token_env`; values remain runtime-only.

First construct the task and export JSON/CWL without invoking it. As an exercise,
review the provider options for secrets, then invoke a low-cost test function only
with operator approval. Deployment, billing, monitoring, and cleanup remain external
responsibilities. Missing SDKs produce an installation hint; missing identity or
endpoint configuration fails at the provider boundary without falling back to
anonymous cloud invocation.
