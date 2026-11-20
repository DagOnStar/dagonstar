# Exporting workflows to CWL

`Workflow.saveAsCWL(filename)` writes the current DAG as a self-contained
[Common Workflow Language (CWL) v1.2](https://www.commonwl.org/v1.2/) document.
The file uses JSON syntax, which is also valid CWL, so the base DAGonStar
installation does not require a YAML library.

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("cwl-example")
prepare = DagonTask(TaskType.BATCH, "prepare", "echo sample > sample.txt")
analyze = DagonTask(TaskType.BATCH, "analyze", "wc -c sample.txt")
workflow.add_task(prepare)
workflow.add_task(analyze)
analyze.add_dependency_to(prepare)

workflow.saveAsCWL("cwl-example.cwl")
```

The exporter discovers `workflow://` dependencies if
`make_dependencies()` has not already run and retains explicit dependencies.
It converts names to portable CWL identifiers and resolves collisions. Each
task becomes an embedded `CommandLineTool` executing `/bin/sh -c <command>`.
Boolean completion values connect steps and expose the completion state of
terminal tasks as workflow outputs. A Docker task with an image adds a
`DockerRequirement` hint.

## Validate or run the export

Install the CWL reference runner separately, then validate the document:

```bash
python -m pip install cwltool
cwltool --validate cwl-example.cwl
cwltool cwl-example.cwl
```

## Portability boundary

With `portable_emulation=True`, export is directly runnable: every step exposes
its working directory as a CWL `Directory`, `workflow://` values become CWL
input paths, infrastructure hints are suppressed, and service tasks use local
emulation. The all-type contract validates and executes this document with
`cwltool` when the reference runner is installed.

Without portable emulation, the following backend boundary applies.

The export describes commands and graph ordering; it is not a lossless
translation of every DAGonStar executor. CWL runs exported commands in its own
working directories. DAGonStar scratch management, checkpointing, remote SSH,
Slurm, cloud, Kubernetes, Nomad, service registration, and specialized staging
are not reproduced. BeeOND volumes (see [BeeOND](beeond.md)) and the common
[ad-hoc file-system resources](adhoc_filesystems.md) are DAGonStar
execution behavior and are not exported; streams between tasks are exported
in materialized form ([Streams](#streams)). A command that refers to
`$DAGON_BEEOND` needs that variable from the CWL runner's environment.
Scheduler-aware pre-staging (`pre_stage`, see
[Scheduler-aware pre-staging](scheduler_prestaging.md)) is a DAGonStar
scheduler policy. It is neither exported nor annotated, so the document is
identical whether or not it is enabled.

In particular, `workflow://` text in a command is retained verbatim. It creates
the correct step dependency in the exported graph, but a generic CWL runner
does not implement DAGonStar's URI staging. For a directly runnable portable
CWL export, write commands using paths available in the CWL working directory,
or adapt the exported document with explicit CWL `File`/`Directory` inputs and
outputs. Native, web, and LLM tasks are exported only when their task object
provides a non-empty shell command.

The mixed-task contract exports a graph containing every registered
`TaskType`. This verifies deterministic CWL graph representation, not execution
of backend-specific infrastructure by a generic CWL runner.

The exported file contains task commands and container image names. Review it
before sharing, and never place credentials in commands.

IoT tools invoke `dagon-iot-runner`, embed a redacted portable specification,
declare scratch outputs, and retain semantics in `dagon:IoTTask`. Execution
still needs the selected provider and device access. See [IoT and CWL](iot_cwl.md).

## Streams

CWL v1.2 has no concurrency between steps, so a
[stream](adhoc_filesystems.md#streaming-between-tasks) between two tasks is
exported in materialized form, and the document stays standards-valid:

- the producer's command is wrapped so that the stream is ended with the
  command's status (`dagon.adhoc stream close`), and its stream is written to
  `$(runtime.outdir)/.dagon-streams/<path>`, exposed as a `Directory` output
  `stream_<producer>_<path>`;
- the consumer's `workflow:///P/path?stream` reference becomes that
  directory (a `Directory` input; with portable emulation the path inside the
  producer's `task_dir` input, because cwltool does not reliably stage a
  directory nested in another staged one), so the consumer runs after the
  producer and reads the complete stream with the same `dagon.adhoc stream`
  commands;
- an `EnvVarRequirement` provides the `DAGON_STREAM_*` variables,
  `DAGON_PYTHON=python3`, and, for consumers, `DAGON_STREAM_IDLE_TIMEOUT=60`
  (the materialized stream is complete, so a missing marker is an error);
- a `dagon:Stream` hint (namespace `https://dagonstar.org/cwl#`) on the
  consumer records `producer`, `stream`, `adhoc`, and `provider`. Generic
  runners report it as an unknown hint and ignore it.

The steps need DAGonStar importable by `python3` in the runner's environment.
The ad-hoc resource itself is not exported. `$(...)` in a command is a CWL
expression, so exported commands should use backticks for shell command
substitution. [`examples/cwl/export_streaming_workflow.py`](../examples/cwl/export_streaming_workflow.py)
exports a portable stream workflow whose consumer verifies the items;
`tests/test_adhoc_streaming.py` runs it with `cwltool` when it is installed
(observed on 18 November 2026 with cwltool on macOS).

## Agentic tasks

`TaskType.AGENTIC` is exported as an executable step whose `baseCommand` is
`dagon-agent-runner run` (installed by `pip install -e .`). The step embeds the
portable, versioned contract as `agent-task.json` through
`InitialWorkDirRequirement`, binds each declared `workflow://` input to the
producer's CWL `File` output (or, with portable emulation, to a path inside
the producer's `task_dir`), and declares the agent's `result`, `evaluation`,
and `trace` files as CWL `File` outputs. A `dagon:AgenticTask` hint records the
schema version, profile name, and contract SHA-256.

Workflows containing an agentic task gain one workflow-level input,
`dagon_config: File`. The agent profile, including any endpoint and the name of
the environment variable holding a key, is resolved from that file at run
time; no endpoint, credential, or scratch path is written to the CWL document.
With `portable_emulation=True` the runner forces the deterministic mock
adapter. Workflows without agentic tasks are exported exactly as before.

The runner exits non-zero when the result is not accepted, so a generic CWL
runner does not start dependent steps. Only producers in the same workflow
that declare the referenced file as an output can be bound; other references
raise `ValueError` at export. `tests/test_agentic_cwl.py` checks determinism
and credential safety, and validates and executes a producer → agent →
consumer document with `cwltool --no-container` when both `cwltool` and
`dagon-agent-runner` are installed (the test is skipped otherwise).
`examples/agentic/cwl_local.py` and
[Lesson 29](tutorial/lesson_29_export_and_validate_common_workflow_language.md)
show the same export. See [Agentic tasks](agentic_tasks.md).

## Meta-tasks

`TaskType.META` is exported as an executable step whose `baseCommand` is
`dagon-meta-runner run` (installed by `pip install -e .`). The credential-free
specification is embedded as `meta-task.json` through
`InitialWorkDirRequirement`; each `workflow://` input is bound to the producer
step's `File` output, or `Directory` output for inputs declared with
`"type": "directory"`, through `--bind REFERENCE=$(inputs.in_N.path)`; each
declared output is a CWL `File` or `Directory` output with glob
`outputs/<path>`, so other meta or agentic steps can bind it; it is also a workflow-level output
named `<step>_<output>`. A
`dagon:MetaTask` hint records the schema version, engine, workflow location,
and the SHA-256 of the external workflow definition.

The portable boundary is explicit: CWL describes the DAGonStar graph and the
meta step's inputs and outputs, not the steps inside the external workflow.
The engine and the workflow definition named in the specification must be
installed on the CWL execution host at the recorded location. Only producers in
the same workflow can be bound; other references raise `ValueError` at export.
With `portable_emulation=True` a meta step is exported like other structured
task types (a placeholder command). `tests/test_meta_task.py` checks
determinism, bindings, and `cwltool --validate`; `examples/cwl/export_meta_workflow.py`
exports, validates, and with `--run` executes a producer → meta-task document.
See [Meta-tasks](meta_tasks.md).

## Runnable interoperability material

The [`examples/cwl/`](../examples/cwl/README.md) directory contains the Python
source and its deterministic, checked-in CWL output. The [example guide](examples/cwl.md)
and [Lesson 29](tutorial/lesson_29_export_and_validate_common_workflow_language.md) cover regeneration,
automatic testing, runner validation, and the interoperability boundary.
