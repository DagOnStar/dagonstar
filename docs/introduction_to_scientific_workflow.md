# Introduction to Scientific Workflows

Scientific workflows are explicit, reproducible descriptions of computational
experiments. They connect data, software, execution environments, and provenance
into a structure that can be inspected, repeated, adapted, and shared.

DAGonStar approaches this problem with a deliberately small abstraction: a
workflow is a directed acyclic graph (DAG) of tasks, and each task is a Python
object that executes a command in a particular environment.

## Why workflows matter in computational science

Modern computational science often combines many heterogeneous activities:

- preprocessing observational data;
- running models or simulations;
- staging intermediate files between machines;
- executing tools on HPC clusters or cloud instances;
- post-processing model products;
- publishing scientific outputs;
- preserving sufficient context to reproduce a result.

If these steps remain implicit in shell history, personal notebooks, or site
specific scripts, the experiment is difficult to audit. Workflow systems make the
structure explicit.

The main scientific benefits are:

- **Reproducibility**: the sequence of computations is encoded as source code.
- **Traceability**: inputs, outputs, and task dependencies are visible.
- **Portability**: the same workflow structure can target different execution
  backends.
- **Parallelism**: independent tasks can run concurrently when resources permit.
- **Recoverability**: checkpointing can avoid recomputing finished work.

## Directed acyclic graphs

A DAG contains nodes and directed edges. In scientific workflow terminology:

- a **node** is a computational task;
- an **edge** means that one task depends on another;
- **acyclic** means the graph has no circular dependency.

DAGonStar validates the workflow graph before execution when dependencies are
constructed through `Workflow.make_dependencies()` or when `Workflow.Validate_WF()`
is called directly. A cycle is a modeling error: no task in the cycle can be
scheduled first without violating a dependency.

## Task-oriented and data-oriented workflows

DAGonStar supports two complementary ways of describing a workflow.

In a **task-oriented workflow**, dependencies are explicit:

```python
task_b.add_dependency_to(task_a)
```

This states that `task_b` must wait for `task_a`.

In a **data-oriented workflow**, dependencies are inferred from the command text
using the `workflow://` schema:

```python
task_b = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/result.txt")
```

When `Workflow.make_dependencies()` is called, DAGonStar finds the reference to
task `A`, records the dependency, and later stages the referenced file into the
consumer task workspace.

The data-oriented style is especially natural for scientific pipelines because
dependency edges follow the data products being consumed.

## DAGonStar's computational model

The current implementation centers on these concepts:

- `Workflow`: container and scheduler for tasks.
- `DagonTask`: factory that creates a concrete task implementation from a
  `TaskType`.
- `Task`: base class for threaded task execution and dependency handling.
- `Batch`: local shell task.
- `Slurm`: task submitted through `sbatch`.
- `RemoteTask`: task executed through SSH.
- `DockerTask`: task executed in a Docker container.
- `CloudTask`: task associated with an Apache Libcloud cloud node.
- `Stager`: component that generates or invokes data movement between tasks.

The workflow engine runs tasks as Python threads. Each task waits for its
predecessors, prepares its scratch directory, resolves data references, executes
its launcher script, updates status, and releases dependent tasks.

## The role of scratch directories

Scientific workflows frequently produce many intermediate files. DAGonStar gives
each task a working directory, also called a scratch directory. The base path is
configured with:

```ini
[batch]
scratch_dir_base=/tmp/
```

If a task has no explicit `working_dir`, DAGonStar creates one from the workflow
base and a timestamped task name. Each task also receives an internal `.dagon`
directory containing launcher scripts and execution metadata.

## Workflow schema

The `workflow://` schema is central to DAGonStar's dataflow mode. The general
form is:

```text
workflow://<workflow-name>/<task-name>/<path-inside-task-scratch>
```

For references inside the same workflow, the workflow name may be omitted:

```text
workflow:///A/output/result.txt
```

The implementation resolves this as:

- current workflow name;
- task `A`;
- file `output/result.txt` inside task `A`'s scratch directory.

## Execution backends

DAGonStar's public task types are defined in `dagon.task.TaskType`:

- `BATCH`
- `SLURM`
- `CLOUD`
- `DOCKER`
- `LLM`
- `NATIVE`
- `WEB`
- `CHECKPOINT`

Remote variants are selected by keyword arguments. For example, a batch task
with `ip=...` becomes a remote batch task.

This design keeps workflow code compact while preserving access to several
execution environments. It also means that optional integrations may require
site-specific services such as SSH, Docker, Slurm, Globus, or cloud provider
credentials.

`LLM` tasks call configured OpenAI-compatible Chat Completions providers and
can consume local UTF-8 producer files with `workflow://`; see [LLM Tasks](llm_tasks.md).

## Documentation map

- [Getting Started](getting_started.md): installation and first local workflow.
- [Configuration](configuration.md): complete configuration model.
- [Architecture](architecture.md): implementation structure and execution flow.
- [User Guide](user_guide.md): practical workflow authoring guidance.
- [Reference Guide](reference_guide.md): API-oriented reference.
- [Developer Guide](developer_guide.md): testing, maintenance, and contribution.
- [Tutorials](tutorial/README.md): fourteen incremental lessons.
