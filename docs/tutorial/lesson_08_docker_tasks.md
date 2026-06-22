# Lesson 08: Run Docker-Backed Tasks

> Colab compatibility: not supported in hosted Colab. This lesson requires a Docker daemon.

## Objective

Run a task inside a Docker container.

## Concept

`TaskType.DOCKER` creates a `DockerTask`. The task uses the Docker Python SDK,
pulls or uses an image, starts a container, and runs the task command with
`docker exec`.

## Prerequisites

- Docker installed.
- Docker daemon running.
- Current user allowed to access Docker.

Verify:

```bash
docker info
```

## Code

Create `lesson_08.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("Lesson08")

    task = DagonTask(
        TaskType.DOCKER,
        "container_python",
        "python --version > python_version.txt",
        image="python:3.12-slim",
    )

    workflow.add_task(task)
    workflow.make_dependencies()
    workflow.run()
```

## Run

```bash
python lesson_08.py
```

## Verify

```bash
DIR=$(find /tmp -maxdepth 1 -type d -name '*-container_python' | tail -n 1)
sed -n '1,80p' "$DIR/python_version.txt"
```

## Expected behavior

The output file contains the Python version reported inside the container.

## Scientific practice note

Containers help preserve software environments. For published workflows, record
the exact image tag or digest used for scientific results.
