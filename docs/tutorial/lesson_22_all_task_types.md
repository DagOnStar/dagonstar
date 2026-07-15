# Lesson 22: combine all task types safely

> Colab compatibility: structural support for every type; local execution for
> Batch, Native, local-mock LLM/Web/FaaS, FAIR, checkpoints, and CWL. External
> backends require their actual service and credentials.

## Objective

Build workflows in which any task type can produce data for any other task
type, and distinguish portable workflow behavior from backend availability.

All task types participate in the same graph. Use
`workflow:///producer/path` in shell commands or structured inputs. DAGonStar
discovers the dependency before execution, stages the artifact, and records the
edge in enabled FAIR provenance.

```python
from dagon.task import TaskType

assert {item.value for item in TaskType} == {
    "checkpoint", "batch", "slurm", "cloud", "docker", "kubernetes",
    "apptainer", "nomad", "llm", "native", "web", "faas",
}
```

Command-oriented types (`CHECKPOINT`, `BATCH`, `SLURM`, `CLOUD`, `DOCKER`,
`KUBERNETES`, `APPTAINER`, and `NOMAD`) accept `workflow://` in their command.
Structured types accept it in LLM prompts/input files, Native bindings, Web
request specifications, and nested FaaS inputs.

## Notebook exercise

Create the workflow with `portable_emulation=True`; this retains every original
task type while executing its credential-free local semantics.

Run the credential-free contract test:

```python
!python3 -m unittest tests.test_tasktype_interoperability -v
```

It constructs and executes a single workflow containing every `TaskType`, without opening
external connections, and verifies dependencies, FAIR declarations, checkpoint
reuse, and runnable CWL export. This is safe in Jupyter and Colab after cloning
the repository and installing `.[all]`.

For live execution, configure each selected backend. A mixed workflow is
operable when those backends are reachable and the selected staging method can
connect every producer and consumer.

Give the workflow a durable `checkpoint_file`, preserve working directories,
and rerun with `resume_checkpoint_file`. Successful tasks of every type are
reused. In Colab, put scratch and checkpoints on mounted Drive if they must
survive a runtime reset.

See [the interoperability contract](../tasktype_interoperability.md) for the
backend matrix and security boundaries.
