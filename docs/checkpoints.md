# Checkpoints

## FAIR checkpoint provenance

When FAIR recording is enabled, a task satisfied from a successful checkpoint
is marked `checkpoint_reused` in `run.json`. Its known working directory and
the normal task status remain available for later provenance interpretation.
Checkpointing lets DAGonStar record completed task state and reuse successful
task outputs in later runs. This is especially important for scientific
workflows where a simulation or data transfer may be expensive.

## What checkpointing records

When a `Workflow` is created with `checkpoint_file`, DAGonStar writes a JSON file
containing:

- workflow scratch base;
- per-task working directories;
- workflow name;
- task name;
- task exit code after execution.

Example shape:

```json
{
  "_scratch_dir": "/tmp/",
  "Experiment.A": {
    "working_dir": "/tmp/1710000000000-A",
    "workflow": "Experiment",
    "name": "A",
    "code": 0
  }
}
```

## Creating a checkpointed workflow

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("Experiment", checkpoint_file="checkpoint.json")

task = DagonTask(TaskType.BATCH, "A", "echo result > result.txt")
workflow.add_task(task)
workflow.make_dependencies()
workflow.run()
```

After the run, `checkpoint.json` is written.

## Resuming from a checkpoint

```python
workflow = Workflow("Experiment", checkpoint_file="checkpoint.json")
task = DagonTask(TaskType.BATCH, "A", "echo result > result.txt")
workflow.add_task(task)
workflow.make_dependencies()
workflow.run(resume_checkpoint_file="checkpoint.json")
```

If the checkpoint contains `code: 0` for `Experiment.A` and the recorded working
directory still exists, the task can be treated as already complete.

## Task identity

Checkpoint keys are built from:

```text
<workflow-name>.<task-name>
```

Therefore, stable workflow and task names are essential. If you rename a task,
DAGonStar treats it as a different checkpoint entry.

## Working directory persistence

Checkpoint reuse requires the recorded working directory to exist.

If scratch directories are deleted, moved, or garbage-collected, checkpoint reuse
cannot recover those task outputs.

For long-running scientific workflows, put scratch directories on storage with a
retention policy appropriate to the experiment.

## Checkpointing and dataflow

For dataflow workflows, checkpointing is most useful when upstream tasks produce
large intermediate files. If a downstream task fails, upstream successful tasks
may be reused on the next run.

Example:

```text
download -> preprocess -> simulate -> postprocess
```

If `simulate` fails, a later run may reuse `download` and `preprocess` if their
working directories and checkpoint entries remain valid.

## Explicit checkpoint tasks

`TaskType.CHECKPOINT` maps to `dagon.checkpoint.Checkpoint`. This task type is
part of the implementation for explicit checkpoint behavior. The workflow-level
`checkpoint_file` is the primary user-facing mechanism for recording and
resuming task metadata.

All registered task types use the same successful-checkpoint contract. LLM,
Native, Web, and FaaS implement it in their structured executors;
command-oriented tasks inherit it from `Task`. See
[Task-type interoperability](tasktype_interoperability.md).

## Remote checkpointing

Remote checkpoint reuse checks for the existence of the recorded directory on
the remote host through the task's SSH connection. This means:

- the same host must be reachable;
- credentials must still work;
- the remote scratch directory must still exist;
- paths must be valid on the remote filesystem.

## Docker and cloud checkpointing

Docker and cloud task checkpointing depends on the persistence of the host
scratch directory and, for cloud tasks, the persistence or reconstruction of the
remote execution environment.

Do not assume a terminated cloud instance preserves local scratch data unless it
was written to persistent storage.

## Scientific usage pattern

For expensive workflows:

1. Use a stable workflow name.
2. Use stable task names.
3. Set `checkpoint_file`.
4. Set a scratch base with enough storage.
5. Preserve the checkpoint JSON with experiment metadata.
6. Preserve or archive task working directories needed for reuse.
7. On rerun, use `resume_checkpoint_file`.

## Limitations and cautions

- Checkpoints record task success and working directory, not full semantic
  equivalence of code, inputs, or parameters.
- If a command changes but the task name and previous success remain, checkpoint
  reuse may skip recomputation.
- For rigorous scientific reproducibility, store code version, configuration,
  input checksums, and software environment alongside the checkpoint file.
- Garbage collection or manual cleanup can invalidate checkpoint reuse.

## Verification example

Run:

```bash
cd examples/dataflow/batch
python dataflow-checkpoint-demo.py
```

Then inspect the generated checkpoint file named by the example script.

For a minimal custom test:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


def build():
    workflow = Workflow("CheckpointDemo", checkpoint_file="checkpoint.json")
    task = DagonTask(TaskType.BATCH, "A", "echo data > data.txt")
    workflow.add_task(task)
    workflow.make_dependencies()
    return workflow


build().run(resume_checkpoint_file="checkpoint.json")
build().run(resume_checkpoint_file="checkpoint.json")
```

The second run can reuse the completed task if the recorded directory remains.
