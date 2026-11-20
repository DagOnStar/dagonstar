# Lesson 28: Compose Meta-Workflows

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported with limitations
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- explain workflow-level composition, naming, and failure boundaries;
- call a workflow written for another engine as one `TaskType.META` task and
  exchange its data through `workflow://` references;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 27](lesson_27_make_a_workflow_fair_by_design.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

Acquisition, analysis, and reporting can remain separate workflows with explicit relationships. A community often already maintains the analysis as a Nextflow pipeline, a Snakefile, a Parsl program, or a StreamFlow/CWL workflow; rewriting it would discard validated work.

## Conceptual model

DAG_TPS coordinates workflows and transversal references. Workflow names become artifact identity, so collisions must be avoided.

A *meta-task* (`TaskType.META`) composes across engines. An adapter translates the engine-neutral task contract into the external engine's own command line and parameter files, so the engine is never modified. Inputs that are `workflow://` references are staged into `inputs/<name>/` and passed as absolute paths; declared outputs are collected from the engine's run directory into `outputs/<path>`, where downstream tasks reference them. The adapter interface is described in [Meta-tasks](../meta_tasks.md).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Identify each workflow namespace before following a transversal `workflow://` reference. Composition is intelligible only when producer identity, consumer identity, artifact path, and failure boundary remain unambiguous.

The second part of the script builds `observe -> external -> publish`, where `external` is a meta-task:

~~~python
DagonTask(TaskType.META, "external", engine="command", workflow=str(ENGINE),
          inputs={"text": "workflow:///observe/out/log.txt", "top": 1},
          outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}},
          engine_options={"command": [sys.executable, "{workflow}", "{parameters_file}"]})
~~~

`ENGINE` is `examples/meta/workflows/tiny_engine.py`, an engine-free stand-in driven by the generic `command` adapter, so the lesson runs without installing an engine. With an engine installed, only `engine`, `workflow`, and the options change: `engine="snakemake", workflow="examples/meta/workflows/Snakefile"` or `engine="nextflow", workflow="examples/meta/workflows/main.nf"`.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_28_meta_workflows.py
python -m unittest tests.test_workflow_core.WorkflowCoreTests.test_transversal_references_resolve_across_loaded_workflows -v
~~~

The script composes two workflows with `DAG_TPS`, resolves `workflow://Acquisition/collect/...` across them, runs both, and shows that an unresolvable cross-workflow reference fails when the optional DAGon service is not configured. It then runs the meta-task graph and checks the published word count and the SHA-256 evidence in `.dagon/meta_result.json`.

Optional, with engines installed (each absent engine is reported as skipped):

~~~bash
python examples/meta/meta_engines.py
~~~

## Expected result

The test proves local cross-workflow dependency discovery. The script prints that the meta-task exchanged data through `workflow://`: `external` depends on `observe`, `publish` depends on `external`, and `publish/top.tsv` contains `gust\t2`.

## Verify

~~~bash
python examples/tutorial/lesson_28_meta_workflows.py
python -m unittest tests.test_workflow_core.WorkflowCoreTests.test_transversal_references_resolve_across_loaded_workflows -v
python -m unittest tests.test_meta_task -v
~~~

It does not prove distributed recovery across independent services. The engine-free tests do not run real engines; `tests.test_meta_task.MetaLiveEngineTests` runs Snakemake, Parsl, Nextflow, StreamFlow, and cwltool only where they are installed.

## What DAGonStar did

DAGonStar resolved the cross-workflow producer and added the corresponding dependency in the loaded workflow set. The test establishes local discovery; it does not provide a distributed transaction across independent schedulers. For the meta-task, DAGonStar staged the input, ran the external program in `run/` without a shell, copied the declared output into `outputs/`, and recorded the digests of the workflow definition, input, and output.

## Controlled experiment

Rename a workflow but not its reference and predict discovery failure. Then change the meta-task's declared `source` to a file the engine does not write, predict the failure phase, and confirm that `publish` does not run (`task.failure_phase == "outputs"`).

## Common problems and diagnosis

Missing cross-workflow producers may attempt service lookup; validate names before execution. A meta-task whose engine is not installed fails with phase `engine` before anything runs; read `.dagon/engine_stderr.txt` for engine errors. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Composition helps ownership only with versioned identifiers and artifact contracts. A meta-task records the workflow-definition digest, not the containers or remote assets the engine may fetch; pin those in the external workflow (for example a Nextflow `revision` and container digests).

## Summary

Meta-workflows connect workflow units while preserving task causality; maturity is lower than core local execution. Meta-tasks extend composition across workflow engines through adapters without modifying the engines.

## Next lesson

Next, export the portable command graph to CWL. Return to the [syllabus](README.md) at any time.
