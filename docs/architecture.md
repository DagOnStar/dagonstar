# Architecture

This document describes the current DAGonStar implementation. It is descriptive,
not aspirational: documentation must remain consistent with the software in this
repository.

## Package layout

```text
dagon/
  __init__.py                 Workflow, Status, DataMover, Stager
  task.py                     TaskType, DagonTask, Task base class
  batch.py                    Batch, RemoteBatch, Slurm, RemoteSlurm
  remote.py                   RemoteTask, CloudTask
  docker_task.py              DockerTask, DockerRemoteTask
  checkpoint.py               Checkpoint tasks
  config.py                   INI configuration reader
  dag_tps.py                  Meta-workflow coordination
  api/                        HTTP client and workflow service
  cloud/                      Apache Libcloud helpers
  communication/              SSH, SCP, Globus, SKYCDS helpers
  ftp_publisher/              FTP publishing helper
  peer2peer/                  Experimental peer-to-peer service functions
```

## Main abstractions

### `Workflow`

`dagon.Workflow` owns a list of tasks and coordinates dependency construction,
execution, checkpoint state, configuration, and optional service registration.

Important methods:

- `add_task(task)`
- `make_dependencies()`
- `run(resume_checkpoint_file=None)`
- `launch(resume_checkpoint_file=None)` and `wait(timeout=None)` for
  background execution; lifecycle hooks are described in
  [Asynchronous Workflow Launch](asynch_launch.md).
- `as_json()`
- `find_task_by_name(workflow_name, task_name)`
- `Validate_WF()`
- `set_data_mover(data_mover)`
- `set_stager_mover(stager_mover)`

### `DagonTask`

`DagonTask` is a factory. It receives a `TaskType` and returns an instance of
the concrete task class mapped in `dagon.task.tasks_types`.

```python
task = DagonTask(TaskType.BATCH, "A", "echo A")
```

### `Task`

`Task` extends `threading.Thread`. It provides:

- task status;
- predecessor and successor lists;
- workflow reference;
- scratch-directory creation;
- `workflow://` parsing;
- launcher script generation;
- reference counting and garbage collection hooks;
- checkpoint interaction.

Concrete task classes override `on_execute()` and related environment-specific
behavior.

## Execution lifecycle

A typical dataflow run follows this sequence:

1. User creates a `Workflow`.
2. User creates tasks through `DagonTask`.
3. User adds tasks with `workflow.add_task()`.
4. User calls `workflow.make_dependencies()`.
5. Each task parses its command for `workflow://` references.
6. Dependencies are recorded in `prevs` and `nexts`.
7. `Workflow.Validate_WF()` rejects cycles.
8. User calls `workflow.run()`.
9. Tasks are started as Python threads.
10. Each task waits for predecessor completion.
11. Each task creates or reuses a scratch directory.
12. Input data is staged.
13. The task launcher script is executed.
14. Status and checkpoint metadata are updated.
15. Dependent tasks proceed.

## Status model

`dagon.Status` has these values:

- `READY`
- `WAITING`
- `RUNNING`
- `FINISHED`
- `FAILED`

Status changes are local and, if the DAGon service is enabled, propagated
through the service API.

## Dependency model

Each task has:

- `prevs`: tasks that must finish before this task can run;
- `nexts`: tasks that depend on this task;
- `reference_count`: number of downstream data references.

Explicit dependencies are created with:

```python
consumer.add_dependency_to(producer)
```

Implicit dependencies are created by parsing:

```text
workflow:///producer/path/to/file
```

## Data staging

`Stager.stage_in()` chooses a data movement strategy. The implemented
`DataMover` enum includes:

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

The currently exercised local paths are primarily `COPY` and `LINK`; remote and
specialized paths require external services and site configuration.

`StagerMover` controls staging mode:

- `NORMAL`
- `PARALLEL`
- `SLURM`

## Execution backends

### Batch

`Batch` executes generated launcher scripts locally through `subprocess.Popen`.

### Remote batch

When a batch task is constructed with `ip=...`, `Batch.__new__` returns
`RemoteBatch`, which uses `SSHManager`.

### Slurm

`Slurm` generates an `sbatch` command using optional parameters such as
partition, task count, memory, wall time, nodes, and tasks per node.

### Docker

`DockerTask` creates or uses a Docker container through the Docker Python SDK.
The task command is wrapped inside `docker exec`.

### Cloud

`CloudTask` extends remote execution with Apache Libcloud-backed instance
management.

### Checkpoint

Checkpoint tasks preserve task working directories and checkpoint metadata. The
base workflow can also resume from a checkpoint file.

## Service architecture

The optional `dagon.api` package contains:

- `API`: client used by workflows to register and update remote service state.
- `WorkflowServer`: Flask-based server wrapper for workflow operations.

The default documented path disables this service:

```ini
[dagon_service]
use = False
```

## Known architectural constraints

- Tasks are Python threads, not isolated processes.
- Some command strings are still assembled by concatenation; shell-command
  safety and path quoting remain active improvement priorities. New staging
  helpers quote generated staging paths.
- Optional integrations are exposed through package extras for Docker, cloud,
  Globus, and API dependencies. Preserve lazy imports so core imports do not
  require those integrations.
- The repository has an initial unit test and CI baseline, but comprehensive
  workflow, checkpoint, staging, and integration coverage is still being
  expanded.
- Public APIs now have broader annotations across workflow, task,
  configuration, staging, task-subclass, and API-client code; stricter static
  checking remains a maintainability improvement.
- Some examples depend on external systems and cannot be verified in generic CI.
