# Lesson 25: Plug in Ad-Hoc File Systems and Stream between Tasks

> **Track:** Distributed infrastructure
> **Runtime:** Local (out-of-package adapter); built-in providers under portable emulation
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- add a storage system to DAGonStar by writing one `AdHocFileSystem` adapter and registering it, without modifying DAGonStar or the storage software;
- explain why built-in provider names are protected and how installed packages contribute adapters through the `dagon.adhoc_providers` entry-point group;
- distinguish workflow-scope, default, and task-scope resources, and name a task-scope resource with `export=`;
- declare a streaming edge with `workflow:///producer/path?stream` and state which guarantees the stream protocol gives the consumer;
- read the access mode (`posix`, `preload`, `client`, `object`) of the built-in providers and say what it implies for the commands that use them.

## Prerequisites

- [Lesson 24](lesson_24_use_beeond_job_local_storage.md), or equivalent concepts.
- No storage software: the lesson's adapter serves an ordinary local directory, and the built-in providers are only inspected under portable emulation.

## Scientific scenario

A research group runs its pipelines on a site whose fast scratch tier is a storage system DAGonStar does not know. Rewriting the workflow engine for each site is not an option, and a long simulation should hand partial results to its analysis before it finishes.

## Conceptual model

Every ad-hoc file system is a subclass of `dagon.adhoc.AdHocFileSystem` with a provider name, an access mode, a `task_path`, and `start`, `is_ready`, and `stop` methods. `register_provider(name, cls)` (or the `dagon.adhoc_providers` entry-point group of an installed package) makes it available to `workflow.create_adhoc_filesystem(name, ...)`. Built-in names (DAGonFS, BeeOND, Hercules, CAPIO, DynoStore) cannot be silently replaced.

A workflow-scope resource starts before the first task and stops after the last; `default=True` binds it to every task. `task.create_adhoc_filesystem(...)` creates a task-scope resource that starts and stops around that single task. Each bound resource is exported as `DAGON_ADHOC_<NAME>_PATH`, or under a variable chosen with `export=` (credential-like names are refused).

An adapter that sets `supports_streaming` can carry streams. A consumer that reads `workflow:///producer/items?stream` keeps an ordinary `workflow://` dependency, but starts while the producer runs and receives each item once its marker exists; the marker records size and SHA-256, and the producer's exit status ends the stream. See [ad-hoc file systems](../adhoc_filesystems.md) and [streaming between tasks](../adhoc_filesystems.md#streaming-between-tasks). New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_25_adhoc_filesystems.py`](../../examples/tutorial/lesson_25_adhoc_filesystems.py). It defines `ScratchDirectory`, registers it, binds a default workflow-scope volume and a task-scope volume exported as `$MYVOLUME`, streams four items from `produce` to `consume`, and finally reads the access modes of four built-in providers under emulation. The longer [`custom_adapter.py`](../../examples/adhoc/custom_adapter.py), [`streaming.py`](../../examples/adhoc/streaming.py), and [`task_scope_volume.py`](../../examples/adhoc/task_scope_volume.py) show the same mechanisms at larger scale.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_25_adhoc_filesystems.py
python examples/adhoc/custom_adapter.py
python examples/adhoc/streaming.py
python examples/adhoc/streaming.py --emulate dagonfs
~~~

## Expected result

The script prints that `shared` and `private` were both bound to `read`, that `consume` received four verified items through `?stream` (total 10), that registering `dagonfs` again was refused, and the access modes `capio=preload, dagonfs=posix, dynostore=object, hercules=preload`. It also asserts that the task-scope directory was removed after its task.

## Verify

~~~bash
python examples/tutorial/lesson_25_adhoc_filesystems.py
python -m unittest tests.test_adhoc_filesystems tests.test_adhoc_streaming -v
~~~

The adapter and the stream run for real on a local directory. The built-in providers are only constructed under portable emulation, which is not evidence that DAGonFS, CAPIO, Hercules, or DynoStore ran; live runs are recorded in `docs/performance/`.

## What DAGonStar did

DAGonStar looked the provider up in its registry, started each workflow-scope resource before the run and the task-scope resource around `read`, exported the paths into the task environments, planned the `?stream` edge so that `consume` started with `produce`, verified every item against its marker, and stopped every resource it had started.

## Controlled experiment

Predict what `$DAGON_ADHOC_NAMES` contains in `read`; the script asserts `private,shared`. Remove `default=True` and predict which command fails first. Then remove `?stream` from `consume` and predict the change: the dependency remains, but `consume` waits for `produce` to finish and reads staged files instead of the stream (the script's `stream_prevs` assertion fails).

## Common problems and diagnosis

A provider name that is already registered raises `ValueError`; use a new name or `replace=True` for your own class. `export` values that look like credentials (for example containing `TOKEN` or `PRIVATE`) are refused. A stream reference on a resource whose adapter does not support streaming is refused at planning time. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record the provider, access mode, and scope that a run used (the task's execution metadata carries them), and state whether the provider ran live or under emulation. A streamed result is accepted item by item only after verification, and a stream that ended with a failure fails its consumer, so partial data is never mistaken for a complete result.

## Summary

New storage systems join DAGonStar through adapters, not code changes. Scope decides a resource's lifetime, and `?stream` turns one data dependency into a verified, overlapping one without leaving the `workflow://` schema.

## Next lesson

Next, let a task own a volume: volume tasks create an ad-hoc volume, share it through `workflow://`, and release it. Return to the [syllabus](README.md) at any time.
