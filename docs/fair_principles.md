# DAGonStar: FAIR by design

DAGonStar implements FAIR support as an opt-in, native workflow capability.
Calling `Workflow.enable_fair(FairProfile(...))` attaches a `FairRecorder` to
the same lifecycle events that drive workflow execution. It does not alter task
scheduling, staging, commands, or behavior for workflows that do not opt in.

The implementation is deliberately local and dependency-free: it records
machine-readable metadata next to a run rather than copying data or publishing
it to a remote repository. This page describes the behavior implemented in the
current codebase.

## Model and opt-in API

The public declaration models live in `dagon.fair`: `FairProfile` defines the
workflow title, description, creators, license, keywords, access policy,
strictness, output directory, and environment allowlist. `Agent` can include
ORCID, ROR, email, and affiliation; `AccessPolicy` records metadata/data access;
and `Artifact` describes intentional input/output paths and optional type,
license, identifier, and semantic metadata.

Tasks can declare intent without changing execution:

```python
task.declare_inputs(Artifact("workflow:///prepare/data.nc")) \
    .declare_outputs(Artifact("result.nc", media_type="application/x-netcdf")) \
    .annotate(description="Run the model", parameters={"steps": 100})
```

These declarations remain inert until the owning workflow enables FAIR mode.

## Lifecycle capture

At workflow start, the recorder creates a UUID-based run identifier and output
directory. It records workflow/profile metadata, DAGonStar version when
discoverable, Python/platform summaries, configured data/stager movers, and an
allowlisted subset of environment variables.

Dependency construction fires `on_dependencies_made`. The recorder records task
edges and recognizes same-workflow references such as
`workflow:///prepare/data.nc` as a producer/consumer relationship. The existing
parser is unchanged: its documented whitespace/path limitation still applies.

Task events capture type, original command and SHA-256 command hash, declared
artifacts, annotations, predecessor/successor names, wait state, working
directory, backend information, staging boundaries, timestamps, and final
status. A task reused from a successful checkpoint is marked `checkpoint_reused`.
Existing declared local outputs receive size and SHA-256 fixity; remote outputs
are represented by their declaration and are not fetched or hashed.

## FAIR interpretation

| Principle | Native DAGonStar behavior |
| --- | --- |
| Findable | Workflow, run, task, and output-artifact URNs are generated; title, description, creators, keywords, and identifiers are structured metadata. |
| Accessible | Metadata is local UTF-8 JSON/JSON-LD, Markdown, and HTML. `AccessPolicy` states the metadata/data access assumption without copying restricted data. |
| Interoperable | The recorder emits RO-Crate JSON-LD, a PROV-like JSON graph, DataCite JSON, and CodeMeta JSON-LD. `workflow://` edges become provenance relationships. |
| Reusable | Profile/artifact licenses, task context, checkpoint reuse, declared outputs, local checksums, file sizes, and runtime summaries are retained. |

## Exports and validation

The default output location is `<scratch>/.dagon/fair/<workflow-name>/<run-uuid>/`;
`FairProfile.output_dir` overrides it. The recorder writes `run.json`,
`ro-crate-metadata.json`, `prov.json`, `datacite.json`, `codemeta.json`,
`checksums.sha256`, `fairness-report.json`, `report.md`, and `report.html`.

Strict mode fails early only when the profile lacks a title, description,
creators, or license. Post-run issues, including missing declared outputs, are
errors in strict mode and warnings otherwise; they do not hide task failures.

## Safety and current boundary

Environment capture is opt-in via `FairProfile.capture_environment`. Even
allowlisted names are omitted when they contain default redaction markers such
as `TOKEN`, `SECRET`, `PASSWORD`, `PRIVATE_KEY`, `AWS_`, `GCP_`, or `AZURE_`.
The recorder does not export raw `dagon.ini` content, credentials, keys, or
tokens.

FaaS activities add only substantiated, sanitized provider/function identity,
request identifiers, attempts, and materialized-output fixity. RO-Crate links
the invocation action to a deployed-function service entity without claiming
that DAGonStar deployed or published it. Provider credentials, authorization
headers, signed query values, and raw SDK objects remain excluded.

This is local export only. It does not yet validate a full Workflow Run RO-Crate
profile, emit PROV-O Turtle, package/copy data, publish to repositories, provide
a FAIR CLI, or calculate remote/container checksums.
