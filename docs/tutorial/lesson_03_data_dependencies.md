# Lesson 03: Use `workflow://` Data Dependencies

> Colab compatibility: supported. `workflow://` references work for files created in the Colab runtime.

## Run in Google Colab

Copy the lesson's **Code** into `lesson_03.py` with a `%%writefile
lesson_03.py` cell, then execute it after this setup:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!cp dagon.ini.sample dagon.ini
!python3 lesson_03.py
```

`workflow://` paths refer to files created inside the current Colab runtime.

## Objective

Let DAGonStar infer dependencies from data references.

## Concept

`workflow:///task/path` references a file inside another task's scratch
directory. `Workflow.make_dependencies()` parses this reference and creates the
dependency.

## Code

Create `lesson_03.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson03")

    observations = DagonTask(
        TaskType.BATCH,
        "observations",
        "mkdir -p data; printf 'time,value\\n0,12.5\\n1,13.1\\n' > data/series.csv",
    )

    statistics = DagonTask(
        TaskType.BATCH,
        "statistics",
        "wc -l workflow:///observations/data/series.csv > line_count.txt",
    )

    workflow.add_task(observations)
    workflow.add_task(statistics)
    workflow.make_dependencies()
    workflow.run()
```

## Run

```bash
python lesson_03.py
```

## Expected behavior

`statistics` waits for `observations`. DAGonStar stages `series.csv` into the
consumer task and rewrites the command to use the local staged path.

## Verify

```bash
find /tmp -maxdepth 1 -type d -name '*-statistics' | tail -n 1
```

Inspect `line_count.txt` in the resulting directory.

## Scientific practice note

Dataflow references make scientific provenance easier to read: an edge exists
because a named data product is consumed.
