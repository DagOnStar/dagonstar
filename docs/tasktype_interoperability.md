# Task-type interoperability contract

DAGonStar workflows may combine any registered `TaskType` in one directed
acyclic graph. A producer's execution backend does not constrain the consumer's
backend: the edge is expressed through `workflow://`, and the configured stager
moves or exposes the artifact between their working directories.

## Contract shared by every task type

Every factory type supports:

- factory construction through `DagonTask(TaskType.<TYPE>, ...)`;
- explicit dependencies and automatic `workflow://` dependency discovery;
- opt-in FAIR input/output declarations and lifecycle provenance;
- successful-checkpoint reuse when the recorded working directory remains accessible;
- JSON workflow representation and deterministic CWL v1.2 graph export;
- coexistence with every other type in the same workflow.

The automated contract is in `tests/test_tasktype_interoperability.py`. It
constructs one graph containing all task types and verifies dependency
discovery, FAIR declarations, checkpoint reuse, and CWL export. Backend-specific
tests separately mock service boundaries without requiring live services.

## Portable emulation

Pass `portable_emulation=True` to `Workflow` to run every task type locally
without contacting Docker, SSH, Slurm, cloud, Kubernetes, Apptainer, or Nomad:

```python
workflow = Workflow("portable-demo", config=config, portable_emulation=True)
```

Command tasks run in isolated local scratch directories. LLM, Web, and FaaS use
credential-free deterministic emulators; Native runs locally; Meta-tasks use the
`mock` engine, which writes placeholder outputs without starting the external engine. Original task
types remain visible in FAIR metadata, JSON, checkpoints, and the DAG. This
profile supports CI, teaching, Colab, Jupyter, and portable validation.

## Backend matrix

| Type | Execution requirement | Notebook/Colab interpretation |
|---|---|---|
| `BATCH` | POSIX shell | Runs locally. |
| `CHECKPOINT` | POSIX shell | Runs locally; persistent storage is recommended. |
| `SLURM` | Local or reachable Slurm client | Construct/export anywhere; live run needs Slurm. |
| `CLOUD` | Provider extra, identity, reachable instance | Live run needs the provider. |
| `DOCKER` | Docker extra and daemon | Local Jupyter may use Docker; hosted Colab normally cannot. |
| `KUBERNETES` | Kubernetes extra and kubeconfig | Live run needs a reachable cluster. |
| `APPTAINER` | Apptainer installation and image | Live run needs an Apptainer-capable host. |
| `NOMAD` | Reachable Nomad API and client environment | Live run needs a Nomad deployment. |
| `LLM` | Configured compatible or local mock endpoint | Local mock runs in notebooks and Colab. |
| `NATIVE` | Importable Python function | Runs locally. |
| `WEB` | HTTP/HTTPS endpoint or local mock server | Local mock runs in notebooks and Colab. |
| `FAAS` | Mock, HTTP, or configured provider adapter | Mock provider runs locally. |
| `IOT` | Mock or configured provider adapter | Deterministic mock runs locally. |
| `AGENTIC` | `dagon.ini` agent profile (mock or OpenAI-compatible adapter) | Mock adapter runs locally; portable emulation forces it. |
| `META` | The external engine (Nextflow, Snakemake, Parsl, StreamFlow, a CWL runner, or any CLI) installed on the DAGonStar host | `command` adapter runs locally; portable emulation forces the `mock` engine. |
| `VOLUME` | A registered ad-hoc provider (DAGonFS, CAPIO, Hercules, DynoStore, or a pluggable adapter) reachable from the DAGonStar host | Pluggable local adapters run locally; portable emulation replaces the volume by a local directory. |

“Notebook supported” means workflow creation, validation, FAIR recording,
checkpoint loading, and CWL export work in the Python kernel. A notebook does
not emulate an unavailable scheduler, container runtime, cluster, or cloud.

Scheduler-aware pre-staging (`Workflow(pre_stage=True)` or a task's
`pre_stage=True`) is supported only by `SLURM` tasks (`Slurm` and
`RemoteSlurm`) that do not use BeeOND or parallel mode. Every other type keeps
its lifecycle when it inherits the workflow default, and rejects an explicit
`pre_stage=True` with `PreStageConfigurationError`. Portable emulation ignores
the setting. See [Scheduler-aware pre-staging](scheduler_prestaging.md).

## Mixed workflow example

```python
workflow.add_task(DagonTask(TaskType.BATCH, "prepare",
    "mkdir -p output; echo sample > output/value.txt"))
workflow.add_task(DagonTask(TaskType.NATIVE, "transform",
    "myproject.tasks:transform",
    inputs={"source": "workflow:///prepare/output/value.txt"},
    outputs={"result": "result.txt"}))
workflow.add_task(DagonTask(TaskType.FAAS, "publish", provider="mock",
    function="echo",
    inputs={"document": "workflow:///transform/outputs/result.txt"}))
```

The same pattern applies to every producer/consumer pairing. Remote and
container combinations require a stager compatible with both endpoints. Never
place credentials in commands, checkpoints, JSON, CWL, or FAIR metadata.

## Checkpoint and restart semantics

`Workflow.run(resume_checkpoint_file=...)` loads successful task records.
Command, LLM, Native, Web, and FaaS tasks skip execution when the recorded
working directory is still accessible. Remote tasks check through their remote
connection. If storage has disappeared, the task runs normally.

Checkpoint identity is currently the workflow and task name. Changing behavior
without renaming the task can reuse an older checkpoint; use a new task name or
checkpoint file when changing the experiment. FaaS additionally checks a
portable-specification digest. A completed pre-staged Slurm task is reused
only if the content identity of its inputs (POSIX `cksum` of every file,
recomputed on the submission host from the producers' current outputs)
matches the identity recorded after its stage-in; otherwise it runs again. A
failed task, including a staging or submission failure, is staged again and
resubmitted on resume. The stage-in completion marker is never a skip token.
IoT additionally validates schema version, declared outputs, and SHA-256 evidence.
Agentic tasks are reused only after re-verifying contract, profile, registered
versions, input content hashes, and published output hashes; agentic inputs
must come from producers with a local working directory. See
[Agentic tasks](agentic_tasks.md).
Meta-tasks are reused only after re-verifying the specification digest, the
workflow-definition digest, the content digests of their inputs (re-read from
the producers' current outputs), and the digests of the collected outputs; a
remote workflow definition always runs again. See [Meta-tasks](meta_tasks.md).
Volume tasks are reused only when their recorded volume specification matches
and, for a create task, every task that uses the volume completed too (a
volume does not survive the process); a destroy task re-verifies the SHA-256
of its staged outputs. See [Volume tasks](volume_tasks.md).
