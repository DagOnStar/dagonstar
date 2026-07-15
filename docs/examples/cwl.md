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
