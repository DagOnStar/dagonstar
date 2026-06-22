# Lesson 02: Add Explicit Task Dependencies

> Colab compatibility: supported. Runs as local batch tasks in hosted Colab.

## Run in Google Colab

Clone and install DAGonStar, copy the lesson's **Code** into a cell beginning
with `%%writefile lesson_02.py`, then run:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!cp dagon.ini.sample dagon.ini
!python3 lesson_02.py
```

## Objective

Create a workflow where tasks execute in a controlled order.

## Concept

Use `consumer.add_dependency_to(producer)` when one task must wait for another.

## Code

Create `lesson_02.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson02")

    prepare = DagonTask(TaskType.BATCH, "prepare", "echo prepared > prepared.txt")
    simulate = DagonTask(TaskType.BATCH, "simulate", "echo simulated > simulated.txt")
    summarize = DagonTask(TaskType.BATCH, "summarize", "echo summarized > summarized.txt")

    workflow.add_task(prepare)
    workflow.add_task(simulate)
    workflow.add_task(summarize)

    simulate.add_dependency_to(prepare)
    summarize.add_dependency_to(simulate)

    workflow.Validate_WF()
    workflow.run()
```

## Run

```bash
python lesson_02.py
```

## Expected behavior

The three tasks run in the order:

```text
prepare -> simulate -> summarize
```

## Verify

```bash
find /tmp -maxdepth 1 -type d \( -name '*-prepare' -o -name '*-simulate' -o -name '*-summarize' \)
```

## Scientific practice note

Explicit dependencies are best when the relation is conceptual or procedural,
for example: "validate parameters before launching the model."
