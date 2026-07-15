# Lesson 13: Run a Task on a Remote Host with SSH

> **Track:** Distributed infrastructure
> **Runtime:** SSH
> **Colab:** Not supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- describe remote identity, scratch, authentication, and safe verification;
- explain the underlying mechanism;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 12](lesson_12_run_a_task_in_docker.md), or equivalent concepts.
- [Lesson 00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) setup.
- SSH is optional for live integration; structural checks remain local.

## Scientific scenario

Remote execution places calculation on a machine with separate software and storage assumptions.

## Conceptual model

SSH adds host identity, user, port, authentication, host-key trust, remote scratch, and staging. It is transport, not scheduling.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read the authoritative example or structural check before running it. The canonical lifecycle is add_task(), optional explicit make_dependencies() and Validate_WF() for inspection, then run(). run() constructs dependencies automatically when needed.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_security_configuration tests.test_shell_commands -v
~~~

## Expected result

Tests verify safe local configuration and command construction.

## Verify

~~~bash
python -m py_compile dagon/remote.py dagon/communication/ssh.py
~~~

Compilation is structural evidence only; live verification needs an authorised host.

## What DAGonStar did

DAGonStar constructed or inspected the graph, applied the selected staging and execution policy, and exposed evidence through task state, working directories, or exports. Files and exit status are observed evidence; broader portability and scientific validity require the controls stated here.

## Controlled experiment

Compare default and non-default ports and predict generated metadata.

## Common problems and diagnosis

Do not disable host-key checks. Diagnose DNS, trust, permissions, software, and scratch separately. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Keep secrets outside source and exported provenance.

## Summary

Remote execution adds explicit trust, environment, and movement boundaries.

## Next lesson

Next, separate transport from scheduler semantics. Return to the [syllabus](README.md) at any time.
