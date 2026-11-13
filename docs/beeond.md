# BeeOND on-demand file systems

**Status:** infrastructure-dependent. Command generation, launcher fragments,
the holder lifecycle, and portable emulation are tested locally. CI also runs
both scopes on a real single-node Slurm cluster with an emulated BeeOND site
(see [below](#continuous-integration)). A production run needs a Slurm site
that provisions BeeOND (BeeGFS On Demand) volumes for jobs. Both scopes have
also been run on real BeeOND: on 2026-11-13,
`tools/ci_beeond_slurm.py --nodes 4` passed all 18 checks on a production BeeOND site (Rocky Linux 8.10, Slurm
23.11.3, four nodes), and `examples/dataflow/slurm/beeond_slurm.py` completed
in both scopes there.

## What BeeOND is in Slurm terms

Some Slurm sites create a job-private BeeGFS file system across the nodes of
an allocation when the job is submitted with a site-specific comment. For
example, a site may use this batch script:

```bash
#SBATCH --nodelist=wn[01-04]
#SBATCH --partition=xxcpu
#SBATCH --comment=beeond-fs
#SBATCH --ntasks-per-node=1
MOUNT="/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}"
srun ... writes "$MOUNT"/node_${HOST}.txt
cat "$MOUNT"/node_*.txt > "$HOME/out"   # copy results to persistent storage
```

The volume is fast, shared by every node of the job, and **destroyed when the
job ends**. Anything not copied to persistent storage before then is lost.
DAGonStar automates that pattern for Slurm tasks.

## Scopes

| Scope | Volume lifetime | How tasks run | Persistence |
|---|---|---|---|
| `task` | one Slurm job per task | `sbatch -W --comment=<comment>` (unchanged submission path) | the launcher copies the volume to `<working_dir>/beeond` before the job ends |
| `workflow` | one holder job per workflow volume | `srun --jobid=<holder>` steps inside the holder allocation | the holder copies the volume to the workflow persistent directory when the workflow ends |

In both scopes the command finds the volume through `$DAGON_BEEOND`.
`$DAGON_BEEOND_SCOPE` is `task` or `workflow`; `$DAGON_BEEOND_PERSIST_DIR` is
the persistent destination when persistence is enabled; workflow-scope steps
also see `$DAGON_BEEOND_VOLUME`. `$DAGON_BEEOND_JOB_ID`, `$DAGON_BEEOND_NODES`,
and `$DAGON_BEEOND_NODELIST` describe the Slurm job that owns the volume: the
task's own job in task scope, the holder job in workflow scope.

### Parallel steps: `dagon_beeond_srun`

Every BeeOND launcher defines the bash function `dagon_beeond_srun`, which
starts a parallel step on the nodes of the job that owns the volume. Use it
instead of `srun` so the same command works in both scopes:

```bash
dagon_beeond_srun --nodes="$DAGON_BEEOND_NODES" --ntasks-per-node=1 \
  bash -c 'hostname > "$DAGON_BEEOND/node_$(hostname).txt"'
```

In task scope it is plain `srun`, because the launcher is the batch script of
the BeeOND job. In workflow scope the launcher is itself a one-node step of the
holder, and a nested `srun` is confined to that step (Slurm reports
`Only allocated 1 nodes asked for 4`, and `$SLURM_JOB_NUM_NODES` is unset).
The helper therefore clears the step's `SLURM_*` variables and runs
`srun --jobid=$DAGON_BEEOND_JOB_ID --overlap ...`, a new step of the holder
allocation that can use every holder node. Under portable emulation the helper
runs the program once locally and skips leading options, so write options as
`--option=value` or end them with `--`.

### Per-task volume

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("beeond-demo")
simulate = DagonTask(
    TaskType.SLURM, "simulate",
    'dagon_beeond_srun --nodes="$DAGON_BEEOND_NODES" --ntasks-per-node=1 '
    'bash -c \'hostname > "$DAGON_BEEOND/node_$(hostname).txt"\' && '
    'cat "$DAGON_BEEOND"/node_*.txt > "$DAGON_BEEOND/all_nodes.txt"',
    partition="xxcpu", nodes=4, nodelist="wn[01-04]", ntasks_per_node=1,
    beeond="task",
)
combine = DagonTask(TaskType.SLURM, "combine",
                    "cp workflow:///simulate/beeond/all_nodes.txt combined.txt")
workflow.add_task(simulate)
workflow.add_task(combine)
workflow.run()
```

`beeond="task"` (or `beeond=True`) adds `--comment=beeond-fs` to the `sbatch`
command once, even when other comments are configured. The generated launcher:

1. resolves the mount point from `mount_template` on the first node of the job
   and waits up to `mount_timeout` seconds for it to become writable;
2. runs the command in the background and waits for it, so signal traps fire
   while the command runs;
3. copies the volume to the persistent directory (`<working_dir>/beeond` by
   default), verifies the copy, and writes `.dagon/beeond_persist.status`;
4. returns a failure code when the command **or** the persistence failed.

Downstream tasks consume persisted data with ordinary `workflow://` references
such as `workflow:///simulate/beeond/result.dat`. Dependency discovery and
staging work as for any other task output.

### Per-workflow volume

```python
workflow = Workflow("beeond-shared")
workflow.create_beeond_volume(
    "scratch", partition="xxcpu", nodelist="wn[01-04]", ntasks_per_node=1,
    time="04:00:00", signal_grace=300,
)
prepare = DagonTask(TaskType.SLURM, "prepare", './prepare.sh "$DAGON_BEEOND"',
                    beeond="workflow:scratch")
solve = DagonTask(TaskType.SLURM, "solve", './solve.sh "$DAGON_BEEOND"',
                  beeond="workflow:scratch")
workflow.add_task(prepare)
workflow.add_task(solve)
workflow.make_dependencies()
solve.add_dependency_to(prepare)   # shared-volume data is not a workflow:// reference
workflow.run()
```

`beeond="workflow"` uses the volume named `default`. When a task asks for a
volume that does not exist yet, DAGonStar creates it from the `[beeond]`
configuration. The first task that runs:

1. writes a holder script under the volume state directory and submits it with
   `sbatch --parsable --comment=<comment>` plus the allocation options;
2. waits up to `start_timeout` seconds until the holder reports its job id and
   mount point (`ready` file), and cancels the holder if it fails or times out.

Every task attached to the volume then runs its launcher as a job step,
`srun --jobid=<holder> --overlap --nodes=1 --ntasks=1 -J <task> -D <working_dir> bash launcher.sh`.
The task's own `partition`, `nodes`, and similar `sbatch` options do not apply
inside the existing allocation. Size the holder with the volume's `nodes` or
`nodelist`, and start parallel work across it with `dagon_beeond_srun` (see
above); a plain nested `srun` cannot leave the task's one-node step.

When `Workflow.run()` ends, including after task failures, DAGonStar writes the
`stop` file. The holder copies the volume to the persistent directory
(`<scratch_dir_base>/<workflow>-beeond-<volume>` by default), verifies it,
writes `done`, and exits, which releases the allocation. `run()` raises
`RuntimeError` if the holder reports a persistence failure or exits without
confirming persistence, after writing the checkpoint file. You can also call
`workflow.stop_beeond_volumes()` yourself.

Tasks that share a workflow volume do not get implicit dependencies from it.
Declare the order with `add_dependency_to` after `make_dependencies()`, or let
`workflow://` references order them.

## Configuration

Defaults come from an optional `[beeond]` section of `dagon.ini`. Keyword
arguments of `Workflow.create_beeond_volume(...)`, a `BeeONDConfig`, or a dict
passed as `beeond=` override them. Unknown keys raise `ValueError`, so a
misspelled option cannot silently disable persistence.

```ini
[beeond]
comment=beeond-fs
mount_template=/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}
mount_timeout=120
persist=True
persist_on_failure=True
persist_tool=auto
verify=list
; Ask Slurm to send SIGUSR1 this many seconds before the time limit.
signal_grace=300
; Workflow-scope holder allocation:
partition=xxcpu
nodelist=wn[01-04]
ntasks_per_node=1
time=04:00:00
```

| Option | Default | Meaning |
|---|---|---|
| `scope` | `task` | `task` or `workflow` (when given as a dict or `BeeONDConfig`) |
| `volume` | `default` | workflow volume name (letters, digits, `.`, `_`, `-`) |
| `comment` | `beeond-fs` | Slurm `--comment` that makes the site provision BeeOND |
| `mount_template` | `/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}` | mount point, expanded by bash on the node; `$VAR`/`${VAR}` only, no quotes, backslashes, backticks, or `$(...)` |
| `mount_timeout` | `120` | seconds to wait for a writable mount |
| `persist` | `True` | copy the volume before it is destroyed |
| `persist_dir` | task: `beeond`; workflow: `<workflow>-beeond-<volume>` | destination; relative task paths are relative to the working directory, relative workflow paths to the workflow scratch directory |
| `persist_on_failure` | `True` | task scope: also persist when the command failed |
| `persist_tool` | `auto` | `auto` (rsync if present, else `cp -a`), `rsync`, or `cp` |
| `verify` | `list` | `none`, `list` (every source file exists in the copy), or `checksum` (POSIX `cksum` of every file) |
| `signal_grace` | unset | adds `--signal=B:USR1@<seconds>` so data is persisted before the time limit |
| `persist_each_task` | `False` | workflow scope: also persist after every task step |
| `restore` | `False` | workflow scope: copy an existing persistent directory into a fresh volume (resume) |
| `nodes`, `nodelist`, `partition`, `time`, `ntasks_per_node` | unset | workflow scope: holder allocation |
| `sbatch_options` | empty | workflow scope: extra holder `sbatch` arguments (space-separated in `dagon.ini`) |
| `step_options` | `--overlap --nodes=1 --ntasks=1` | workflow scope: options of each task step |
| `state_dir` | `<scratch_dir_base>/.dagon-beeond/<workflow>-<volume>` | workflow scope: holder script, log, and control files |
| `start_timeout`, `stop_timeout`, `poll_interval` | `600`, `3600`, `5` | workflow scope: holder waits, in seconds |

`Slurm` and `RemoteSlurm` also accept `nodelist=` and `sbatch_options=` for
per-task submissions. `RemoteSlurm` additionally accepts `comment`, `time`,
`nodes`, `ntasks_per_node`, and `ssh_port`.

## Persistence guarantees and limits

What DAGonStar guarantees:

- on normal completion, whether the command succeeded or failed (task scope,
  unless `persist_on_failure=False`), the volume is copied before the job ends,
  the copy is verified as configured, and a failed copy fails the task;
- on `SIGUSR1` (from `signal_grace`) or `SIGTERM`, the task launcher stops the
  command's process group (all its descendants), persists, and exits non-zero; the holder
  persists and exits when it receives those signals;
- the persistence status, file lists, and checksums are written next to the
  launcher (`<working_dir>/.dagon/`) or to the holder state directory.

What it cannot guarantee:

- `SIGKILL`, node failure, or a time limit without a sufficient
  `signal_grace` window destroys the volume before it can be copied;
- a snapshot taken on a signal reflects whatever the stopped command had
  written; processes that leave the command's process group (for example with
  `setsid`) are not stopped;
- `verify=list` checks presence, not content; use `verify=checksum` when
  content integrity matters and the copy time is acceptable;
- file names that contain newlines are not handled by verification;
- the persistent directory, the working directory, and the workflow state
  directory must be on a file system shared by the login node and the compute
  nodes (the usual case for `scratch_dir_base` on clusters).

`persist=False` gives a purely temporary scratch volume.

## Checkpoints, FAIR, JSON, and CWL

- **Checkpoints.** Each task checkpoint records `beeond.scope` and
  `beeond.persist_dir` (plus `volume` for workflow scope). Task-scope data lives
  in the working directory, so checkpoint reuse sees it. A resumed workflow gets
  a new workflow volume; set `restore=True` to copy the previous persistent
  directory into it.
- **FAIR.** With FAIR recording enabled, the task record's `execution.beeond`
  holds the scope, comment, persistence settings, and, for workflow volumes, the
  holder job id and mount point. No credentials are involved.
- **JSON.** `Workflow.as_json()` includes the task's `beeond` specification and
  `jsonload` restores it for Slurm tasks.
- **CWL.** `saveAsCWL` is unchanged: BeeOND is DAGonStar execution behavior and
  is not exported. A command that uses `$DAGON_BEEOND` needs that variable from
  the CWL runner's environment to run there.

## Portable emulation and local testing

With `Workflow(..., portable_emulation=True)` no scheduler is contacted.
`$DAGON_BEEOND` points directly at the persistent directory: `<working_dir>/beeond`
for task scope and the workflow persistent directory for workflow scope. The
graph, the data paths, and the `workflow:///<task>/beeond/...` references
therefore behave as on the cluster. The volume speed, the multi-node sharing,
and the holder job are not emulated.
[`examples/dataflow/slurm/beeond_local_emulation.py`](../examples/dataflow/slurm/beeond_local_emulation.py)
is the self-contained demonstration, and `tests/test_beeond.py` runs the
generated bash fragments against a temporary directory that stands in for the
mount.

## Continuous integration

The `beeond-slurm` job of `.github/workflows/ci.yml` starts a single-node Slurm
cluster with `tools/ci/slurm/setup-slurm-beeond.sh`. A Prolog creates the
default mount point for every job whose comment contains `beeond-fs`, and an
Epilog deletes it when the job ends, so data survives only if DAGonStar
persisted it in time. `tools/ci_beeond_slurm.py` runs these checks with
`verify=checksum`: per-task persistence and a downstream `workflow://` read,
persistence after a failing command, a per-workflow holder volume shared by two
`srun --jobid` steps, the `signal_grace` time-limit warning, and the teardown of
every created volume. The emulated volume is a local directory, so BeeGFS
behavior and multi-node sharing are not tested. On a cluster you control, run
the same checks with
`python tools/ci_beeond_slurm.py --partition <partition> --nodes <n> --scratch <shared-dir>`;
`--nodes` sets the number of nodes of every BeeOND job and holder.

### Live site verification

On 2026-11-13, `tools/ci_beeond_slurm.py --nodes 4` passed all 18 checks on a
production BeeOND site (Rocky Linux 8.10, Slurm 23.11.3, four nodes), and
`examples/dataflow/slurm/beeond_slurm.py` completed in both scopes there. This is a
one-time manual run, not part of CI; repeat it on your site after upgrading
DAGonStar or Slurm.

## Troubleshooting

- *"BeeOND mount ... is not available"*: the site did not create the volume.
  Check the comment value, the partition, and whether the site requires
  exclusive nodes (`sbatch_options=["--exclusive"]`). Compare
  `mount_template` with the path the site documents.
- *"BeeOND mount ... is not available" although the path exists*: the mount
  must be a writable directory. Some sites provision BeeOND only for
  multi-node jobs and give single-node jobs a node-local substitute; at one
  site that substitute was a root-owned `/scratch/jobid-<id>` with mode
  `drwx------`, which the job cannot write. Request at least two nodes
  (`nodes=2` or a `nodelist`) or ask the site to fix the ownership.
- *Holder never becomes ready*: read `holder-<jobid>.out` in the state
  directory, and check `squeue` for pending reasons; raise `start_timeout`
  for busy queues.
- *Steps fail with resource errors*: older Slurm releases lack `--overlap`;
  set `step_options` to options your site supports.
- *Persistence failed*: read `beeond_persist.status` and the `.lst` or
  `.cksum` files, and check quota on the persistent file system.
