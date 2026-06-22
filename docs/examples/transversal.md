# Transversal and Meta-Workflow Examples

Source directories:

- [`examples/transversal`](../../examples/transversal)
- [`examples/transversal_old_scripts`](../../examples/transversal_old_scripts)

## Current transversal files

- `transversal-demo.py`
- `transversal-cycle.py`
- `WF1-transversal-async.py`
- `WF2-transversal-async.py`
- `wf1-transversal-demo.json`
- `wf2-transversal-demo.json`
- `figs/`

## Historical scripts

`examples/transversal_old_scripts` contains older research scripts retained for
context and reproducibility. They are not the recommended starting point for new
users.

## Purpose

Transversal examples demonstrate dependencies across workflow boundaries. A task
in one workflow can reference a task in another workflow:

```text
workflow://OtherWorkflow/TaskName/path/to/file
```

This is useful when independent pipelines exchange scientific products.

## Concepts exercised

- `DAG_TPS`
- multiple `Workflow` instances
- cross-workflow `workflow://` references
- service-backed asynchronous transversal workflows
- cycle detection across workflows

## Verification

Local meta-workflow behavior is more legacy-sensitive than single-workflow
behavior. Start by reading:

```bash
cd examples/transversal
python transversal-demo.py
```

For asynchronous examples, inspect the JSON files and service assumptions before
execution.

## Scientific interpretation

Transversal workflows model scientific systems such as:

- observations workflow feeding model workflow;
- forecast workflow feeding publication workflow;
- multi-region workflows sharing boundary conditions;
- ensemble members feeding post-processing.

For production use, preserve both the individual workflow definitions and the
meta-workflow dependency graph.
