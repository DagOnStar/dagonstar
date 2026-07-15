# User Guide

## FAIR metadata and provenance

Enable `FairProfile` on a workflow and use task `declare_outputs(Artifact(...))`
or `declare_inputs()` for intentional data metadata. The recorder writes local
RO-Crate, PROV, DataCite, CodeMeta, SHA-256 and human-readable reports. See the
[FAIR principles](fair_principles.md) and [FAIR tutorial](tutorial/lesson_15_fair_by_design.md)
for the implemented model and a runnable example.
This guide explains how to author DAGonStar workflows for scientific computing.

## Basic workflow structure

Every workflow has the same core structure:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("Experiment")

task = DagonTask(TaskType.BATCH, "task", "echo hello")
workflow.add_task(task)

workflow.make_dependencies()
workflow.run()
```

To exchange the command graph with CWL-aware tools, call
`workflow.saveAsCWL("workflow.cwl")`. See [Exporting workflows to CWL](cwl_export.md)
for validation instructions and the portability boundary.

Use the `if __name__ == "__main__":` guard in scripts that may be imported by
tests or other tools.

## Naming tasks

Task names are used in:

- dependency references;
- scratch directory names;
- JSON serialization;
- checkpoint keys;
- service registration.

Use stable, concise names:

```python
download_observations
run_model
postprocess
publish
```

Avoid spaces and shell-sensitive characters in task names.

## Explicit dependencies

Use explicit dependencies when the scientific relation is logical rather than
file-based:

```python
quality_control.add_dependency_to(download)
simulation.add_dependency_to(quality_control)
```

Read this as: `quality_control` depends on `download`.

## Dataflow dependencies

Use `workflow://` when a task consumes a file from another task:

```python
simulation = DagonTask(
    TaskType.BATCH,
    "simulation",
    "python run.py --forcing workflow:///prepare/forcing.nc",
)
```

Call:

```python
workflow.make_dependencies()
```

DAGonStar will infer that `simulation` depends on `prepare`.

For a full definition of this syntax, see
[The `workflow://` Schema](the_workflow_schema.md).

## Local batch tasks

Local batch tasks are the most portable starting point:

```python
DagonTask(TaskType.BATCH, "hostname", "hostname > host.txt")
```

The command is included in a generated Bash launcher script. Standard output is
also piped into `.dagon/stdout.txt`.

## Remote tasks

Passing `ip`, `ssh_username`, and optionally `keypath` selects a remote batch
task:

```python
DagonTask(
    TaskType.BATCH,
    "remote_hostname",
    "hostname > host.txt",
    ip="192.0.2.10",
    ssh_username="researcher",
    keypath="/home/researcher/.ssh/id_rsa",
)
```

Before using remote tasks, verify SSH manually:

```bash
ssh -i /path/to/key researcher@192.0.2.10 hostname
```

DAGonStar verifies SSH host keys from the normal user/system `known_hosts`
files and rejects unknown or changed keys. On first use, verify the host-key
fingerprint through a trusted channel and enroll it with a normal interactive
`ssh` connection (or your site's managed `known_hosts` deployment). Do not
disable host-key checking to make an unattended workflow connect.

## Slurm tasks

Use Slurm tasks for scheduler-managed HPC jobs:

```python
DagonTask(
    TaskType.SLURM,
    "hpc_model",
    "./run_model.sh",
    partition="compute",
    ntasks=32,
    memory=64000,
    time="06:00:00",
)
```

The implementation generates an `sbatch` command. Confirm that `sbatch` is
available and that the partition/resource values are valid on the target system.

## Docker tasks

Docker tasks run commands inside a container:

```python
DagonTask(
    TaskType.DOCKER,
    "python_version",
    "python --version",
    image="python:3.12-slim",
)
```

The Docker SDK must be able to connect to the Docker daemon.

## LLM tasks

`TaskType.LLM` sends a JSON Chat Completions request to a configured
OpenAI-compatible provider. Prompt strings support named parameters, and
`input_files` maps those parameters to UTF-8 text files referenced with
`workflow://`.

```python
DagonTask(
    TaskType.LLM,
    "summarize",
    {"messages": [{"role": "user", "content": "Summarize {report}"}]},
    provider="research",
    input_files={"report": "workflow:///prepare/output/report.txt"},
)
```

Configure `[llm.research]` locally with an endpoint, model, and `api_key_env`.
The response is saved as `response.json` in the task directory. Use the
[local mock example](../examples/llm/local_mock_llm.py) or [Lesson 12](tutorial/lesson_12_llm_tasks.md)
before connecting a real provider.

## Data movement

Set the workflow default data mover:

```python
from dagon import DataMover

workflow.set_data_mover(DataMover.COPY)
```

For local workflows, `COPY` is the safest default. `LINK` may be faster but
creates symbolic links rather than independent file copies. `SCP`, `GRIDFTP`,
and `SKYCDS` require external services.

## Checkpoints

Create a workflow with a checkpoint file:

```python
workflow = Workflow("Experiment", checkpoint_file="checkpoint.json")
```

Resume:

```python
workflow.run(resume_checkpoint_file="checkpoint.json")
```

Checkpoint behavior depends on stable task names and preserved task working
directories.

For detailed semantics and limitations, see [Checkpoints](checkpoints.md).

## Dry runs

Set:

```python
workflow.set_dry(True)
```

Dry mode prevents task execution after launcher generation. It is useful when
inspecting dependency resolution and generated scripts.

## Recommended workflow design

For scientific workflows:

1. Separate preparation, simulation, post-processing, and publication tasks.
2. Make intermediate scientific products explicit files.
3. Prefer dataflow dependencies for file products.
4. Keep commands deterministic when possible.
5. Record external software versions.
6. Use container images or environment modules for reproducible environments.
7. Add unit tests for dependency structure when developing reusable workflows.

## Common mistakes

- Calling `make_dependencies()` is optional before `workflow.run()` or
  `workflow.launch()`: both build dependencies automatically when needed. Call
  it explicitly when you want to inspect or validate the graph before running.
- Referencing a task name that does not exist.
- Creating a dependency cycle.
- Using remote tasks before SSH is verified.
- Committing secrets in `dagon.ini`.
- Assuming Docker, Slurm, Globus, or cloud credentials are available in CI.
