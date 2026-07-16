# Lesson 15: Make a Workflow FAIR by Design

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- record supported metadata and distinguish local export from publication;
- relate each observed result to the workflow mechanism that produced it;
- verify observed behavior and state what the evidence does not prove.

## Prerequisites

- [Lesson 14](lesson_14_submit_a_task_through_slurm.md), or equivalent concepts.
- No external service unless stated below.

## Scientific scenario

The observation workflow gains creator, licence, descriptions, checksums, and provenance records.

## Conceptual model

The opt-in FAIR recorder captures locally substantiated workflow and artifact metadata. It does not deposit artifacts, grant access, or guarantee preservation.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read one FAIR test that declares artifacts and one that sanitises metadata. Map each exported statement to a locally available source: workflow declaration, execution event, file property, checksum, licence, or creator profile.

## Run the example

From the repository root:

~~~bash
python -m unittest tests.test_fair -v
~~~

## Expected result

Tests verify profiles, records, sanitisation, and local exports.

## Verify

~~~bash
python -m unittest tests.test_fair -v
~~~

They do not publish to a repository.

## What DAGonStar did

The opt-in recorder assembled locally substantiated metadata and provenance and emitted local standard-form exports. It did not upload data, mint a persistent identifier, negotiate access, or certify repository conformance.

## Controlled experiment

Remove a required profile field temporarily, predict strict validation, then restore it.

## Common problems and diagnosis

Metadata validation and task execution failures are separate diagnoses. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

FAIRness is stewardship practice; local metadata alone is not global findability or accessibility.

## Summary

FAIR recording culminates declared artifacts, checksums, licences, and honest provenance.

## Next lesson

Next, compose acquisition, analysis, and reporting workflows. Return to the [syllabus](README.md) at any time.
