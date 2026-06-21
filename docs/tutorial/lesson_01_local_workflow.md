# Lesson 01: Create a Local Workflow

## Objective

Create and run the smallest useful DAGonStar workflow.

## Concept

A `Workflow` owns tasks. A `DagonTask` factory creates task instances. A local
batch task executes a shell command on the same machine.

## Code

Create `lesson_01.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson01")
    task = DagonTask(TaskType.BATCH, "hello", "echo 'hello from DAGonStar' > hello.txt")

    workflow.add_task(task)
    workflow.make_dependencies()
    workflow.run()
```

## Run

```bash
cp dagon.ini.sample dagon.ini
python lesson_01.py
```

## Expected behavior

DAGonStar creates a scratch directory under the configured
`scratch_dir_base`, executes the task, and writes `hello.txt` in that task
directory.

## Verify

```bash
find /tmp -maxdepth 1 -type d -name '*-hello' | tail -n 1
```

Then inspect the printed directory:

```bash
ls /tmp/*-hello
```

To print the content of the latest execution:
```bash
cat $(find /tmp -maxdepth 1 -type d -name '*-hello' | tail -n 1)/hello.txt
```

## Scientific practice note

Even a one-task workflow is useful when the task has scientific meaning, such as
downloading observations or generating a reproducible input dataset.
