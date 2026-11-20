# Volume tasks (`TaskType.VOLUME`)

A volume task creates, or destroys, one ad-hoc file-system volume as a node of
the workflow graph. Other tasks use the volume through the ordinary
`workflow://` schema, and the volume is released when no task refers to it any
longer. Volume tasks build on the [ad-hoc file-system](adhoc_filesystems.md)
adapters: any registered provider that can serve a volume outside a Slurm
allocation (DAGonFS, CAPIO, Hercules, DynoStore, or a pluggable adapter) can be
used. Implementation: [`dagon/volume.py`](../dagon/volume.py).

## Creating a volume

```python
from dagon.task import DagonTask, TaskType

abc = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz",
                stage_in={"inputs/data": "workflow:///Prep/data",
                          "inputs/n.txt": {"path": "workflow:///Prep/n.txt", "type": "file"}},
                options={"frontend": "fuse3"})
```

| Argument | Meaning |
|---|---|
| `provider` | registered ad-hoc provider name or adapter class (create only); `beeond` is refused because BeeOND volumes exist only inside a Slurm allocation |
| `volume` | volume name, unique in the workflow (letters, digits, `.`, `_`, `-`); defaults to the task name |
| `stage_in` | `{path in the volume: source}`; a source is a `workflow://` reference to another task's scratch directory, an existing local path, or `{"path": ..., "type": "file" \| "directory"}` |
| `options` | provider options passed to the adapter (JSON, credential-free; credential-like keys are refused, `token_env` names a variable) |
| `export` | developer-chosen variable carrying the volume path in every bound task |
| `release` | `"auto"` (default): release when the last reference is gone; `"end"`: keep until a destroy task or the end of the workflow |

When the task runs it starts the volume, waits until the provider is ready,
and copies the `stage_in` entries into it with a helper process
(`python -m dagon.volume stage`) that receives the volume's task environment,
so preload providers intercept the helper's file calls. Each stage-in source
creates a dependency on its producer, as any `workflow://` reference does.

## Using a volume: `workflow:///<task>/<volume>/...`

If the volume task `Abc` created the volume `xyz`, then
`workflow:///Abc/xyz/results/out.txt` is `results/out.txt` inside the volume.
The reference keeps the schema's meaning (`<workflow>/<task>/<path>`, a path in
the producer task's data space) because the volume appears in `Abc`'s scratch
directory under its own name. What changes is only the transfer:

- A command task (batch, Slurm, Docker, ...) that refers to the volume is bound
  to it (it receives `DAGON_ADHOC_*`, the `export` variable, and, for preload
  providers, the interception library) and its reference is rewritten to the
  location inside the volume. Nothing is copied: writes by one task are seen by
  every later task, so several siblings may read and write the same volume.
  Globs keep working because the path part is left unquoted.
- A structured task (native, web, LLM, FaaS, IoT, agentic, meta) reads the path
  through the scratch-directory link, which exists for POSIX volumes and under
  portable emulation. Structured readers of preload, client, or object volumes
  are refused when dependencies are made.
- A reference to `Abc` whose path does not start with the volume name is an
  ordinary scratch reference.
- `abc.attach(t1, t2)` binds tasks that use the volume only through
  `$DAGON_ADHOC_<NAME>_PATH` or an `export` variable; they are counted as users.

Volume references are not pre-staged: a task that uses a volume is ineligible
for [scheduler-aware pre-staging](scheduler_prestaging.md).

## Streams through a volume

A provider that supports streaming carries streams between tasks bound to the
volume. The producer is a command task; the consumer names the volume in the
query:

```text
workflow:///Emit/numbers?stream=xyz
```

This binds `Emit` and the consumer to `xyz` and runs them concurrently with
the [stream protocol](adhoc_filesystems.md#streaming-between-tasks). A volume
task is never a stream producer, and a `?stream` query on a volume reference
(`workflow:///Abc/xyz/...?stream`) is refused with a hint to use
`?stream=<volume>`.

## Releasing a volume

**Reference counting.** Every task that refers to the volume increments its
reference count when dependencies are made; the count is decremented when the
task finishes, with the same rule that collects scratch directories
([`Task.decrement_reference_count`](../dagon/task.py)). At zero the volume is
released (its provider stopped) whatever the `remove_dir` setting, and before
the workflow ends. A volume that no task refers to is released right after it
was created. A user that failed keeps the volume until the end of the workflow.
`release="end"` disables early release.

**Destroy task.** A destroy task is optional:

```python
delete = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                   stage_out={"results": {"path": "workflow:///Abc/xyz/results", "type": "directory"},
                              "summary.txt": "results/summary.txt"})
```

It receives a dependency on every task that uses the volume, copies each
`stage_out` entry (a path in the volume, a reference inside it, or a
descriptor) into its own scratch directory, and releases the volume. Later
tasks read the copies as `workflow:///Del/results/...`. A task that uses the
volume but must run after the destroy task, two destroy tasks for one volume,
and a destroy reference that does not name a create task's volume are refused
when dependencies are made.

Every remaining volume is released when the workflow ends, also after a
failure.

## Provider support

| Provider | Access | Location used for references | Streams |
|---|---|---|---|
| DAGonFS (`fuse3`) | posix | mount point | yes |
| DAGonFS (`native`) | client | path in the DAGonFS namespace, staged through its Python client | yes |
| CAPIO | preload | intercepted directory | yes |
| Hercules | preload | intercepted directory | yes |
| DynoStore | object | deterministic object key (UUID v5 of volume and path); directories are a manifest object | yes |
| pluggable adapters | as declared | `volume_location()` hook | when `supports_streaming` |
| BeeOND | - | refused (allocation-scoped) | - |

Adapters may override `volume_location`, `volume_reference_text`,
`volume_parameters`, and `open_volume_store` to serve volume tasks; the
defaults cover POSIX and preload providers.

## Checkpoints, JSON, FAIR, and CWL

- **Checkpoints.** A volume does not survive the process, so a create task's
  checkpoint is reused only when it records the same specification and every
  user's checkpoint is also complete; otherwise the volume is created again. A
  destroy task's checkpoint is reused only after the SHA-256 of its staged
  outputs is re-verified. A bare successful directory is never reused.
- **JSON.** Both actions survive `Workflow.as_json()` / `load_json()`.
- **FAIR.** Dependency edges served by a volume carry `"transfer": "volume"`
  and the volume name; the volume task's execution metadata records the action, volume,
  the resource's `metadata()` (provider, access, scope, owner), staged items with
  their digests, the release reason, and the users, never credentials.
- **CWL.** CWL v1.2 has no shared mutable storage. The exporter materializes
  the volume as a `Directory` output of the create step (its staged-in
  content), passes it to consumers, lets the destroy step copy its `stage_out`
  entries, and records the intent in a `dagon:Volume` hint. Data written into
  the volume by sibling steps is not exchanged through CWL. See
  [CWL export](cwl_export.md#volume-tasks).

## Portable emulation and evidence

Under portable emulation the volume is a local directory below the creating
task's scratch directory; no provider is started, and an emulated run is not
evidence that the provider ran. [`examples/adhoc/volume_task.py`](../examples/adhoc/volume_task.py)
executes create, shared writes, a stream, destroy with stage-out, and
reference-counted release on a real local-directory adapter, and accepts
`--emulate PROVIDER` or `--live PROVIDER --option KEY=VALUE`.
[`tests/test_volume_task.py`](../tests/test_volume_task.py) covers
construction, discovery, execution, checkpoints, stores (with an in-memory
object store), and CWL. No live run of a volume task on a deployed provider is
recorded in `docs/performance/` yet. Tutorial:
[Lesson 26](tutorial/lesson_26_share_and_release_volumes_with_volume_tasks.md).
