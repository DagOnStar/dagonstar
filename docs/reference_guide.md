# Reference Guide

## FAIR API

`Workflow.enable_fair(profile)` registers and returns a `FairRecorder`.
`FairProfile` defines title, description, creators (`Agent`), license, keywords,
`AccessPolicy`, strict validation and an optional output directory. `Artifact`
describes a path and optional type, license, identifier, and semantic metadata.
Tasks expose chainable `declare_inputs(*artifacts)`, `declare_outputs(*artifacts)`
and `annotate(**metadata)` methods; they remain inert without FAIR mode.
For export semantics, validation, and safety constraints, see
[FAIR by Design](fair_principles.md).
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
- `TaskType.KUBERNETES`
- `TaskType.APPTAINER`
- `TaskType.NOMAD`
- `TaskType.LLM`
- `TaskType.NATIVE`
- `TaskType.WEB`

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
| `KUBERNETES` | `dagon.kubernetes_task` | `KubernetesTask` |
| `APPTAINER` | `dagon.apptainer_task` | `ApptainerTask` |
| `NOMAD` | `dagon.nomad_task` | `NomadTask` |
| `LLM` | `dagon.llm` | `LLMTask` |
| `NATIVE` | `dagon.native` | `NativeTask` |
| `WEB` | `dagon.web` | `WebTask` |
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

## LLM tasks

`LLMTask` invokes an OpenAI-compatible Chat Completions endpoint without an
additional SDK. Its constructor is:

```python
DagonTask(TaskType.LLM, name, prompt, provider, params=None, input_files=None,
          working_dir=None, output_file="response.json", timeout=120)
```

`prompt` is a JSON object (or a JSON string) containing `messages`; string
values may use `{parameter}` placeholders from `params` or `input_files`.
Provider configuration is read from `[llm.<provider>]`. `input_files` maps
parameter names to `workflow://` references, which infer dependencies and stage
local UTF-8 text before the request. See [LLM Tasks](llm_tasks.md) and the
[local example](../examples/llm/local_mock_llm.py).

## Native tasks

`NativeTask` executes an importable `module:function` through a JSON runner:

```python
DagonTask(TaskType.NATIVE, name, function, inputs=None, outputs=None,
          executor="local", resources=None, python=sys.executable,
          working_dir=None, environment=None)
```

Inputs may be JSON scalars, existing local files, or `workflow://` file references. File values are staged below `inputs/`; `outputs` maps parameter names to safe relative paths below `outputs/`. JSON return metadata is written to `.dagon/native_result.json`. `executor` accepts `local` and `slurm`; use existing Slurm settings in `resources`. Functions must be importable module-level callables.

Lambdas and nested functions are not supported because a native task is run in a
separate Python process and needs a stable `module:function` import target.
`environment` supplies string environment variables to that runner, while
`python` selects its interpreter. Dependencies are not installed automatically:
install them, along with DAGonStar, into the selected environment before running
the workflow. See [Native Tasks](native_tasks.md) for complete regular-function,
lambda-replacement, dependency, and Slurm examples.

## Web tasks

`WebTask` represents one JSON-serializable HTTP/HTTPS request. It is created
through `DagonTask` and executes in the task scratch directory:

```python
DagonTask(
    TaskType.WEB,
    name,
    {"method": "GET", "url": "https://example.org", "outputs": {"body": "response.json"}},
    executor="local",
)
```

Supported methods are `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and `HEAD`.
Specifications support `query`, `headers`, `json`, `data`, `multipart`, `auth`,
`timeout`, retry settings, expected status codes, and `outputs`. `GET`, `HEAD`,
`PUT`, and `DELETE` may retry; retries for `POST` or `PATCH` require explicit
`"retry_unsafe": True` in the specification.

Recursive `workflow://` values infer dependencies; referenced files are copied
below `inputs/`. The special values `{"text": "workflow://..."}` and
`{"json_file": "workflow://..."}` load a staged UTF-8 text or JSON file into
the request. Declared body output is raw response bytes, while headers and
metadata outputs are JSON, all at safe relative paths below `outputs/`.
`.dagon/web_result.json` records non-secret status metadata.

Supported authentication is bearer, basic, API-key header, or API-key query,
always by environment-variable name rather than literal secrets. The task
accepts `executor="local"` (default) or `executor="slurm"`; the latter accepts
existing scheduler options in `resources`. See [Web Tasks](web_tasks.md) for
the complete field reference, authentication shapes, request examples, retry
semantics, and scratch-artifact behavior.

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
[The `workflow://` Schema](the_workflow_schema.md). In brief:

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
