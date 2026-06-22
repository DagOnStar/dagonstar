# Lesson 05: Detect and Fix Dependency Cycles

## Objective

Learn how DAGonStar rejects invalid workflow graphs.

## Concept

A DAG cannot contain cycles. If `A` depends on `B` and `B` depends on `A`, no
valid execution order exists.

## Code

Create `lesson_05_cycle.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("Lesson05")

a = DagonTask(TaskType.BATCH, "A", "echo A")
b = DagonTask(TaskType.BATCH, "B", "echo B")

workflow.add_task(a)
workflow.add_task(b)

b.add_dependency_to(a)
a.add_dependency_to(b)

workflow.Validate_WF()
```

## Run

```bash
python lesson_05_cycle.py
```

## Expected behavior

The script raises an exception reporting a cycle.

## Fix

Remove one edge:

```python
b.add_dependency_to(a)
```

Then run:

```python
workflow.Validate_WF()
workflow.run()
```

## Scientific practice note

Cycle detection is not only a software constraint. It also catches ambiguous
scientific logic, such as attempting to calibrate a model using results that the
same model has not produced yet.
