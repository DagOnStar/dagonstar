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
    (content, where the source is readable) -> .dagon/stage-in-identity.txt
    -> .dagon/stage-in-complete.json -> launcher.sh (compute only)
    -> sbatch --parsable -W -> queue -> allocation -> compute -> downstream references
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
| any | `True` on a BeeOND, parallel-mode, or `StagerMover.SLURM` task | rejected | — |
| `True` | `None` on a BeeOND, parallel-mode, or `StagerMover.SLURM` task | legacy, with a warning | — |

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
- **`StagerMover.SLURM`** (set on the task or inherited from the workflow).
  This stager mover submits a small copy job for every transfer, so it would
  request scheduler resources before stage-in had succeeded. That contradicts
  the pre-staging contract, so the combination is refused. `StagerMover.NORMAL`
  and `StagerMover.PARALLEL` (GNU `parallel` on the submission host) are
  eligible.

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

DAGonStar cannot detect a violation of these requirements before submission.
The compute launcher therefore checks, before the prologue and the command,
that `.dagon/stage-in-complete.json` and every staged input are visible on the
compute node. If they are not, the job exits with "the scratch directory must
be shared with the submission host" and the task fails with
`failure_phase == "execution"`, so the command never runs on missing data.
This check catches a scratch directory that is missing or empty on the compute
node. It cannot detect a different copy of the same files at the same path,
and by the time it runs the allocation has already been granted. Configure
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
| `stage_in.sh` | DAGonStar | removes a stale marker, identity record, and previously staged inputs; runs the planned transfers; stops at the first failure; checks that every staged input exists and, where the source is readable on the submission host, that its content matches the source; records the source identity; exits non-zero on any failure; never runs the task command or the allocation prologue |
| `stage-in-identity.txt` | `stage_in.sh`, after successful verification | one `<name> <CRC> <size>` line per file of every content-verified source (POSIX `cksum`); its SHA-256 is stored in the marker and the checkpoint |
| `stage-in-complete.json` | DAGonStar, after `stage_in.sh` exits 0 | marker (schema `dagonstar.stage-in-marker/2`): task identity, input manifest with each input's integrity level, movers, policy version, timestamps, `source_identity_sha256`; no credentials |
| `launcher.sh` | DAGonStar | compute-only launcher: no transfers; records `allocation_started_at`, checks that the marker and staged inputs are visible on the compute node, then runs the prologue and the command |
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
`StagerMover.SLURM` is not eligible (see above).

## Verification and integrity

Every input has an integrity level, recorded in the marker:

| Level | When | What `stage_in.sh` checks |
|---|---|---|
| `content` | the context discovery chose a same-host `COPY` or `LINK` transfer, so the source is readable where `stage_in.sh` runs | every staged path exists, and the staged tree matches the source tree file by file: same relative names, same POSIX `cksum` CRC and size (links are followed) |
| `existence` | any other mover (`SCP`, `GRIDFTP`, `SKYCDS`, ...), whose source is on another host | every staged path exists (unmatched globs and dangling links fail) |

A transfer that exits 0 but writes wrong, truncated, or missing content is
therefore caught for `content` inputs, and the scheduler is not contacted.
For `existence` inputs DAGonStar does **not** claim corruption detection: it
relies on the mover's own exit status and checks only that the data arrived.
`cksum` is a CRC, which detects accidental corruption, not deliberate
tampering. Content verification reads every staged input and its source once
more on the submission host, so it adds I/O proportional to the input size.

## Failure handling

The gate is strict: **`sbatch` is never called when stage-in fails or when its
success cannot be confirmed.**

| Failure | Exception (`.phase`) | `task.failure_phase` | Scheduler contacted | Marker |
|---|---|---|---|---|
| context discovery or planning fails | `StageInFailedError` (`staging`) | `staging` | no | absent |
| a transfer fails, or an input is missing (verification) | `StageInFailedError` (`staging`) | `staging` | no | absent (a stale one is removed first) |
| writing `stage_in.sh` or the marker fails, or SSH drops | `StageInFailedError` (`staging`) | `staging` | no | absent |
| staged content differs from its source (`content` inputs) | `StageInFailedError` (`staging`) | `staging` | no | absent |
| a `workflow://` reference with a `..` component, an empty or `..` task name, or naming a whole scratch directory | `StageInFailedError` (`staging`), wrapping `PreStageConfigurationError` | `staging` | no | absent |
| `sbatch` exits non-zero and printed no job identifier | `SchedulerSubmissionError` (`submission`) | `submission` | rejected | kept |
| `sbatch` printed a job identifier and the job failed, including staged data not visible on the compute node | `ScheduledExecutionError` (`execution`) | `execution` | yes | kept |
| explicit unsupported request | `PreStageConfigurationError` (`configuration`) | — | no | — |

Pre-staged submissions add `--parsable` to `sbatch`, so its first output line
is the job identifier (`<id>` or `<id>;<cluster>`). The failure phase is
decided from that identifier (`dagon.task.parsable_job_id`), never from
display text such as `Submitted batch job`. The identifier is recorded as
`scheduler_job_id`. Legacy submissions are unchanged and do not use
`--parsable`.

The task status becomes `FAILED`, downstream tasks do not run, and the error
is logged as for any failed task. Staged inputs and the scratch directory are
not deleted on failure. Cleanup behaves as in the legacy lifecycle.

Unlike the legacy launcher, the stage-in script propagates transfer failures.
The legacy stager loop does not report a failed copy through `$?`, so that
loop is unchanged for compatibility. `stage_in.sh` uses the stager's strict
mode instead (`Stager.stage_in(..., strict=True)`).

## Retries, restarts, and checkpoints

- A completed pre-staged task (checkpoint `code == 0` and an accessible
  working directory) is reused on resume **only if its inputs are unchanged**.
  Before reuse, DAGonStar resolves every recorded input against the
  producer's *current* scratch directory, recomputes the source identity on
  the submission host (locally, or over SSH for RemoteSlurm, without writing a
  file), and compares its SHA-256 with the one recorded after the successful
  stage-in. If they differ, a warning is logged and the task runs again: it
  stages the new inputs and is submitted again.
- A completed checkpoint is also **not** reused, and the task runs again, when
  an input has the `existence` integrity level (its source cannot be re-read on
  the submission host), when a producer cannot be found, or when the
  checkpoint has no identity for the current policy version (for example, one
  written before policy version 2). Rerunning is the safe choice in each case.
- Identity covers content (names, CRCs, sizes), not timestamps. A producer
  that runs again and writes identical content does not invalidate its
  consumers.
- A task that failed in any phase has no successful checkpoint, so a rerun
  starts the whole lifecycle again. `stage_in.sh` first removes the old
  marker, the identity record, and everything under `.dagon/inputs`, so data
  from an earlier attempt is never trusted, and a partial transfer can never be
  reported as complete.
- The marker is provenance, not a skip token. DAGonStar never skips stage-in
  because a marker exists.
- The checkpoint entry gains
  `"pre_stage": {"effective": true, "staged": <bool>, "stage_in_code": <int>, "marker": ".dagon/stage-in-complete.json", "policy_version": 2, "source_identity_sha256": <hex>, "inputs": [{"reference", "workflow", "task", "local_path", "integrity"}]}`.
  These are references and relative paths. No credentials are stored.
- Legacy (non-pre-staged) checkpoints keep their historical behaviour: they
  are reused without input validation.

## Dry runs

With `workflow.set_dry(True)`, a pre-staged task has no side effects. It
creates no scratch directory and no checkpoint entry. It writes and runs no
script (including `context.sh`), and for RemoteSlurm it sends nothing over
SSH. It transfers nothing and does not contact the scheduler. It parses and
checks the `workflow://` references, logs the planned order
(`task.prepared_task.planned_order()`), and records `"dry_run": true` in its
metadata. Directories that would only be created at run time appear as
placeholders such as `<scratch of C>`. Because context discovery is skipped,
the dry run does not choose a data mover and does not report integrity levels.
The legacy dry run is unchanged; it still creates scratch directories and runs
`context.sh`.

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
| `policy_version` | pre-staging policy version (`2`) |
| `phase` | last internal phase |
| `inputs` | number of `workflow://` inputs |
| `inputs_content_verified` | how many inputs had their staged content compared with the source |
| `scheduler_job_id` | job identifier printed by `sbatch --parsable`, or `null` when none was printed |
| `dry_run` | `true` for a dry run |
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
  spaces are staged correctly. Its transfer template is assigned in single
  quotes, so `eval` expands `$file` and `$dst` as quoted variables rather than
  re-parsing their values. Shell syntax in a scratch path, such as `$(...)`,
  backticks, or `;`, is never executed (tested). The legacy launcher keeps its
  historical text, which expands the paths before `eval`.
- `context.sh`, which runs in both lifecycles, now quotes its `cd` into the
  scratch directory. Before this change, shell syntax in a scratch path was
  executed there, in every lifecycle.
- Rewritten `workflow://` arguments in the *user command* are inserted
  unquoted, as in the legacy lifecycle. The reference parser also ends a
  reference only at a space. A scratch path with spaces therefore breaks the
  user command, although staging succeeds. Use scratch paths without spaces,
  or reference inputs through a shell variable:
  `f=workflow:///A/out.txt ; cat "$f"`.
- In pre-staged mode a `workflow://` reference whose task name is empty or
  `..`, whose workflow name is `..`, whose path contains a `..` component, or
  whose path names the whole producer scratch directory is refused before any
  transfer. Such a reference could otherwise address files outside the
  producer's scratch directory or write outside `.dagon/inputs`. Symbolic links
  inside the producer's scratch directory are not resolved; they are producer
  outputs. The legacy lifecycle keeps its historical, unchecked parser; this
  hardening is not applied there.
- Markers and metadata contain no credentials. The marker lives in the task
  scratch directory and lists scratch paths, so treat it like the other
  `.dagon` files.
- RemoteSlurm reuses the task's existing SSH connection and key handling.

## Evidence and what it does not show

| Evidence | Where |
|---|---|
| Legacy launcher unchanged byte for byte | `tests/test_scheduler_prestaging.py`, fixture captured before the refactor |
| Ordering, gate, failures, retries, checkpoint resume and changed-input invalidation, side-effect-free dry run, content verification and corruption, `..` references, `StagerMover.SLURM` rejection, `--parsable` classification, spaces, JSON, CWL, FAIR | `tests/test_scheduler_prestaging.py` (mock `sbatch`) |
| RemoteSlurm over SSH, disconnects, failed script creation, failed remote `sbatch`, non-default port, dry run without SSH traffic, changed-input invalidation over SSH | `tests/test_remote_scheduler_prestaging.py` (loopback SSH double) |
| Stage-in finished before the job started, the job saw its inputs at start, content verified, job identifier from `--parsable`, failed stage-in never reached `sbatch`, BeeOND and `StagerMover.SLURM` rejected, changed input invalidates a checkpoint, `..` reference refused, dry run creates nothing | `tools/ci_prestage_slurm.py` on the CI single-node Slurm cluster |

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
