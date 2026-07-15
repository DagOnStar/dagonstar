# Lesson 00: Set Up DAGonStar and Understand the Learning Model

> **Track:** Core
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 20 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- establish a reproducible environment and distinguish local lessons from optional integrations;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- Python 3 and a command shell.
- A repository checkout or package installation.
- No external service unless stated below.

## Scientific scenario

A reproducible installation is part of the experimental method. This orientation establishes one repository checkout and one environment.

## Conceptual model

An editable installation exposes the checked-out source to Python. Repository-root-relative commands assume that the directory containing README.md is current.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python -m pip install -e .
python -c "import dagon; print(dagon.Workflow.__name__)"
~~~

## Expected result

The import prints Workflow without contacting an external service.

## Verify

~~~bash
python -m unittest tests.test_workflow_core.WorkflowCoreTests.test_workflow_uses_safe_defaults_for_optional_sections -v
~~~

This confirms minimal local construction, not Docker, SSH, Slurm, or cloud operation.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Change the virtual-environment location, predict whether repository-relative commands change, then repeat the import check.

## Common problems and diagnosis

A missing import normally means the environment was not activated. Inspect 'python -m pip show dagonstar' and 'pwd'. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record Python and dependency versions. Never copy credentials into dagon.ini.sample.

## Summary

A controlled environment and explicit repository root provide the evidence base for later lessons.

## Next lesson

Next, create and execute one local task. Return to the [syllabus](README.md) at any time.
