# Docker Dataflow Examples

Source directory: [`examples/dataflow/docker`](../../examples/dataflow/docker)

## Files

- `dataflow-demo-docker.py`
- `dataflow-demo-docker-checkpointing.py`
- `dataflow-demo-docker-remote.py`
- `dataflow-demo-docker-remote-checkpoint.py`
- `README.md`

## Purpose

These examples show how DAGonStar tasks can run inside Docker containers while
retaining the same workflow and dataflow concepts used by local batch tasks.

## Concepts exercised

- `TaskType.DOCKER`
- Docker image selection
- existing versus newly created containers
- container volume mounting
- `workflow://` data references
- checkpointing with container-backed tasks
- remote Docker through SSH

## Prerequisites

- Docker Engine installed.
- Docker daemon running.
- User permission to access Docker.
- Required images available locally or pullable from a registry.

Verify:

```bash
docker info
docker ps
```

## Execution model

`DockerTask` uses the Docker Python SDK. It creates or obtains a container and
wraps the task command in `docker exec`. DAGonStar still creates task scratch
directories on the host and mounts the workflow scratch base into the container.

## New container example

The documented pattern is:

```python
taskA = DagonTask(
    TaskType.DOCKER,
    "A",
    "mkdir output; hostname > output/f1.txt",
    image="ubuntu:20.04",
)
```

## Existing container example

An existing container can be selected by ID:

```python
taskB = DagonTask(
    TaskType.DOCKER,
    "B",
    "cat workflow:///A/output/f1.txt",
    container_id="container-id",
)
```

Use:

```bash
docker ps
```

to find container IDs.

## Verification

```bash
cp dagon.ini.sample dagon.ini
cd examples/dataflow/docker
python dataflow-demo-docker.py
```

Checkpoint variant:

```bash
python dataflow-demo-docker-checkpointing.py
```

Remote Docker variants require SSH and a Docker daemon reachable on the remote
machine.

## Scientific interpretation

Docker examples are useful when an external scientific code has complex runtime
dependencies. A container image can preserve:

- compiler/runtime libraries;
- Python/R/Fortran/C/C++ dependencies;
- command-line tools;
- model versions.

For publication-quality reproducibility, record the image tag or digest.
