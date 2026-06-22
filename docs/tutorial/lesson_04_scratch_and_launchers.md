# Lesson 04: Inspect Scratch Directories and Generated Launchers

## Objective

Understand what DAGonStar writes during execution.

## Concept

Each task has a working directory and an internal `.dagon` directory containing
generated scripts and captured output.

## Code

Use the workflow from Lesson 03 or create:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson04")
    task = DagonTask(TaskType.BATCH, "inspect", "pwd; echo product > product.txt")
    workflow.add_task(task)
    workflow.make_dependencies()
    workflow.run()
```

## Run

```bash
python lesson_04.py
```

## Verify

```bash
DIR=$(find /tmp -maxdepth 1 -type d -name '*-inspect' | tail -n 1)
ls "$DIR"
ls "$DIR/.dagon"
sed -n '1,160p' "$DIR/.dagon/launcher.sh"
sed -n '1,160p' "$DIR/.dagon/stdout.txt"
```

## Expected behavior

You should see:

- task output files in the task directory;
- `.dagon/launcher.sh`;
- `.dagon/context.sh`;
- `.dagon/stdout.txt`.

## Scientific practice note

Generated launchers are a practical provenance artifact. They show the actual
command DAGonStar executed after preprocessing.
