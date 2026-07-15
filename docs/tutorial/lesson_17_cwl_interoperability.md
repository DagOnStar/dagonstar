# Lesson 17: Interoperate with Common Workflow Language

## Objective

Export a DAGonStar command graph as CWL v1.2, validate the handoff, and
understand which DAGonStar semantics are portable.

## Concept

CWL connects process outputs to downstream process inputs. DAGonStar's exporter
represents every task as an embedded `CommandLineTool` and uses boolean
completion values for control dependencies. This preserves the DAG without
claiming that undeclared scientific files are CWL outputs.

The interoperability contract is mandatory for command-graph export: changes
to workflow/task/dependency behavior must keep `saveAsCWL()` and its tests,
example, and documentation consistent. This does not imply that a generic CWL
runner implements DAGonStar's SSH, Slurm, cloud, checkpoint, or staging layers.

## Code

The runnable source is
[`examples/cwl/export_workflow.py`](../../examples/cwl/export_workflow.py). Its
essential handoff is:

```python
workflow = build_workflow()
workflow.saveAsCWL("interoperable-workflow.cwl")
```

Generate the document:

```bash
python3 examples/cwl/export_workflow.py --output /tmp/interoperable-workflow.cwl
```

## Expected behavior

The CWL workflow has three steps. `collect_observations` and
`prepare_parameters` are independent. `run_simulation` has two boolean inputs
whose sources are the completion outputs of those steps. The workflow exposes
`run_simulation_completed` as its terminal output.

## Verification

The local, dependency-free check is:

```bash
python3 -m unittest tests.test_cwl_example -v
```

For standards-level validation, install the optional reference runner and use:

```bash
python3 -m pip install cwltool
cwltool --validate /tmp/interoperable-workflow.cwl
cwltool /tmp/interoperable-workflow.cwl
```

## Interoperability boundary

Use command-only tasks, or explicitly adapt files as CWL `File`/`Directory`
parameters, when the exported document must run outside DAGonStar. A
`workflow://` reference still contributes an edge during export, but its text
is retained because generic CWL runners do not implement DAGonStar staging.
Remote and scheduler-specific tasks similarly become shell commands plus graph
structure; their original executor is not recreated.

## Scientific practice note

Treat the generated CWL as a reviewable research artifact. Record the
DAGonStar version, validate with the target runner, declare data interfaces
instead of relying on implicit paths, and inspect commands for secrets before
sharing the document.
