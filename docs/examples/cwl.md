# CWL interoperability example

Source: [`examples/cwl/`](../../examples/cwl/README.md)

## Purpose

The example demonstrates a reproducible handoff from a Python-defined
DAGonStar DAG to a self-contained Common Workflow Language v1.2 document. It
contains two independent preparation tasks followed by one simulation task.

## DAGonStar mechanisms

- local `Batch` tasks;
- explicit many-to-one dependencies;
- `Workflow.saveAsCWL(filename)`;
- portable CWL identifiers derived from DAGonStar task names;
- terminal completion output.

## Run and verify

Generate a new document without changing the repository copy:

```bash
python3 examples/cwl/export_workflow.py --output /tmp/interoperable-workflow.cwl
python3 -m unittest tests.test_cwl_example -v
```

The unit test checks that the generated document matches the committed example
and that both preparation outputs feed the simulation step. When `cwltool` is
available, the test also asks the reference runner to validate the document.

No credentials, network service, scheduler, or container runtime is required
to generate the export. Running it requires a CWL v1.2 runner and `/bin/sh`.

Agentic tasks export to an executable `dagon-agent-runner` step with a
workflow-level `dagon_config: File` input; see the agentic section of the
[CWL export guide](../cwl_export.md) and `examples/agentic/cwl_local.py`.

Meta-tasks export to an executable `dagon-meta-runner` step whose `workflow://`
inputs are bound to producer `File` or `Directory` outputs; see the meta-task
section of the [CWL export guide](../cwl_export.md) and `examples/cwl/export_meta_workflow.py`
(`--run` executes it with `cwltool` when `dagon-meta-runner` is installed).

## Volume tasks

`export_volume_workflow.py` exports
`prepare → scratch (create volume) → {left, right} → drop (destroy) → check`.
CWL v1.2 has no shared mutable storage, so the create step materializes the
volume as a `Directory` output, consumers read it as an input, the destroy
step copies its `stage_out` entries, and both carry a `dagon:Volume` hint.
`--portable` (default) is directly runnable; `--standard` exports the backend
form; `--run` executes the portable document with `cwltool --no-container`:

```bash
python3 examples/cwl/export_volume_workflow.py --output /tmp/volume.cwl --run
cwltool --validate /tmp/volume.cwl
```

Data that sibling steps write into the volume during a DAGonStar run is not
exchanged through CWL. See [Volume tasks](../cwl_export.md#volume-tasks).
