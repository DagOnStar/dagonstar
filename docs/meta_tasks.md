# Meta-tasks: run workflows written for other engines

`TaskType.META` runs a complete workflow written for another workflow engine
(Nextflow, Snakemake, Parsl, StreamFlow, a CWL runner, or any engine with a
command-line interface) as one task of a DAGonStar workflow. Data moves in
and out through ordinary `workflow://` references, so the external workflow
is a node of the DAGonStar graph like any other task.

Two properties hold by construction:

- **The external engine is never modified.** DAGonStar runs the engine's
  documented command line and writes the engine's own parameter files
  (Nextflow `-params-file`, Snakemake `--configfile`, a CWL job document, a
  Python call for Parsl). Nothing is patched, monkey-patched, or installed.
- **Engines are homogenised by adapters.** Every engine-specific detail lives
  in one adapter class (`dagon.meta.adapters`); the task, the staging,
  output collection, checkpoint, FAIR, JSON, and CWL behaviour are shared.

```python
from dagon.task import DagonTask, TaskType

count = DagonTask(TaskType.META, "count", engine="nextflow", workflow="pipelines/wordcount/main.nf",
                  inputs={"text": "workflow:///prepare/data/text.txt", "top": 10},
                  outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}},
                  engine_options={"profile": "standard"}, timeout=3600)
report = DagonTask(TaskType.BATCH, "report", "sort workflow:///count/outputs/counts.tsv > report.tsv")
```

`prepare -> count -> report` is discovered from the references alone.

## Task interface

`MetaTask(name, engine, workflow, inputs=None, outputs=None, engine_options=None,
environment=None, timeout=None, staging="copy", working_dir=None)`

| Argument | Meaning |
| --- | --- |
| `engine` | Registered adapter name: `nextflow`, `snakemake`, `parsl`, `streamflow`, `cwl`, `command`, `mock`, or a plug-in. |
| `workflow` | The external workflow definition: a local file or directory (resolved to an absolute path when the task is created), or, for adapters with `remote_workflows` such as Nextflow, an engine-resolved name (`nextflow-io/hello`). It may not be a `workflow://` reference. |
| `inputs` | Name → value. A `workflow://` string is a staged file or directory (detected at run time). `{"type": "file"|"directory", "path": ...}` names a local or referenced path explicitly. `{"type": "value", "value": ...}` or any other JSON value is passed through unchanged. Names must be identifiers (`[A-Za-z_][A-Za-z0-9_]*`). References embedded inside structured values are refused: bind each file or directory as its own input. Stream references (`?stream`) are refused. |
| `outputs` | Name → relative path, or `{"path", "source", "engine_output", "type", "required"}`. `path` is the destination below `outputs/`; `source` is the location relative to the engine run directory (default: `path`); `engine_output` names an output the engine reports (CWL runners, StreamFlow); `type` is `file` (default) or `directory`; `required` defaults to `True`. |
| `engine_options` | Adapter options (JSON). Unknown options are rejected. Keys that look like credentials are rejected. |
| `environment` | Extra environment variables for the engine. Credential-like names are rejected; credentials are inherited from the parent process environment and never stored in the specification. |
| `timeout` | Seconds before the engine is terminated (`MetaTimeoutError`). |
| `staging` | `copy` (default) or `symlink` for staged inputs; use `symlink` for large data when the engine runs on the same host. |

Every validation error is a `MetaValidationError` (a `ValueError`) raised when
the task is created, before any side effect.

## Lifecycle and scratch layout

1. **Dependencies.** `pre_run` adds one dependency (and one reference count)
   per producer named by a `workflow://` input.
2. **Staging in.** Each file or directory input is copied (or symlinked) to
   `inputs/<name>/<basename>` in the task scratch directory.
3. **Invocation.** The adapter writes the engine-native parameter files below
   `.dagon/` and returns an argument vector; the engine runs in `run/` without a
   shell, with the task timeout. Its standard output and error are kept in
   `.dagon/engine_stdout.txt` and `.dagon/engine_stderr.txt`.
4. **Output collection.** Each declared output is taken from the location the
   engine reported or from `run/<source>`, refused if it resolves outside the
   scratch directory (symbolic links included), copied atomically to
   `outputs/<path>`, and hashed (SHA-256; directories by sorted relative path
   and content).
5. **Result.** `.dagon/meta_result.json` records the engine, adapter, engine
   version (best effort), workflow identity, input and output digests,
   duration, and sanitized engine metadata (for example the Nextflow process
   count read from its trace file).

```text
<scratch>/
  .dagon/meta_spec.json        effective specification
  .dagon/meta_bindings.json    reference -> staged path
  .dagon/meta_invocation.json  argument vector and environment *names* only
  .dagon/<engine files>        nextflow-params.json, snakemake-config.json, cwl-job.json, ...
  .dagon/meta_result.json      evidence
  inputs/<name>/...            staged inputs
  run/                         engine working (launch) directory
  outputs/<path>               collected outputs, referenced downstream
```

Downstream tasks read outputs as `workflow:///<meta task>/outputs/<path>`.

Failures are classified in `task.failure_phase`: `validation`, `engine`
(executable or library not installed), `staging`, `execution` (non-zero exit or
timeout), or `outputs` (a required output is missing or escapes scratch). A
failed meta-task fails its dependants, as every other task type does.

## Built-in adapters

All adapters accept `executable` (override the engine executable; also
settable per site in `dagon.ini`) and `arguments` (extra engine arguments, a
list of strings).

| Engine | Command | Inputs reach the workflow as | Specific options |
| --- | --- | --- | --- |
| `nextflow` | `nextflow -log … [-c cfg] run <workflow> -params-file .dagon/nextflow-params.json -work-dir run/work -ansi-log false [-with-trace …]` | `params.<name>` (absolute paths for files) | `profile`, `config` (paths), `revision`, `resume`, `trace` (default true), `work_dir` |
| `snakemake` | `snakemake --snakefile <workflow> --directory run --configfile .dagon/snakemake-config.json --cores N [targets]` | `config["<name>"]` | `cores` (int or `all`), `targets`, `profile`, `executor` (for example `slurm`) |
| `parsl` | function mode: `python dagon/meta/parsl_driver.py --job .dagon/parsl-job.json`; script mode: `python <workflow> <arguments>` | keyword arguments of `entrypoint` (function mode), or the JSON document named by `DAGON_META_PARAMETERS` (script mode) | `mode` (`function`/`script`), `entrypoint` (default `main`), `config` (`threads`, `htex_local`, or `path/config.py:attribute`), `max_threads`, `python` |
| `streamflow` | `streamflow run .dagon/streamflow.yml --outdir run/streamflow-output` | CWL job document (`File`/`Directory` objects) | `deployments`, `bindings` (generated StreamFlow file), `workflow_name` (existing StreamFlow file) |
| `cwl` | `cwltool [arguments] --outdir run/cwl-output <workflow> .dagon/cwl-job.json` | CWL job document | `runner` (any CWL runner accepting `--outdir`, such as `toil-cwl-runner`) |
| `command` | `engine_options["command"]`, an argument vector with placeholders | JSON document named by `{parameters_file}` and `DAGON_META_PARAMETERS`; `{inputs[name]}` | `command` |
| `mock` | no process | deterministic JSON placeholders | used automatically in portable emulation |

Notes that matter in practice:

- **Nextflow** runs with `run/` as its launch directory, so `publishDir`
  relative paths land where `source` paths are resolved. Remote pipelines are
  fetched by Nextflow itself; pin them with `revision`.
- **Snakemake** resolves relative rule outputs against `--directory`.
- **Parsl** programs are Python programs. In function mode the program defines
  a function that composes Parsl apps and returns futures (or structures of
  futures); the driver loads the Parsl configuration, calls it with the inputs
  as keyword arguments, waits for every future, writes
  `.dagon/parsl-result.json`, and calls `parsl.dfk().cleanup()` and
  `parsl.clear()`. The module must not call `parsl.load()` at import time
  (`if __name__ == "__main__":` is enough). A custom `config` can name any
  `parsl.config.Config`, for example one with a `SlurmProvider`. The driver
  imports nothing from DAGonStar, so `python` may name an interpreter that has
  Parsl but not DAGonStar's dependencies.
- **StreamFlow** runs a CWL workflow on the deployments its StreamFlow file
  declares. Given a `.cwl` file the adapter generates the StreamFlow file
  (with `deployments` and `bindings` copied verbatim); given an existing
  StreamFlow file it writes a derived copy whose workflow `settings` point at
  the meta-task inputs and whose CWL `file` is absolute. The original file is
  never modified. StreamFlow resolves relative paths against the StreamFlow
  file's directory and the derived file lives in `.dagon/`, so paths inside
  `deployments` should be absolute. The StreamFlow metadata database is kept
  in `.dagon/streamflow.db`.
- **CWL runners** print the CWL output object; outputs declared with
  `engine_output` are taken from it by name.

### Site configuration

An optional `[meta.<engine>]` section of `dagon.ini` supplies site defaults
for `executable` (every engine) and `python` (Parsl). Task options take
precedence. The effective values are part of the checkpoint identity.

```ini
[meta.nextflow]
executable = /opt/nextflow/bin/nextflow

[meta.parsl]
python = /opt/parsl-env/bin/python
```

## Checkpoint and resume

A completed meta-task is reused only when all of the following still hold:
the effective specification has the same SHA-256; the workflow definition is
local and has the same digest (a remote workflow cannot be re-verified and
always runs again); every file or directory input, re-read from its producer's
*current* scratch directory, has the recorded digest; and every collected
output still exists with its recorded digest. A bare successful directory is
never enough. Checkpoints from portable emulation are not reused by real runs
and vice versa. The checkpoint record contains no credentials and no
environment values.

The engine's own resume mechanism (for example Nextflow `resume`) is
independent and opt-in through `engine_options`.

## Portable emulation

With `Workflow(portable_emulation=True)` meta-tasks never start their engine:
the `mock` adapter writes one JSON placeholder per declared output (an empty
directory with `placeholder.json` for directory outputs) recording the engine
that would have run and the digests of its inputs. Results are marked
`emulated` in `.dagon/meta_result.json`, checkpoints, and FAIR records.

## FAIR provenance

When FAIR recording is enabled, each collected output becomes an artifact
(`role` `meta-file` or `meta-directory`, SHA-256 checksum, `emulated` flag), and
the RO-Crate `CreateAction` of the task names the external workflow as its
`instrument`: a `ComputationalWorkflow` identified by engine and workflow
digest, with the engine version when it could be determined locally. The
recorder does not inspect the engine's internal provenance (for example a
Nextflow report or StreamFlow's database); those files stay in the scratch
directory.

## CWL export

`Workflow.saveAsCWL` exports a meta-task as a `CommandLineTool` that runs
`dagon-meta-runner run --spec meta-task.json --workdir .`, with the
specification embedded through `InitialWorkDirRequirement`. Each `workflow://`
input becomes a `File` (or `Directory`) step input bound to the producer step's
output (`--bind REFERENCE=$(inputs.in_N.path)`), and each declared output is a
CWL output with glob `outputs/<path>`, exposed as the workflow output
`<step>_<output>`. A `dagon:MetaTask` hint records the
schema version, engine, workflow location, and workflow SHA-256. The export is
deterministic and credential-free.

The boundary is explicit: the external engine and the workflow definition
named in the specification must be installed on the CWL execution host, and
`dagon-meta-runner` must be on `PATH` (`pip install -e .`). What the engine does
inside its run is outside the portable command-graph contract. In portable
emulation the meta step is exported like other structured task types. See
[CWL export](cwl_export.md) and `examples/cwl/export_meta_workflow.py`.

## Developing a new adapter

An adapter is a subclass of `dagon.meta.MetaEngineAdapter`. It is the only
code a new engine needs; neither DAGonStar nor the engine changes.

```python
from dagon.meta import EngineCapabilities, EngineInvocation, MetaEngineAdapter, register_adapter


class AirflowTestAdapter(MetaEngineAdapter):
    """Run one Airflow DAG locally with ``airflow dags test`` (illustrative)."""

    name = "airflow-test"
    executable = "airflow"          # looked up on PATH; engine_options["executable"] overrides it
    options = ("dag_id",)           # engine options accepted besides executable and arguments

    def capabilities(self):
        return EngineCapabilities(remote_workflows=True)   # dag_id is resolved by Airflow, not a file

    def prepare(self, context):
        conf = context.write_json("airflow-conf.json", context.parameters)   # .dagon/airflow-conf.json
        return EngineInvocation(
            argv=[self.resolve_executable(context), "dags", "test", context.option("dag_id"),
                  "--conf", conf.read_text()] + context.arguments(),
            cwd=context.run_dir,
            generated_files=[".dagon/airflow-conf.json"])


register_adapter("airflow-test", AirflowTestAdapter)
```

### The contract

| Member | Required | Contract |
| --- | --- | --- |
| `name` | yes | Lower-case registry name. |
| `executable` | no | Default executable; `None` when the adapter starts a known interpreter (Parsl) or none (mock). |
| `options` | no | Accepted engine option names; anything else is rejected by `validate`. |
| `capabilities()` | no | `EngineCapabilities(remote_workflows, directory_inputs, named_outputs, parameter_format)`; the task validates the specification against it. |
| `validate(workflow, engine_options)` | no | Static checks only; must not start the engine. Call `super().validate(...)`. |
| `unavailable_reason(context)` | no | Return why the engine cannot run on this host (missing executable or library), or `None`. Reported as failure phase `engine`. |
| `prepare(context)` | **yes** | Write engine-native parameter files with `context.write_json(...)` (or your own writer) below `context.metadata_dir`, and return an `EngineInvocation(argv, cwd, environment, generated_files)`. `argv` is an argument vector: never build a shell string. |
| `execute(context, invocation)` | no | Default: run `argv` without a shell, with the timeout, saving stdout/stderr; raise `MetaEngineFailedError` on a non-zero status. Override to read engine reports into `EngineResult.metadata` (call `super().execute` first) or for engines without a process. |
| `collect_outputs(context, result)` | no | Return output name → local path for outputs the engine reports by name; set `named_outputs=True` in the capabilities. |
| `version(context)` | no | Best-effort engine version for provenance; `None` when unknown. |

`MetaRunContext` gives the adapter `engine`, `workflow`, `workdir` (scratch),
`run_dir`, `metadata_dir`, `inputs` (`MetaInput(name, kind, value, reference,
sha256)` with `kind` in `value`/`file`/`directory` and absolute paths as
values for files), `parameters` (name → value), `outputs`, `engine_options`,
`environment`, `timeout`, `python`, and the helpers `write_json`, `option`, and
`arguments`.

### Rules for adapters

- Do not modify, patch, or wrap the engine's code; use its public command line
  or public API only.
- Keep imports of the engine lazy (inside methods or a separate process) so the
  base installation stays engine-free.
- Never put credentials in parameter files, argument vectors, metadata, or
  errors. Engines inherit credentials from the parent environment.
- Write generated files below `context.metadata_dir`; let the engine write in
  `context.run_dir`.
- Report only what the adapter can substantiate locally in
  `EngineResult.metadata` (for example counts read from an engine trace file).

### Registering an adapter

Call `register_adapter(name, cls)` before the task is created, or declare the
class in the `dagon.meta_adapters` entry-point group of an installed package:

```toml
[project.entry-points."dagon.meta_adapters"]
airflow-test = "my_package.adapters:AirflowTestAdapter"
```

Built-in names cannot be replaced, and registering a second class under an
existing name needs `replace=True`.

### Testing an adapter

Test `prepare` without the engine: create a `MetaRunContext` in a temporary
directory, set `engine_options["executable"]` to an existing program (for
example `sys.executable`), and assert on `invocation.argv` and the generated
parameter files (see `tests/test_meta_task.py::MetaAdapterCommandTests`). Add
a live test guarded by `unittest.skipUnless(shutil.which("<engine>"), ...)`.

## Verification

The tutorial covers meta-tasks in [Lesson 30](tutorial/lesson_30_compose_meta_workflows.md)
(composition) and [Lesson 31](tutorial/lesson_31_run_other_engines_workflows_with_meta_tasks.md)
(a new adapter, checkpoint identity, failure phases, and emulation).

```bash
python -m unittest tests.test_meta_task -v
python examples/tutorial/lesson_31_meta_tasks.py
python examples/meta/meta_workflow_local.py
python examples/meta/meta_engines.py            # every installed engine; others are skipped
python examples/cwl/export_meta_workflow.py
```

`tests.test_meta_task.MetaLiveEngineTests` run the real engines only when
installed (`DAGON_META_PARSL_PYTHON` names an interpreter with Parsl). The live
results recorded for this release are in
[performance/meta_engines_2026-11-19.md](performance/meta_engines_2026-11-19.md).

## Limitations

- The engine runs on the DAGonStar host as a local process. Remote and HPC
  execution is delegated to the engine's own executors (Nextflow executors,
  Snakemake executor plugins, Parsl providers, StreamFlow deployments); running
  the engine itself over SSH or inside a Slurm allocation is future work.
- Only declared outputs are collected and exposed; the engine's other files
  remain in `run/`.
- Meta-tasks do not produce or consume streams and are not eligible for
  scheduler-aware pre-staging.
- Input and output digests read whole files and directory trees, which costs
  time on very large data.
- Workflow identity covers the workflow definition (file or directory tree),
  not containers, modules, or remote assets that the engine fetches at run time.
