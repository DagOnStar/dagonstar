# Scheduler-aware pre-staging

Scheduler-aware pre-staging (`pre_stage`) is an opt-in execution mode for
Slurm and RemoteSlurm tasks. The task transfers its `workflow://` inputs
**before** it asks the scheduler for resources. With the default (legacy)
lifecycle, the transfer happens **inside** the job, while the allocation is
already held.

The feature is implemented in `dagon/prestage.py`, `Task.prepare_task`,
`Task.execute_pre_staged` (`dagon/task.py`), and the submission-host helpers of
`Slurm` and `RemoteSlurm` (`dagon/batch.py`). It is tested with a mock
`sbatch`, a loopback SSH double, and a real single-node Slurm cluster in CI
(see [Evidence](#evidence-and-what-it-does-not-show)). It has not been
validated on a production multi-node cluster.

## Motivation

A legacy scheduler task requests resources, waits in the queue, receives an
allocation, and then copies its inputs. Every allocated core is idle for the
whole copy. For a 200-core job whose inputs take 30 minutes to copy, the
allocation holds

```text
200 cores x 1800 s / 3600 = 100 core-hours
```

before the scientific computation starts. With pre-staging, the copy runs on
the submission (login) host first, so those 100 allocated core-hours are not
held. DAGonStar reports this figure as
`estimated_allocated_core_hours_saved = cores x staging_seconds / 3600`. It is
an estimate of allocated resources not held. It is **not** a measured
saving in queue time or wall time: the queue wait may be longer or shorter,
and the submission is simply later by the time spent staging.

## Lifecycles

Legacy (default, `pre_stage=False`):

```text
create scratch -> context.sh -> launcher.sh (stage-in + command) -> sbatch -W
    -> queue -> allocation -> stage-in -> compute -> downstream references
```

Pre-staged (`pre_stage=True`, eligible task):

```text
create scratch -> checkpoint record -> context.sh (submission host)
    -> stage plan -> stage_in.sh (submission host) -> verify staged inputs
    -> .dagon/stage-in-complete.json -> launcher.sh (compute only) -> sbatch -W
    -> queue -> allocation -> compute -> downstream references
```

No stage-out step is added. Downstream tasks read producer outputs through
`workflow://` as before.

The internal phase (`task.pre_stage_phase`, a `dagon.prestage.TaskPhase`) moves
through `PREPARING -> STAGING -> STAGED -> SUBMITTED -> COMPLETED`, or to
`FAILED`. `SUBMITTED` covers both the queue wait and the execution, because
`sbatch -W` returns only when the job ends. The public `dagon.Status` values
are unchanged: a task is `RUNNING` while it stages, waits, and computes, just
as a legacy Slurm task is `RUNNING` while its job is queued.

## Configuration and inheritance

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("forecast", pre_stage=True)              # default: False
simulate = DagonTask(TaskType.SLURM, "simulate", "...", ntasks=200)  # pre_stage=None: inherits True
analyse = DagonTask(TaskType.SLURM, "analyse", "...", pre_stage=False)  # explicit opt-out
```

| `Workflow(pre_stage=)` | task `pre_stage=` | Eligible Slurm/RemoteSlurm task | Other task types |
|---|---|---|---|
| `False` (default) | `None` (default) | legacy | legacy |
| `False` | `True` | **pre-staged** | rejected (`PreStageConfigurationError`) |
| `True` | `None` | **pre-staged** | legacy, unchanged |
| `True` | `False` | legacy | legacy |
| any | `True` on a BeeOND or parallel-mode task | rejected | — |
| `True` | `None` on a BeeOND or parallel-mode task | legacy, with a warning | — |

Rules:

- The resolution is `effective = task.pre_stage if task.pre_stage is not None
  else workflow.pre_stage`, limited to eligible tasks. It is computed when the
  task executes, so a later change to `workflow.pre_stage` is honoured. The
  declared task value is never modified.
- Only the real booleans `True` and `False` are accepted (and `None` for
  tasks). `"true"`, `1`, and similar values raise
  `dagon.prestage.PreStageConfigurationError`, a `ValueError`.
- `Workflow.add_task` validates an explicit `pre_stage=True` immediately, so an
  unsupported request fails before the workflow runs. The check runs again at
  execution, before the scratch directory is created.
- Positional constructor arguments are unchanged. `pre_stage` is the last
  keyword parameter of `Workflow`, `Slurm`, and `RemoteSlurm`.
- `Workflow.as_json()` adds `"pre_stage": true` only when the workflow enables
  it. A Slurm task adds `pre_stage` only when it is not `None`. Default JSON
  documents are unchanged, and `load_json` restores both values.

## Supported backends and eligibility

Eligibility is a backend capability (`Task.pre_stage_capable`) plus
per-task conditions (`Task.pre_stage_unsupported_reason()`). The task type
name is not used.

| Backend | Capable | Stage-in runs on |
|---|---|---|
| `Slurm` | yes | the local machine running DAGonStar (the submission host), outside any allocation, via the same route as `context.sh` |
| `RemoteSlurm` | yes | the remote login host, over SSH (`create_file` and `bash`), with no local mount assumed |
| `Batch`, `RemoteBatch`, Docker, Kubernetes, Apptainer, Nomad, cloud, Native, Web, LLM, FaaS, IoT, checkpoint | no | unchanged lifecycle |

Per-task conditions that make an eligible backend ineligible:

- **BeeOND** (`beeond=` set to anything except `None` or `False`). A task-scope
  volume exists only inside its own allocation. Workflow-scope tasks run as
  `srun` steps of a holder job that already holds its allocation. In both
  cases the BeeOND lifecycle depends on an allocation. Pre-staging with BeeOND
  is not supported. It would need a dedicated design and is future work.
- **Parallel mode** (`task.set_mode("parallel")`), which rewrites the graph
  while it plans staging.

Portable emulation (`Workflow(portable_emulation=True)`) ignores `pre_stage`,
because it never stages or submits.

## Filesystem requirements

Pre-staging is correct only when the task's scratch directory:

1. has the **same absolute path** on the submission host and on every compute
   node of the job;
2. **persists** for as long as the job waits in the queue;
3. is **writable** by the submitting user, both on the submission host and in
   the job;
4. is **not** node-local, job-local, or allocation-only storage, such as
   BeeOND, `$TMPDIR` on a compute node, or a burst buffer created at job
   start.

DAGonStar cannot always detect a violation of these requirements. A
non-shared scratch path that happens to exist on both sides would let
stage-in succeed while the job sees different or empty data. Configure
`[batch] scratch_dir_base` (or the task `working_dir`) on a shared parallel
file system before you enable pre-staging. For RemoteSlurm, scratch paths are
paths on the cluster. Stage-in runs on the login node, so the login node must
mount the same file system as the compute nodes.

## Recipes

Local Slurm, on a login node, with a shared scratch directory:

```bash
python examples/dataflow/slurm/pre_stage_local.py --scratch /shared/scratch/$USER/dagon --partition compute --cores 200
python examples/dataflow/slurm/pre_stage_local.py --scratch /shared/scratch/$USER/dagon --legacy
```

Remote Slurm, from a workstation, through SSH:

```bash
python examples/dataflow/slurm/pre_stage_remote.py --host LOGIN_HOST --user USER --key ~/.ssh/id_rsa --remote-scratch /shared/scratch/USER/dagon
```

Both examples submit real jobs. Run them only where you are authorised to. Without Slurm, run the deterministic comparison:

```bash
python examples/dataflow/slurm/pre_stage_mock.py
```

It replaces `sbatch` with `examples/dataflow/slurm/mock_scheduler.py`, runs the
same coastal-forecast workflow in both lifecycles, and prints `Verification: ok`
when the evidence recorded at submission time matches the expected order.

## What is generated

Each pre-staged task writes these files in `<working_dir>/.dagon/`:

| File | Written by | Content |
|---|---|---|
| `context.sh` | DAGonStar | host and protocol discovery (unchanged) |
| `stage_in.sh` | DAGonStar | removes a stale marker, runs the planned transfers, stops at the first failure, checks that every staged input exists, exits non-zero on any failure; never runs the task command or the allocation prologue |
| `stage-in-complete.json` | DAGonStar, after `stage_in.sh` exits 0 | marker: task identity, input manifest, movers, policy version, timestamps; no credentials |
| `launcher.sh` | DAGonStar | compute-only launcher: no transfers; records `allocation_started_at` and runs the prologue and the command |
| `allocation_started_at` | the job | epoch seconds at which the allocation started running the launcher |

The stage-in plan and the compute launcher are rendered from one structured
`PreparedTask` (`Task.prepare_task`), not by splitting the legacy launcher's
text. Inputs are therefore staged exactly once: before submission when
pre-staging is effective, inside the job otherwise. The legacy launcher is
rendered from the same plan and is byte-for-byte unchanged
(`tests/fixtures/legacy_slurm_launcher.sh`).

The movers keep their semantics. `COPY`, `LINK`, and `SCP`-from-a-remote-source
transfers run in `stage_in.sh`. Movers that already transferred data while
DAGonStar planned staging continue to do so: `SCP` from a local source to a
remote destination, `GRIDFTP`, and `SKYCDS`. Planning happens before
submission, so these transfers also finish before `sbatch`.
`StagerMover.SLURM` submits its own small copy jobs and waits for them to leave
the queue. Their exit status is not checked, so the final verification step is
what catches a failed copy.

## Failure handling

The gate is strict: **`sbatch` is never called when stage-in fails or when its
success cannot be confirmed.**

| Failure | Exception (`.phase`) | `task.failure_phase` | Scheduler contacted | Marker |
|---|---|---|---|---|
| context discovery or planning fails | `StageInFailedError` (`staging`) | `staging` | no | absent |
| a transfer fails, or an input is missing (verification) | `StageInFailedError` (`staging`) | `staging` | no | absent (a stale one is removed first) |
| writing `stage_in.sh` or the marker fails, or SSH drops | `StageInFailedError` (`staging`) | `staging` | no | absent |
| `sbatch` exits non-zero without `Submitted batch job` | `SchedulerSubmissionError` (`submission`) | `submission` | rejected | kept |
| the job ran and failed | `ScheduledExecutionError` (`execution`) | `execution` | yes | kept |
| explicit unsupported request | `PreStageConfigurationError` (`configuration`) | — | no | — |

The task status becomes `FAILED`, downstream tasks do not run, and the error
is logged as for any failed task. Staged inputs and the scratch directory are
not deleted on failure. Cleanup behaves as in the legacy lifecycle.

Unlike the legacy launcher, the stage-in script propagates transfer failures.
The legacy stager loop does not report a failed copy through `$?`, so that
loop is unchanged for compatibility. `stage_in.sh` uses the stager's strict
mode instead (`Stager.stage_in(..., strict=True)`).

## Retries, restarts, and checkpoints

- A completed task (checkpoint `code == 0` and an accessible working
  directory) is reused on resume as before: nothing is staged or submitted
  again.
- A task that failed in any phase has no successful checkpoint, so a rerun
  starts the whole lifecycle again. With a fixed `working_dir`, `stage_in.sh`
  first removes the old marker. A partial transfer can never be reported as
  complete, and copies overwrite partial files.
- The marker is provenance, not a skip token. DAGonStar never skips stage-in
  because a marker exists, because upstream outputs may have changed since.
- The checkpoint entry gains
  `"pre_stage": {"effective": true, "staged": <bool>, "stage_in_code": <int>, "marker": ".dagon/stage-in-complete.json"}`.

## Dry runs

With `workflow.set_dry(True)`, a pre-staged task discovers its context and
builds the plan, as the legacy dry run does. It then logs the planned order
(`task.prepared_task.planned_order()`) and stops: it neither writes nor runs
`stage_in.sh`, and it does not submit.

## Events and metrics

`on_task_staging_in_start` and `on_task_staging_in_end` bracket context
discovery, planning, **and the actual transfer** in pre-staged mode. In legacy
mode they still bracket only launcher generation, because the transfer happens
later inside the job. `on_task_execute_start` fires just before submission in
both modes.

`task.get_execution_metadata()["pre_stage"]` (and therefore FAIR
`execution.pre_stage`) contains only timings, counts, and identifiers, never
paths or credentials:

| Key | Meaning |
|---|---|
| `pre_stage_effective` | whether the task was pre-staged (also `false` when configured but not effective) |
| `policy_version` | pre-staging policy version (`1`) |
| `phase` | last internal phase |
| `inputs` | number of `workflow://` inputs |
| `staging_started_at`, `staging_finished_at`, `staging_seconds` | submission-host stage-in timing |
| `requested_cores`, `estimated_allocated_core_hours_saved` | `ntasks` (or `nodes x ntasks_per_node`) and `cores x staging_seconds / 3600` |
| `submission_started_at`, `scheduler_returned_at`, `scheduler_wall_seconds` | `sbatch -W` call; the wall time includes the queue wait |
| `allocation_wait_seconds`, `execution_seconds` | derived from `allocation_started_at` when it can be read; one-second resolution and dependent on synchronised clocks; otherwise `null` |

Tasks for which pre-staging is not configured have no `pre_stage` key, so
existing FAIR records are unchanged.

## CWL export

`saveAsCWL()` output does not depend on `pre_stage`. Pre-staging is a
DAGonStar scheduler policy outside the portable command-graph semantics
described in [CWL export](cwl_export.md). It is neither exported nor
annotated, and the export stays standards-valid.

## Security

- Generated scripts quote scratch paths with `shlex.quote`. The stage-in loop
  expands sources with `IFS` set to a newline, so scratch paths that contain
  spaces are staged correctly.
- Rewritten `workflow://` arguments in the *user command* are inserted
  unquoted, as in the legacy lifecycle. The reference parser also ends a
  reference only at a space. A scratch path with spaces therefore breaks the
  user command, although staging succeeds. Use scratch paths without spaces,
  or reference inputs through a shell variable:
  `f=workflow:///A/out.txt ; cat "$f"`.
- Markers and metadata contain no credentials. The marker lives in the task
  scratch directory and lists scratch paths, so treat it like the other
  `.dagon` files.
- RemoteSlurm reuses the task's existing SSH connection and key handling.

## Evidence and what it does not show

| Evidence | Where |
|---|---|
| Legacy launcher unchanged byte for byte | `tests/test_scheduler_prestaging.py`, fixture captured before the refactor |
| Ordering, gate, failures, retries, checkpoint resume, dry run, spaces, JSON, CWL, FAIR | `tests/test_scheduler_prestaging.py` (mock `sbatch`) |
| RemoteSlurm over SSH, disconnects, failed script creation, failed remote `sbatch`, non-default port | `tests/test_remote_scheduler_prestaging.py` (loopback SSH double) |
| Stage-in finished before the job started, the job saw its inputs at start, failed stage-in never reached `sbatch`, BeeOND rejected | `tools/ci_prestage_slurm.py` on the CI single-node Slurm cluster |

A single-node CI cluster with an empty queue cannot show queue-time
behaviour, multi-node file-system visibility, or production-scale transfers.
Before you rely on pre-staging at a site, run `pre_stage_local.py` or
`pre_stage_remote.py` there with a representative input size, and confirm that
the scratch file system meets the requirements above.

## FAQ and migration

**Do existing workflows change?** No. `pre_stage` defaults to `False`, the
legacy launcher is unchanged byte for byte, and other task types ignore the
workflow default.

**How do I enable it for one expensive step only?** Leave the workflow default
at `False` and pass `pre_stage=True` to that Slurm task.

**What if a task has no `workflow://` inputs?** The stage-in script is a
verified no-op, the marker is written, and the job is submitted.

**Will the job start sooner?** Not necessarily. The job is submitted after
staging, so its queue wait starts later. The benefit is that allocated
resources are not held while data is copied.

**Can I use it with BeeOND?** Not yet. An explicit request is rejected. An
inherited workflow default falls back to the legacy lifecycle with a warning.
