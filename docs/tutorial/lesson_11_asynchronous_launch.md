# Lesson 11: Launch a Workflow Asynchronously

## Objective

Start a workflow without blocking the main Python thread, observe its lifecycle,
and wait for completion only when needed.

## Concept

`Workflow.launch()` runs the same workflow execution path as `run()`, but in a
background thread. `Workflow.wait()` joins that thread. Event hooks let an
application report task and workflow progress without polling task status.

## Code

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("Lesson11")
workflow.add_task(DagonTask(TaskType.BATCH, "hello", "echo hello"))

workflow.on_task_start += lambda task: print("starting", task.name)
workflow.on_task_end += lambda task: print("ended", task.name, task.status.name)
workflow.on_workflow_end += lambda wf: print("workflow complete")

workflow.launch()
print("The caller is free to do other work.")
workflow.wait()
```

## Run

```bash
cp dagon.ini.sample dagon.ini
python3 lesson_11.py
```

## Expected behavior

The line from the caller can print while the workflow is executing. `wait()`
then blocks until the task and workflow-end callbacks have run. Dependencies are
discovered automatically by `launch()`; calling `make_dependencies()` yourself
remains useful when you want to inspect or validate the graph before launch.

## Verify

Run the repository example:

```bash
python3 examples/async/asynchronous_launch.py
```

## Scientific practice note

Asynchronous launch is useful for notebook interfaces, web services, and
experiment controllers that need to remain responsive while workflows run.
Event callbacks should report progress or update state quickly; expensive work
in a callback delays the workflow thread.
