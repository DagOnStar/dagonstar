# Changelog

All notable changes to DAGonStar are recorded here. Versions follow
`setup.cfg`; release tags are `v<version>`.

## Unreleased

### DAGonService client

- `[dagon_service] token` (or `DAGON_SERVICE_TOKEN`) sends an access token as
  `Authorization: Bearer`, for services that set `DAGONSERVICE_API_TOKEN`.
- `[dagon_service] timeout` (default 10 s) bounds every request to the service.
- Path segments and the `update_task` value are URL-encoded; working
  directories containing `&`, `#` or `+` reached the service altered.

### Fixes

- A task whose name contains shell metacharacters (for example `C$x`) no longer
  fails: scratch directory names keep only `[A-Za-z0-9._-]` (other characters
  become `_`), and the launcher's and Native launcher's `cd` are quoted.

## 3.0.0 (2026-11-20)

First release since `v2.0.2`. It gathers the work released on `development`
under the 2.9.x version numbers, which were never tagged.

### Behaviour changes to review when upgrading

- A task whose command exits with a non-zero status now fails, and so do its
  dependants. Before, the exit status was ignored.
- `make_dependencies()` and `Workflow.load_json()` keep explicit dependency
  edges when they rebuild the graph.
- Portable emulation ends a `workflow://` reference at the next space, as real
  runs do. A task whose reference names no producer artifact now fails under
  emulation.
- The names of the built-in ad-hoc providers (`dagonfs`, `beeond`, `hercules`,
  `capio`, `dynostore`) cannot be replaced, even with
  `register_provider(..., replace=True)`.
- The tutorial has 36 lessons. Former Lessons 25–32 are now 27–35, and the
  example scripts were renamed to match.

### New task types

- `TaskType.VOLUME` creates or destroys one ad-hoc file-system volume as a
  task. Sibling tasks share it as `workflow:///<task>/<volume>/...` and stage
  data in from other tasks' scratch directories. Data can be streamed through
  the volume with `?stream=<volume>`. The volume is released by an optional
  destroy task, which stages results out, or by reference counting when no
  task refers to it any longer.
- `TaskType.META` runs Nextflow, Snakemake, Parsl, StreamFlow, CWL, or any
  command-line workflow unmodified, through an adapter registry.
- `TaskType.AGENTIC` runs bounded agents selected by `dagon.ini` profiles,
  with:
  - registered tools and guardrails;
  - independent evaluation;
  - atomic publication of accepted results;
  - verified checkpoint reuse.
- Native Python, web, LLM, FaaS, and IoT tasks run with deterministic mocks
  for local use.

### Storage, scheduling, and data movement

- A common ad-hoc file-system interface covers DAGonFS (FUSE3, native socket,
  and preload frontends), BeeOND, Hercules, CAPIO, and DynoStore. Resources
  have workflow, task, and volume scopes. A task may use several volumes, and
  `export=` names the variable that carries a volume's path. New providers
  need only a registered adapter.
- Streaming between tasks (`workflow://...?stream`) uses a verified,
  rename-free marker protocol.
- BeeOND volumes can be created per task or per workflow for Slurm tasks.
- Scheduler-aware pre-staging (`pre_stage=True`) stages and verifies inputs
  before `sbatch`, for Slurm and RemoteSlurm tasks.

### Interoperability and FAIR

- CWL v1.2 export covers every task type. Streams and volumes are exported in
  materialized form, with `dagon:Stream` and `dagon:Volume` hints.
- Opt-in FAIR metadata and provenance recording, with RO-Crate, PROV,
  DataCite, and CodeMeta exports.

### Quality

- CI runs on Ubuntu (Python 3.8–3.13), macOS, Windows, Rocky Linux 9, and
  Debian bookworm arm64. It includes an emulated BeeOND/Slurm site, the
  notebook, packaging, and a wheel smoke test.
- The unit test suite has 545 tests. A machine-checked tutorial coverage map
  links every task type and feature to lessons, examples, and tests.
- Manual live runs are recorded in `docs/performance/`:
  - ad-hoc providers on two Slurm sites and on macOS;
  - meta-task engines;
  - DAGonFS volume tasks with three frontends.

### Fixes found in live volume-task runs

- Command tasks can no longer write through a client volume reference (for
  example `/results` on the host). Such references to client and object
  volumes are refused.
- Preload volumes stage data through the DAGonFS socket client. Directories
  are listed without `stat`, and the staging helper no longer creates the
  preload root.

## 2.0.2

See the [GitHub release](https://github.com/DagOnStar/dagonstar/releases/tag/v2.0.2).
