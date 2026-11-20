# Lesson 26: Share and Release Volumes with Volume Tasks

> **Track:** Distributed infrastructure
> **Runtime:** Local emulation
> **Colab:** Supported
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- create an ad-hoc volume with a `TaskType.VOLUME` task and address it from sibling tasks as `workflow:///<task>/<volume>/...`;
- stage files and directories from other tasks' scratch directories into the volume with `stage_in`;
- destroy a volume with a second volume task and stage selected content out into its scratch directory;
- explain how reference counting releases a volume when no task refers to it any more;
- stream through a volume with `workflow:///producer/path?stream=<volume>` and recognise the plans DAGonStar refuses.

## Prerequisites

- [Lesson 25](lesson_25_plug_in_adhoc_file_systems_and_stream_between_tasks.md), or equivalent concepts.
- No storage software: DAGonFS and CAPIO run under portable emulation, where a local directory stands in for the volume.

## Scientific scenario

An ensemble of analysis tasks reads the same prepared input and writes partial results to a fast shared tier. Only the final table must survive; the tier should be freed as soon as no task needs it, without the author tracking which task finishes last.

## Conceptual model

A volume task is part of the graph. `DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz", stage_in={...})` creates volume `xyz` when it runs; `stage_in` maps paths inside the volume to `workflow://` references, so the task depends on their producers. Sibling tasks read and write `workflow:///Abc/xyz/...`. The reference creates the edge to `Abc` exactly as a scratch reference does, but DAGonStar rewrites it to the volume's own path instead of copying, so writes become visible to every later user.

`DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz", stage_out={...})` waits for every task that uses the volume, copies the listed entries into its own scratch directory, and releases the volume; later tasks read them as `workflow:///Del/...`. A destroy task is optional: the volume task counts the references to it, and once the last user has finished the volume is released, with the same rule that collects scratch directories. A consumer of `workflow:///Emit/numbers?stream=xyz` streams from `Emit` through the volume when its adapter supports streaming (DAGonFS, CAPIO, and other built-ins). See [volume tasks](../volume_tasks.md) and the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_26_volume_tasks.py`](../../examples/tutorial/lesson_26_volume_tasks.py) and the longer [`examples/adhoc/volume_task.py`](../../examples/adhoc/volume_task.py), which runs the same patterns on a real local adapter and accepts `--emulate PROVIDER` or `--live PROVIDER`.

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_26_volume_tasks.py
python examples/adhoc/volume_task.py
python examples/adhoc/volume_task.py --emulate capio
~~~

## Expected result

The script prints that `Del` waited for `Abc, Emit, Square, Sum`, that `Report` read the staged-out `square.txt` (`1 4 9 16`), and that `Sum` received the total 10 through the stream on `xyz`. The second workflow prints `released by reference counting: no task refers to it`. The third is refused before any task runs: `task Late uses volume v but runs after Drop, which destroys it`.

## Verify

~~~bash
python examples/tutorial/lesson_26_volume_tasks.py
python -m unittest tests.test_volume_task -v
~~~

Emulation verifies planning, references, staging, release, and the stream protocol, not the speed, sharing, or durability of DAGonFS or CAPIO. `examples/adhoc/volume_task.py` without options executes the same lifecycle on a real local-directory adapter.

## What DAGonStar did

When dependencies were made, DAGonStar bound every user of `xyz` to its file system, gave `Del` an edge from every user, and checked that no user ran after it. At run time `Abc` started the volume and staged `Prep`'s data in; users' references resolved to volume paths; `Del` staged `out/` out and released the volume. In the second workflow the decrement after `Read` brought the count to zero and released `tmp`.

## Controlled experiment

Predict whether `Square` can run before `Prep`; it cannot, because it depends on `Abc`, which depends on `Prep`. Remove the `Del` task and predict when `xyz` is released and what `Report` must read instead. Finally, add a task reading `workflow:///Abc/xyz/in/n.txt` after `Report` and predict the error.

## Common problems and diagnosis

`does not name the volume of a create volume task` means the destroy reference has a wrong task or volume name. Credential-like keys in `options` are rejected. BeeOND volumes exist only inside a Slurm allocation and are refused. A stream query on a plain volume reference is refused with a hint to use `?stream=<volume>`. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Treat a volume as transient: anything that must outlive the run is staged out by a destroy task and recorded like any scratch output. FAIR records mark edges served by a volume, and a volume task's checkpoint is reused only when every user also completed, because a volume does not survive the process.

## Summary

Volume tasks make shared ad-hoc storage an explicit part of the graph: one task creates it, siblings use it through `workflow://`, and either a destroy task or reference counting releases it.

## Next lesson

Next, move input staging out of the allocation with scheduler-aware pre-staging. Return to the [syllabus](README.md) at any time.
