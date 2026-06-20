# Reference Guide

This guide summarizes the public API and important implementation classes in the
current repository.

## Import conventions

```python
from dagon import Workflow, DataMover, StagerMover
from dagon.task import DagonTask, TaskType
```

## `dagon.Workflow`

Constructor:

```python
Workflow(
    name,
    config=None,
    config_file="dagon.ini",
    max_threads=10,
    jsonload=None,
    checkpoint_file=None,
)
```

Parameters:

- `name`: workflow name.
- `config`: optional in-memory configuration dictionary.
- `config_file`: INI file path used when `config` is not provided.
- `max_threads`: semaphore size currently stored for task use.
- `jsonload`: JSON-like workflow object to load.
- `checkpoint_file`: file path for writing checkpoint metadata.

Selected methods:

- `add_task(task)`: add a task and attach it to this workflow.
- `make_dependencies()`: parse dataflow references and validate the graph.
- `run(resume_checkpoint_file=None)`: run tasks in the current thread.
- `launch(resume_checkpoint_file=None)`: run tasks in a background thread.
- `wait(timeout=None)`: wait for a launched workflow; returns whether it ended.
- `add_listener(event_name, callback)`: register a workflow or task lifecycle
  callback. See [asynchronous launch](asynch_launch.md) for events and hooks.
- `set_dry(dry)`: set dry-run flag.
- `get_dry()`: return dry-run flag.
- `set_data_mover(data_mover)`: set workflow default data mover.
- `get_data_mover()`: return workflow default data mover.
- `set_stager_mover(stager_mover)`: set workflow default staging mode.
- `get_scratch_dir_base()`: compute or return workflow scratch base.
- `find_task_by_name(workflow_name, task_name)`: locate a task.
- `as_json()`: serialize workflow metadata.
- `load_json(Json_data)`: load tasks from JSON-like data.
- `Validate_WF()`: reject cycles.

## `dagon.Status`

Task states:

- `Status.READY`
- `Status.WAITING`
- `Status.RUNNING`
- `Status.FINISHED`
- `Status.FAILED`

## `dagon.task.TaskType`

Factory task types:

- `TaskType.CHECKPOINT`
- `TaskType.BATCH`
- `TaskType.SLURM`
- `TaskType.CLOUD`
- `TaskType.DOCKER`

## `dagon.task.DagonTask`

Factory usage:

```python
task = DagonTask(TaskType.BATCH, "A", "echo A")
```

The concrete class is selected from `tasks_types`:

| Task type | Module | Class |
| --- | --- | --- |
| `CHECKPOINT` | `dagon.checkpoint` | `Checkpoint` |
| `BATCH` | `dagon.batch` | `Batch` |
| `CLOUD` | `dagon.remote` | `CloudTask` |
| `DOCKER` | `dagon.docker_task` | `DockerTask` |
| `SLURM` | `dagon.batch` | `Slurm` |

## `dagon.task.Task`

Base constructor:

```python
Task(name, command, working_dir=None, transversal_workflow=None, globusendpoint=None)
```

Important attributes:

- `name`
- `command`
- `working_dir`
- `nexts`
- `prevs`
- `reference_count`
- `workflow`
- `status`
- `data_mover`
- `stager_mover`
- `globusendpoint`

Important methods:

- `add_dependency_to(task)`
- `add_transversal_point(task)`
- `pre_run()`
- `pre_process_command(command)`
- `post_process_command(command)`
- `include_command(body)`
- `create_working_dir()`
- `execute()`
- `run()`
- `as_json()`
- `get_scratch_dir()`
- `get_endpoint()`
- `set_endpoint(globusendpoint)`
- `set_data_mover(data_mover)`
- `set_stager_mover(stager_mover)`

Subclasses are expected to implement or specialize command execution.

## Batch tasks

```python
DagonTask(TaskType.BATCH, "local", "hostname")
```

Remote batch is selected by passing SSH parameters:

```python
DagonTask(
    TaskType.BATCH,
    "remote",
    "hostname",
    ip="example.org",
    ssh_username="user",
    keypath="/path/to/key",
)
```

## Slurm tasks

```python
DagonTask(
    TaskType.SLURM,
    "simulation",
    "./run.sh",
    partition="compute",
    ntasks=4,
    memory=4096,
    time="01:00:00",
)
```

Supported constructor options include:

- `comment`
- `partition`
- `ntasks`
- `memory`
- `time`
- `nodes`
- `ntasks_per_node`
- `working_dir`
- `globusendpoint`

Remote Slurm is selected by passing `ip`.

## Docker tasks

```python
DagonTask(
    TaskType.DOCKER,
    "container-task",
    "python --version",
    image="python:3.12-slim",
)
```

Options include:

- `image`
- `container_id`
- `working_dir`
- `globusendpoint`
- `remove`
- `volume`

Remote Docker is selected by passing SSH information including `ip`.

## Cloud tasks

Cloud tasks are backed by `dagon.remote.CloudTask` and Apache Libcloud. They
require provider information, SSH user, key options, and either an existing
instance or instance flavor data. Cloud behavior is provider-specific and should
be tested in the target environment.

## Data movement enums

`DataMover`:

- `DONTMOVE`
- `LINK`
- `COPY`
- `SCP`
- `HTTP`
- `HTTPS`
- `FTP`
- `SFTP`
- `GRIDFTP`
- `SKYCDS`

`StagerMover`:

- `NORMAL`
- `PARALLEL`
- `SLURM`

## Configuration API

```python
from dagon.config import read_config

all_sections = read_config("dagon.ini")
batch = read_config("dagon.ini", "batch")
```

If a requested section does not exist, `read_config(..., section)` returns
`None`.

## Workflow schema

The `workflow://` schema is documented in detail in
[The `workflow://` Schema](the_workflow_schiema.md). In brief:

```text
workflow://<workflow-name>/<task-name>/<path-inside-task-working-directory>
workflow:///<task-name>/<path-inside-task-working-directory>
```

## Meta-workflows

`dagon.dag_tps.DAG_TPS` coordinates multiple workflows. Typical usage:

```python
from dagon.dag_tps import DAG_TPS

meta = DAG_TPS("ExperimentSet")
meta.add_workflow(workflow_a)
meta.add_workflow(workflow_b)
meta.make_dependencies()
meta.run()
```

This is useful for transversal workflows that reference data across workflow
boundaries.

The meta-workflow code is legacy-sensitive and less covered by automated tests
than local `Workflow` behavior. When using transversal workflows for production
science, verify the exact scenario with representative workflows and preserve the
verification command with the experiment record.

## Service API

`dagon.api.API` communicates with a DAGon service endpoint. It supports:

- `create_workflow(workflow)`
- `add_task(workflow_id, task)`
- `update_task_status(workflow_id, task, status)`
- `get_task(workflow_id, task)`
- `get_workflow_by_name(workflow_name)`
- `update_task(workflow_id, task, attribute, value)`
- `add_dependency(workflow_id, task, dependency)`

The service is optional and disabled in the default sample configuration.
