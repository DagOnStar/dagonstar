# The `workflow://` Schema

This document defines the DAGonStar workflow schema.

## Purpose

The `workflow://` schema is DAGonStar's mechanism for expressing file-level
dependencies between tasks. It lets a command refer to a file produced by another
task. DAGonStar then infers the dependency and stages the file before the
consumer task runs.

## Formal shape

```text
workflow://<workflow-name>/<task-name>/<path-inside-task-working-directory>
```

For same-workflow references, `<workflow-name>` may be omitted:

```text
workflow:///<task-name>/<path-inside-task-working-directory>
```

Examples:

```text
workflow:///A/output/f1.txt
workflow://Forecast/preprocess/out/forcing.nc
workflow://Observations/download/data/profile.csv
```

## Components

### Scheme

```text
workflow://
```

The scheme is defined in the implementation as:

```python
Workflow.SCHEMA = "workflow://"
```

### Workflow name

The workflow name identifies the producer workflow. It is optional for references
inside the current workflow.

Same workflow:

```text
workflow:///producer/output.dat
```

Named workflow:

```text
workflow://OtherWorkflow/producer/output.dat
```

### Task name

The task name is the producer task's `name` attribute.

```text
workflow:///prepare/input.nc
```

Here, `prepare` is the task name.

### Path

The remaining path is interpreted relative to the producer task's working
directory.

```text
workflow:///prepare/output/result.nc
```

This means:

```text
<prepare working directory>/output/result.nc
```

## Dependency inference

When `Workflow.make_dependencies()` is called, each task runs `pre_run()`.
`pre_run()` scans the command string for `workflow://` occurrences. For each
reference:

1. it parses workflow name, task name, and file path;
2. it finds the producer task;
3. it appends the consumer to the producer's `nexts`;
4. it appends the producer to the consumer's `prevs`;
5. it increments the producer's reference count.

Therefore, this command:

```python
DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/f1.txt")
```

creates:

```text
A -> B
```

## Command rewriting

Before execution, `Task.pre_process_command()` stages referenced files and
rewrites the command body. The producer reference is replaced by a path inside
the consumer task's working directory, under:

```text
.dagon/inputs/<workflow-name>/<task-name>/...
```

This lets the external program read a normal filesystem path.

## Whitespace boundary rule

The current parser scans from `workflow://` until the next space character or
the end of the command string. This means paths with spaces are not safely
supported in `workflow://` references.

Recommended:

```text
workflow:///A/output/result.nc
```

Avoid:

```text
workflow:///A/output/result with spaces.nc
```

## Same-workflow examples

Producer:

```python
task_a = DagonTask(TaskType.BATCH, "A", "mkdir -p output; echo data > output/f1.txt")
```

Consumer:

```python
task_b = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/f1.txt > copy.txt")
```

## Cross-workflow examples

```python
task = DagonTask(
    TaskType.BATCH,
    "run_model",
    "cat workflow://Observations/collect/out/forcing.txt > model_input.txt",
)
```

Cross-workflow behavior is used by meta-workflow/transversal examples and may
involve `DAG_TPS` or the optional DAGon service.

## Schema and data staging

The schema identifies what data must be staged. The staging method is controlled
by the workflow or task data mover:

- `DataMover.COPY`
- `DataMover.LINK`
- `DataMover.SCP`
- `DataMover.GRIDFTP`
- `DataMover.SKYCDS`

For local workflows, `COPY` is the safest default. Specialized movers require
external services or remote configuration.

## Best practices

- Use stable task names.
- Use simple path names without spaces.
- Write producer outputs under explicit directories such as `output/`.
- Reference exact files rather than broad directory assumptions where possible.
- Call `workflow.make_dependencies()` before `workflow.run()`.
- Keep cross-workflow references rare and well documented.

## Common errors

### Missing producer task

If a referenced task is not found and the DAGon service is disabled, DAGonStar
raises a connection/service-related error because it cannot resolve the
reference externally.

### Dependency cycle

If `workflow://` references create a cycle, validation fails.

### Wrong path inside producer task

The dependency may be valid, but staging or downstream execution fails if the
producer did not create the referenced file.

### Path contains spaces

The current parser uses spaces as token boundaries. Avoid spaces in paths used
inside `workflow://` references.
