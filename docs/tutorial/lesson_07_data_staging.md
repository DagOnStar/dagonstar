# Lesson 07: Choose Data Staging Modes

## Objective

Control how DAGonStar stages files between tasks.

## Concept

The workflow default data mover is set with `workflow.set_data_mover(...)`.
Local workflows commonly use `DataMover.COPY` or `DataMover.LINK`.

## Code

Create `lesson_07.py`:

```python
from dagon import DataMover, Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson07")
    workflow.set_data_mover(DataMover.COPY)

    source = DagonTask(TaskType.BATCH, "source", "mkdir -p out; echo sample > out/data.txt")
    sink = DagonTask(TaskType.BATCH, "sink", "cat workflow:///source/out/data.txt > copied.txt")

    workflow.add_task(source)
    workflow.add_task(sink)
    workflow.make_dependencies()
    workflow.run()
```

## Run

```bash
python lesson_07.py
```

## Verify

```bash
DIR=$(find /tmp -maxdepth 1 -type d -name '*-sink' | tail -n 1)
sed -n '1,80p' "$DIR/copied.txt"
```

## Expected behavior

The sink task receives a copy of the source file and writes `copied.txt`.

## Experiment

Change:

```python
workflow.set_data_mover(DataMover.LINK)
```

Run again and inspect the generated launcher script to observe the staging
command difference.

## Scientific practice note

`COPY` is often better for archival reproducibility because downstream tasks get
their own materialized inputs. `LINK` can reduce storage and I/O cost when
intermediate files remain stable.
