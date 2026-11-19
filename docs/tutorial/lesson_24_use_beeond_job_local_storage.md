# Lesson 24: Use BeeOND Job-Local Storage

> **Track:** Distributed infrastructure
> **Runtime:** Local emulation
> **Colab:** Supported
> **Estimated effort:** approximately 35 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- distinguish task-scope and workflow-scope BeeOND volumes;
- explain persistence of job-local data before teardown;
- validate BeeOND options and recognise rejected configurations;
- bind DAGonFS, BeeOND, Hercules, CAPIO, or DynoStore to tasks through the common ad-hoc interface and read its access mode;
- choose workflow-scope, default, or task-scope ad-hoc volumes, combine several of them, and add a new system by writing an adapter;
- declare a streaming edge with `workflow:///producer/path?stream` and verify that only that edge overlaps.

## Prerequisites

- [Lesson 23](lesson_23_submit_a_task_through_slurm.md), or equivalent concepts.
- No BeeOND site; portable emulation maps `$DAGON_BEEOND` to a persistent directory.

## Scientific scenario

A multi-node simulation writes intermediate files to a fast, job-private file system that disappears when the job ends. Later tasks still need some of those files.

## Conceptual model

A Slurm task with `beeond="task"` receives the mount in `$DAGON_BEEOND`; its launcher copies the volume to `<working_dir>/beeond` before the job ends. With `create_beeond_volume(name)` and `beeond="workflow:<name>"`, a holder job keeps one volume for several tasks. `BeeONDConfig` validates options. See the [BeeOND guide](../beeond.md).

BeeOND is one of five built-in ad-hoc storage systems behind a common
interface: `workflow.create_adhoc_filesystem(provider, name, **options)`
returns a resource that the workflow starts before its tasks and stops after
them, and `resource.bind(task)` exports `DAGON_ADHOC_PATH` and
`DAGON_ADHOC_ACCESS` (`posix`, `preload`, `client`, or `object`) to the task.
DAGonFS and BeeOND provide mounted directories, Hercules and CAPIO intercept
file calls through a preloaded library, the DAGonFS native frontend needs a
client, and DynoStore is an object store. `default=True` binds a resource to
every task; `task.create_adhoc_filesystem(...)` creates a task-scope resource
that lives only around that task. A task may be bound to any number of
resources, each addressed as `DAGON_ADHOC_<NAME>_PATH` or, with `export="NAME"`, under a variable the developer chooses ([`task_scope_volume.py`](../../examples/adhoc/task_scope_volume.py)). A further system needs
only an adapter class registered with `register_provider`
([`custom_adapter.py`](../../examples/adhoc/custom_adapter.py)).

A resource whose adapter supports streaming can also carry a stream between
two tasks bound to it. The consumer reads `workflow:///B1/frames?stream`: the
query keeps the reference a valid `workflow://` reference (same dependency,
same producer path), but the consumer starts while the producer runs and
receives each published item as soon as its marker exists. See
[ad-hoc file systems](../adhoc_filesystems.md#streaming-between-tasks).

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_24_beeond_storage.py`](../../examples/tutorial/lesson_24_beeond_storage.py) and the longer [`beeond_local_emulation.py`](../../examples/dataflow/slurm/beeond_local_emulation.py).

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_24_beeond_storage.py
python examples/dataflow/slurm/beeond_local_emulation.py
python examples/adhoc/portable.py
python examples/adhoc/custom_adapter.py
python examples/adhoc/streaming.py
python examples/adhoc/streaming.py --emulate capio
python examples/adhoc/task_scope_volume.py
~~~

## Expected result

Invalid `scope`, `mount_template`, and `volume` values are rejected; the task volume is persisted and read through `workflow:///write/beeond/result.txt`; the workflow volume is shared. The ad-hoc example prints `Verified 6 providers through 12 tasks`: each provider's producer writes through its own path and its consumer reads the file back. `task_scope_volume.py` prints `Verification: ok` after B used two task-scope volumes as `$MYVOLUME_1` and `$MYVOLUME_2` and C, which saw neither, read B's result. `custom_adapter.py` prints `Verification: ok` after a workflow-scope default volume and a task-scope volume were both bound to one task. `streaming.py` runs `A → {B1, C}`, `B1 → B2`, `{B2, C} → D` and prints how long before B1 finished B2 received the first of eight verified frames (about 3 s locally).

## Verify

~~~bash
python examples/tutorial/lesson_24_beeond_storage.py
python -m unittest tests.test_beeond -v
python -m unittest tests.test_adhoc_filesystems tests.test_adhoc_streaming -v
~~~

Emulation does not reproduce volume speed, multi-node sharing, or the holder job, and the ad-hoc example redirects every path to a local directory without starting any provider (`DAGON_ADHOC_EMULATED=1`). The CI `beeond-slurm` job adds single-node Slurm evidence with an emulated site.

## What DAGonStar did

DAGonStar validated BeeOND options, added the site comment exactly once, and under emulation ran the same launcher fragments against persistent directories.

## Controlled experiment

Predict how many `--comment` options appear when the task already passes `comment="beeond-fs"`; the script asserts one. Then explain why BeeOND tasks are ineligible for pre-staging. Finally, bind one task to both the `ram` (DAGonFS) and `stream` (CAPIO) resources of `examples/adhoc/portable.py` and predict which provider `DAGON_ADHOC_PATH` names; confirm with `DAGON_ADHOC_RAM_PATH` and `DAGON_ADHOC_STREAM_PATH`. Last, remove `?stream` from B2's command in `examples/adhoc/streaming.py` and predict the change: B2 then waits for B1 to finish, the first-arrival check fails, and every frame is read from a staged copy.

## Common problems and diagnosis

Read `.dagon/beeond_persist.status` for persistence failures. A missing mount fails fast. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record where job-local data was persisted and verify it, because the source file system no longer exists. Record the ad-hoc provider, access mode, and frontend from the task's execution metadata, and distinguish an emulated run from a live one. A streamed result is verified item by item (size and SHA-256), and a stream that its producer ended with a failure fails its consumer, so partial results are never mistaken for complete ones.

## Summary

Job-local storage is fast but volatile; persistence is an explicit, verified step.

## Next lesson

Next, move input staging out of the allocation with scheduler-aware pre-staging. Return to the [syllabus](README.md) at any time.
