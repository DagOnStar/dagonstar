# Lesson 29: Export and Validate Common Workflow Language

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- export CWL v1.2 and explain portability boundaries;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 28](lesson_28_compose_meta_workflows.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

The capstone exports the command-oriented graph for other workflow tooling.

## Conceptual model

saveAsCWL() emits deterministic CWL v1.2 JSON for portable commands, dependencies, and interfaces. Backend staging and credentials may lack exact equivalents.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Inspect `examples/cwl/export_workflow.py` and predict how tasks, edges, commands, inputs, and outputs appear in the exported document. Generate into a temporary path so the checked-in reference remains an independent comparison.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_29_cwl_export.py
python -m unittest tests.test_cwl_example -v
python examples/agentic/cwl_local.py
python examples/cwl/export_streaming_workflow.py --output /tmp/streaming.cwl
python examples/cwl/export_meta_workflow.py
~~~

The Lesson 29 script exports the same graph twice, checks byte-identical output, a file edge and an ordering-only edge, and the absence of scratch paths, and runs `cwltool --validate` when it is installed. `cwl_local.py` exports an agentic step as a `dagon-agent-runner` invocation that takes `dagon_config` as a workflow input, and executes the graph with `cwltool --no-container` when both tools are present. `export_streaming_workflow.py` exports a `workflow:///produce/items?stream` edge: CWL has no concurrent steps, so the stream becomes a `Directory` passed from producer to consumer, and a `dagon:Stream` hint keeps the intent. `export_meta_workflow.py` exports a meta-task as a `dagon-meta-runner` step whose `workflow://` input is bound to the producer's `File` output and whose `dagon:MetaTask` hint records the engine and the workflow-definition SHA-256; the external engine itself stays outside the portable contract.

## Expected result

The test regenerates and checks deterministic CWL structure.

## Verify

~~~bash
python examples/tutorial/lesson_29_cwl_export.py
python -m unittest tests.test_cwl_example tests.test_agentic_cwl -v
python -m unittest tests.test_adhoc_streaming -k cwl -v
~~~

Schema validation does not prove identical runtime behavior on every runner.

## What DAGonStar did

`saveAsCWL()` serialised the supported portable command graph deterministically as CWL v1.2 JSON. DAGonStar-specific staging, remote execution policy, and credentials remain outside that representation and must not be inferred from it.

## Controlled experiment

Change one command, predict the changed CWL field, and compare exports.

## Common problems and diagnosis

JSON parsing is weaker evidence than an available CWL validator. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Portable descriptions need explicit interfaces and documented semantic boundaries.

## Summary

CWL export describes the portable graph; it is not execution.

## Next lesson

Next, [combine edge, serverless, native, and agentic tasks across the compute continuum](lesson_30_compute_continuum_operations.md). Return to the [syllabus](README.md) at any time.
