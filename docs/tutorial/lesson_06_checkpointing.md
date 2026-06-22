# Lesson 06: Use Checkpoint Files

## Objective

Record task completion metadata and resume a workflow.

## Concept

`Workflow(checkpoint_file=...)` writes checkpoint metadata after execution.
`workflow.run(resume_checkpoint_file=...)` can reuse completed task directories
when the checkpoint records success and the working directory still exists.

## Code

Create `lesson_06.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


def build_workflow():
    workflow = Workflow("Lesson06", checkpoint_file="lesson_06_checkpoint.json")
    slow = DagonTask(TaskType.BATCH, "slow", "echo computed > result.txt")
    workflow.add_task(slow)
    workflow.make_dependencies()
    return workflow


if __name__ == "__main__":
    workflow = build_workflow()
    workflow.run(resume_checkpoint_file="lesson_06_checkpoint.json")
```

## Run twice

```bash
python lesson_06.py
python lesson_06.py
```

## Verify

```bash
sed -n '1,200p' lesson_06_checkpoint.json
```

## Expected behavior

After the first run, the checkpoint file contains the task working directory and
exit code. On a later run, DAGonStar can skip a task already marked successful if
the recorded working directory still exists.

## Scientific practice note

Checkpointing is most valuable for expensive simulations. Preserve checkpoint
files together with enough metadata to know which code and configuration
produced them.
