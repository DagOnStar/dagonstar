# Lesson 31: Run Other Engines' Workflows with Meta-Tasks

> **Track:** FAIR composition and interoperability
> **Runtime:** Local; real engines optional
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- support a new workflow engine by writing one `MetaEngineAdapter` and registering it, without modifying the engine or DAGonStar;
- pass data into and out of an external workflow only through `workflow://` references and declared outputs;
- explain which identities a meta-task checkpoint re-verifies before it is reused;
- read a failed meta-task's `failure_phase` (`validation`, `engine`, `staging`, `execution`, `outputs`);
- distinguish a portable-emulation run (mock engine, placeholder outputs) from a real engine run.

## Prerequisites

- [Lesson 30](lesson_30_compose_meta_workflows.md), or equivalent concepts.
- No external engine: the lesson's adapter runs a small Python file; Nextflow appears only under emulation.

## Scientific scenario

A collaborator's analysis is published as a workflow for another engine. Rewriting it would introduce errors and lose its provenance; the DAGonStar workflow should call it unchanged, feed it data, and use its results.

## Conceptual model

A `TaskType.META` task names an `engine`, a `workflow` (file or engine-specific identifier), `inputs`, and `outputs`. An adapter's `prepare` writes the engine's own parameter files below `.dagon/` and returns an argument vector; DAGonStar runs it without a shell, then collects only the declared outputs, refusing any that resolve outside the task's scratch directory. `register_adapter(name, cls)` or the `dagon.meta_adapters` entry-point group adds an engine; built-in names (`mock`, `command`, `nextflow`, `snakemake`, `parsl`, `streamflow`, `cwl`) are protected.

The checkpoint records digests of the specification, the workflow definition, the inputs, and the outputs; it is reused only when all of them are re-verified. Engine options and environment names that look like credentials are rejected. Under portable emulation, every engine is replaced by the deterministic `mock` adapter. See [meta-tasks](../meta_tasks.md) and the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_31_meta_tasks.py`](../../examples/tutorial/lesson_31_meta_tasks.py), then [`examples/meta/meta_workflow_local.py`](../../examples/meta/meta_workflow_local.py) and, when engines are installed, [`examples/meta/meta_engines.py`](../../examples/meta/meta_engines.py).

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_31_meta_tasks.py
python examples/meta/meta_workflow_local.py
python examples/meta/meta_engines.py
~~~

## Expected result

The script prints `observe -> tally (lesson31-tally adapter) -> report: 3 words, 2 unique`, then that the checkpoint was reused while nothing changed and not after the workflow definition changed. A Snakemake task with a missing executable fails with `failure_phase=engine` (its traceback is logged), a credential-like engine option is rejected at construction, replacing `nextflow` is refused, and the emulated Nextflow task writes a placeholder output.

## Verify

~~~bash
python examples/tutorial/lesson_31_meta_tasks.py
python -m unittest tests.test_meta_task -v
~~~

Engine-free tests always run; live-engine tests skip when an engine is absent. A placeholder from the mock adapter is never evidence that the named engine ran.

## What DAGonStar did

DAGonStar staged `observe`'s file into the meta-task, let the adapter write `tally-parameters.json`, ran the engine command without a shell, collected `tally.json` into `outputs/`, and served it to `report` as `workflow:///tally/outputs/tally.json`. On the second run it recomputed the recorded digests and reused the checkpoint; after the definition changed the digest differed and the engine ran again.

## Controlled experiment

Predict whether changing the text that `observe` writes invalidates the checkpoint; it does, because the input digest changes. Make `ENGINE_SCRIPT` write `tally.txt` instead of `tally.json` and predict the failure phase (`outputs`). Then run `meta_engines.py --engine snakemake` with and without Snakemake installed and compare the evidence.

## Common problems and diagnosis

`MetaEngineUnavailableError` means the executable was not found; set `engine_options["executable"]` or install the engine. `unknown ... engine option(s)` lists options the adapter does not understand. Outputs refused as outside the scratch directory usually come from symbolic links the engine created. Read `.dagon/engine_stderr.txt` for engine failures. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Pin what the meta-task cannot see: its digest covers the workflow definition, not the containers or remote assets the engine fetches. Record engine versions only when read locally, and label emulated runs as such.

## Summary

Meta-tasks reuse workflows from other engines as single, verified DAGonStar tasks: adapters isolate engine specifics, `workflow://` carries the data, and checkpoints are reused only after their identity is re-verified.

## Next lesson

Next, export the portable command graph to CWL. Return to the [syllabus](README.md) at any time.
