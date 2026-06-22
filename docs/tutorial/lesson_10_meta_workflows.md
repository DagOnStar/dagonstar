# Lesson 10: Compose Meta-Workflows

> Colab compatibility: supported for local workflows. Remote backends retain their own requirements.

## Run in Google Colab

For the local workflow version, copy the **Code** into a cell beginning with
`%%writefile lesson_10.py`, then run:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!cp dagon.ini.sample dagon.ini
!python3 lesson_10.py
```

## Objective

Coordinate more than one workflow and use transversal references.

## Concept

`DAG_TPS` coordinates a set of workflows. A task in one workflow can reference a
task in another workflow with:

```text
workflow://OtherWorkflow/task/path
```

## Code

Create `lesson_10.py`:

```python
from dagon import Workflow
from dagon.dag_tps import DAG_TPS
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    observations = Workflow("Observations")
    model = Workflow("Model")

    collect = DagonTask(
        TaskType.BATCH,
        "collect",
        "mkdir -p out; echo 'forcing' > out/forcing.txt",
    )

    run_model = DagonTask(
        TaskType.BATCH,
        "run_model",
        "cat workflow://Observations/collect/out/forcing.txt > model_output.txt",
    )

    observations.add_task(collect)
    model.add_task(run_model)

    meta = DAG_TPS("Lesson10")
    meta.add_workflow(observations)
    meta.add_workflow(model)
    meta.make_dependencies()
    meta.run()
```

## Run

```bash
python lesson_10.py
```

## Expected behavior

The model workflow waits for the observations workflow task that produces
`forcing.txt`.

## Verify

```bash
DIR=$(find /tmp -maxdepth 1 -type d -name '*-run_model' | tail -n 1)
sed -n '1,80p' "$DIR/model_output.txt"
```

If this legacy path behaves differently in your environment, first verify
construction without execution:

```python
print(meta.as_json())
```

Then inspect the dependency graph with `task.prevs` and `task.nexts`. The
meta-workflow implementation is powerful but less covered by automated tests
than local single-workflow behavior, so production use should be validated with
site-specific examples.

## Scientific practice note

Meta-workflows are useful when a research system has separable but connected
pipelines, such as observations, model execution, validation, and dissemination.
