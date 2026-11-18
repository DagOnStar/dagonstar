# Ad-hoc file systems

DAGonStar provides one opt-in lifecycle interface for five ad-hoc storage
systems: DAGonFS, BeeOND, Hercules, CAPIO, and DynoStore. The storage software
remains separately installed; DAGonStar does not vendor, patch, or deploy its
dependencies. It owns only the invocation, readiness check, shutdown, and the
credential-free environment of the tasks bound to a resource. Workflows that do
not create a resource behave exactly as before.

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("analysis")
task = DagonTask(TaskType.BATCH, "analyse", 'cp input.dat "$DAGON_ADHOC_PATH/result.dat"')
workflow.add_task(task)

volume = workflow.create_adhoc_filesystem(
    "dagonfs", mountpoint="/scratch/dagonfs", ranks=4, executable="/opt/dagonfs/bin/dagonfs",
)
volume.bind(task)
workflow.run()
```

## Contract

`Workflow.create_adhoc_filesystem(provider, name="default", **options)` returns
a registered resource. Names are unique per workflow and may contain letters,
digits, `.`, `_`, and `-`. Every resource provides:

| Operation | Behaviour |
|---|---|
| `bind(task)` | Exposes the resource to the task; returns the task. |
| `start()` / `stop()` | Called by `Workflow.run()`: all resources start before the first task and stop in reverse order after the last one, also after a task failure or interruption. `start()` returns only when the resource is ready, and cleans up after a failed start. |
| `is_ready()` | Provider-specific readiness probe (see below). |
| `task_environment(task)` | Variables exported in the task's launcher. |
| `metadata()` | Credential-free description recorded in execution and FAIR metadata. |

Every bound task receives:

| Variable | Meaning |
|---|---|
| `DAGON_ADHOC_PROVIDER` | `dagonfs`, `beeond`, `hercules`, `capio`, or `dynostore` |
| `DAGON_ADHOC_NAME` | The resource name |
| `DAGON_ADHOC_PATH` | Where the task reaches the data (see access modes) |
| `DAGON_ADHOC_ACCESS` | `posix`, `preload`, `client`, or `object` |
| `DAGON_ADHOC_<NAME>_PATH`, `DAGON_ADHOC_<NAME>_ACCESS` | The same for one named resource (name upper-cased, other characters replaced by `_`), so a task bound to several resources can address each of them |

When a task is bound to several resources, the generic `DAGON_ADHOC_*`
variables refer to the last one bound. Resource variables never carry
credentials: a variable whose name looks like a token, secret, password, or key
is rejected.

The access mode tells a task how to use `DAGON_ADHOC_PATH`:

- `posix`: an ordinary mounted directory (DAGonFS FUSE3, BeeOND).
- `preload`: paths below `DAGON_ADHOC_PATH` are intercepted by a library in
  `LD_PRELOAD` (Hercules, CAPIO, DAGonFS preload); other paths are unaffected,
  and the interception applies only to dynamically linked programs.
- `client`: a client protocol is required (the DAGonFS native socket, used with
  `python -m dagonfs`).
- `object`: an object store addressed by keys in a catalog (DynoStore);
  `DAGON_ADHOC_PATH` is an informational `dynostore://server/catalog` URI.

## Providers

| Provider | Lifecycle run by DAGonStar | Ready when | Task access |
|---|---|---|---|
| `dagonfs` | `mpirun -np N … dagonfs --model M [--frontend F] -f ROOT`; stopped by unmounting (FUSE3) or a `SHUTDOWN` request (native, preload), then waited for | the FUSE mount exists, or the socket answers `STAT /` | `fuse3`: `DAGONFS_MOUNTPOINT`; `native`: `DAGONFS_SOCKET`; `preload`: `DAGONFS_SOCKET`, `DAGONFS_PRELOAD_ROOT`, and the preload variable |
| `beeond` | Delegated to the Slurm BeeOND support ([BeeOND](beeond.md)) | the holder job reports the mount | `DAGON_BEEOND`; `DAGON_ADHOC_PATH` is set to it inside the allocation |
| `hercules` | `hercules start [-m META -d DATA] -f CONF`, `hercules stop …` | the optional `ready_command` succeeds | `HERCULES_CONF`, `HERCULES_MOUNT_POINT`, `LD_PRELOAD`, optional `LD_LIBRARY_PATH` prefix |
| `capio` | `capio_server -c CONFIG` or `--no-config`, stopped with `SIGTERM` | the server log shows `ready_marker` (default `Server instance successfully started`) | `CAPIO_DIR`, `CAPIO_WORKFLOW_NAME`, `CAPIO_APP_NAME`, `LD_PRELOAD`, optional `LD_LIBRARY_PATH` prefix |
| `dynostore` | attach to a running gateway, or `docker compose -f FILE up -d` plus optional setup commands, and `down` afterwards | the gateway answers HTTP | `DYNOSTORE_SERVER`, `DYNOSTORE_URL`, `DYNOSTORE_CATALOG`, `DYNOSTORE_AUTH_VARIABLE` |

Process output (DAGonFS, CAPIO, Hercules) is written to
`<scratch_dir_base>/.adhoc-<provider>-<name>.log` unless `log=` is given.

### DAGonFS

```python
workflow.create_adhoc_filesystem(
    "dagonfs", name="ram", mountpoint=None, model="client-server", ranks=2,
    executable="dagonfs", mpirun="mpirun", mpirun_args=(), frontend="fuse3",
    preload_library=None, preload_root="/dagonfs", python_path=None, config=None,
    startup_timeout=30.0)
```

`frontend` selects how tasks reach the volume, following DAGonFS's
[frontends](https://github.com/DagOnStar/DAGonFS/blob/main/docs/FRONTENDS.md):

- `fuse3` (default) mounts `mountpoint` (client-server) or `mountpoint/<rank>`
  (peer-to-peer; tasks receive rank 0's mount). Needs FUSE on the host
  (`fusermount3`, or macFUSE on macOS).
- `native` serves a Unix socket at `mountpoint` (default
  `<scratch>/.dagonfs-<name>.sock`, at most 103 bytes). No kernel module is
  needed. Tasks move data with DAGonFS's standard-library client, which
  `python_path` (the `DAGonFS/python` directory) exports as `DAGONFS_PYTHON`:
  `PYTHONPATH="$DAGONFS_PYTHON" python3 -m dagonfs put local /run/local`.
- `preload` serves the same socket and exports `LD_PRELOAD` (Linux) or
  `DYLD_INSERT_LIBRARIES` (macOS) with `preload_library`, so ordinary file
  calls on absolute paths below `preload_root` reach the volume. The
  interposer does not cover `stat`, directory listing, `mmap`, or relative
  paths, and macOS ignores it for SIP-protected programs such as `/bin/cp`.

The native and preload frontends serve only client-server volumes. DAGonStar
checks readiness and stops these volumes through the DAGonFS native protocol
(version 2) without importing DAGonFS.

### CAPIO

```python
workflow.create_adhoc_filesystem(
    "capio", name="stream", directory=None, server="capio_server",
    library="libcapio_posix.so", library_dir=None, config=None, backend=None, backend_options=None,
    mem_only=False, workflow_name=None, app_names=None, server_args=(), server_launcher=())
```

CAPIO intercepts paths below `CAPIO_DIR` (default `<scratch>/.capio-<name>`,
created before the server starts). When `config` names a readable CAPIO-CL JSON
file, `CAPIO_WORKFLOW_NAME` is its `name`, and a task bound under a name that is
not an `IO_Graph` step is reported in the log; `app_names` maps DAGonStar task
names to CAPIO-CL step names. Without a configuration the server starts with
`--no-config`, and both the server and the tasks receive the DAGonStar workflow
name as `CAPIO_WORKFLOW_NAME`: the server names its shared-memory channels
after it, so a client with a different name waits indefinitely (observed on
PurpleJeans before this was enforced). `library_dir` (for example the installation's `lib64`) is
joined to a bare library name and prepended to `LD_LIBRARY_PATH`, because
`libcapio_posix.so` loads `libsyscall_intercept.so.0` from the same directory.
`backend`
and `backend_options` are passed as `--backend` and `--backend-options` (for
example `mtcl` and `TCP:7600@1000000`). CAPIO needs one server per node; inside
an allocation, `server_launcher=["srun", "--ntasks-per-node=1"]` starts them
with the same lifecycle (stopping the workflow resource signals `srun`, which
forwards the signal to the servers).

### Hercules

```python
workflow.create_adhoc_filesystem(
    "hercules", name="tiered", config="hercules.conf", launcher="hercules",
    library="libhercules_posix.so", library_dir=None, path=None,
    meta_hostfile=None, data_hostfile=None, client_hostfile=None, job_id=None,
    ready_command=None)
```

`hercules start` deploys the servers and returns. Inside a Slurm allocation the
Hercules script derives the hosts from the allocation and writes
`<config>_<SLURM_JOB_ID>`, which tasks receive as `HERCULES_CONF` (pass
`job_id` when the tasks run in an allocation other than the submitting
process's). Outside Slurm, pass both host files. The intercepted prefix is the
configuration's `MOUNT_POINT` (default `/mnt/hercules`). `library_dir` is
prepended to the task's `LD_LIBRARY_PATH` and joined to a bare library name.
The configuration's `HERCULES_PATH` must name the Hercules tree (the script
keeps its state in `HERCULES_PATH/tmp`). Hercules documents no readiness
command, and its script can return 0 after a failed deployment: give
`ready_command`, which runs with the task's preload environment, for example
`["ls", "/mnt/hercules/"]`, so that the workflow waits for the servers and fails
instead of running tasks against an absent file system.

`stop` runs `hercules stop -f <config>_<SLURM_JOB_ID>` inside an allocation:
the script does not derive the per-job configuration when stopping, and that
configuration already names the job's host files. The host files are passed to
`stop` only outside Slurm, because `hercules stop -d FILE` deletes the stopped
hosts from `FILE`.

**Required Hercules fixes.** Hercules at upstream commit `a13da96` (November
2026) cannot serve a workflow as released. The fixes, verified on a Slurm
cluster, are in
[`tools/adhoc/hercules-a13da96-fixes.patch`](../tools/adhoc/hercules-a13da96-fixes.patch);
apply them with `git apply` in the Hercules tree and rebuild. They are
proposed upstream in [arcos-uc3m-hercules/hercules#3](https://github.com/arcos-uc3m-hercules/hercules/pull/3)
(open as of 18 November 2026); drop the patch once they are released:

- the metadata server crashed when a data server registered (it connected to
  port 85000 instead of `DATA_PORT`, then formatted its error message from
  uninitialised memory);
- POSIX reads larger than one block returned bytes past end of file;
- one-node allocations started no data server, and explicit `-m`/`-d` host
  files under Slurm were never copied to the per-job host files that servers
  and clients read;
- `hercules stop` signalled every Hercules server on a node, read
  half-written status files as failures, and edited the user's `-d` file.

Hercules keeps its server status files in the shared `HERCULES_PATH/tmp`
without a job identifier, so run one Hercules deployment per Hercules tree at a
time. Live results are in the
[performance record](performance/adhoc_filesystems_2026-11-18.md).

### BeeOND

`beeond` accepts only Slurm tasks and delegates to the existing BeeOND volume
implementation (workflow scope). Its options are those of
`Workflow.create_beeond_volume`. Because the mount exists only inside the
allocation, the launcher sets `DAGON_ADHOC_PATH="$DAGON_BEEOND"` after the
BeeOND prologue. BeeOND tasks remain ineligible for scheduler-aware
pre-staging.

### DynoStore

```python
workflow.create_adhoc_filesystem(
    "dynostore", name="objects", server=None, catalog=None, token_env="DYNOSTORE_TOKEN",
    compose_file=None, compose_project=None, setup_commands=(), docker="docker",
    startup_timeout=120.0, request_timeout=60.0, resiliency=1)
```

DynoStore is an object store, not a file system: it has no mount, and tasks
address objects by key within a catalog (default: the workflow name) through the
`dynostore` CLI or Python client. `server` defaults to the `host` and `port` of
the `[dynostore]` section of `dagon.ini` (the workflow-wide mover described in
[DynoStore examples](../examples/dynostore/README.md)), else `127.0.0.1:8095`.
With `compose_file`, the workflow runs `docker compose up -d`, the
`setup_commands` (for example the deployment's migration script), waits for the
gateway, and runs `docker compose down` at the end; without it, DAGonStar only
checks that the gateway answers.

The resource also offers `put(local, key=None)`, `get(key, local)`,
`exists(key)`, and `evict(key)` for workflow scripts. They follow the REST
routes of the DynoStore gateway (`POST /metadata`, `PUT /upload`,
`GET /storage`, `GET /storage/.../exists`, `DELETE /storage`) and its object
encoding (zlib-compressed pickled bytes). Objects are decoded without
unpickling: the stream must be a single bytes value, so a malicious gateway
cannot execute code in the task. Encrypted objects are refused; use the
`dynostore` client for them. Object keys must be 32 to 256 letters, digits, or
hyphens, which is what the DynoStore catalog service accepts; the default key
is a UUID, and other keys are refused before any request is sent. `exists`
honours the service's `{"exists": false}` answer as well as HTTP 404.

Bound tasks receive `DYNOSTORE_SERVER` (`host:port`), `DYNOSTORE_URL`,
`DYNOSTORE_CATALOG`, and `DYNOSTORE_AUTH_VARIABLE`, the *name* of the variable
holding the user token. The token itself is read from that variable only
inside `put`, `get`, `exists`, and `evict`; it is never exported to tasks by
DAGonStar, logged, included in error messages (it is a URL path segment), or
recorded in metadata. A task that has the token in its own environment can use
the same client from the command line:

```bash
python -m dagon.adhoc dynostore put result.dat "$KEY"   # prints the key
python -m dagon.adhoc dynostore exists "$KEY"           # exit 0 yes, 1 no
python -m dagon.adhoc dynostore get "$KEY" copy.dat
python -m dagon.adhoc dynostore evict "$KEY"
```

or `DynoStoreClient.from_environment()` in Python. Tasks that call the
`dynostore` CLI authenticate with the CLI's own token file.

Setup commands run in the compose file's directory with
`DYNOSTORE_COMPOSE_FILE` (absolute path) and, when `compose_project` is set,
`DYNOSTORE_PROJECT` in their environment, so DynoStore's deployment scripts
address the same stack as DAGonStar. `docker compose down` keeps the named
volumes, so a stack initialised once (administrator, data containers) keeps
its user token across workflow runs; DAGonStar never creates users or tokens.

**Required DynoStore fixes.** DynoStore as released (commit `b9dedd7`, November 2026) cannot be deployed
from its `docker-compose.dev.yml` and README steps, and loses data integrity
on overwrite. [`tools/adhoc/dynostore-b9dedd7-fixes.patch`](../tools/adhoc/dynostore-b9dedd7-fixes.patch)
(apply with `git apply` in a DynoStore checkout at that commit; proposed
upstream in [dynostore/dynostore#15](https://github.com/dynostore/dynostore/pull/15),
open as of 18 November 2026; drop the patch once it is released) fixes:

1. The metadata service never creates its tables (it assumed Laravel
   migrations); it now creates them at start-up, waiting for MySQL.
   `configure_services.sh` called a removed PHP service; it now creates the
   schema idempotently.
2. The gateway registers data containers at `/api/servers`, which the
   metadata service does not route, and reports success regardless; it now
   uses `/servers` and propagates the status (also for `/statistic` and
   `/clean`). The metadata service rejected the numeric `memory`/`storage`
   the data containers send, and registration added a duplicate row on every
   run; both are fixed.
3. Data containers reported `storage: null` under Docker Desktop (no
   partition contains the working directory); they now fall back to the
   working directory's file system. Registration exits non-zero on failure,
   and `create_nodes.sh` retries.
4. KAGIO analytics and the replicator defaulted on and waited on a
   site-specific host; they now default off (`ENABLE_KAGIO=true`,
   `ENABLE_REPLICATOR=true`, and `KAGIO_API_BASE_URL` re-enable them).
5. `DELETE /storage/<user>/<key>` called the controller with the wrong
   arguments and without `await`; the metadata `exists` route never reached
   its "not found" branch.
6. A second `put` of an existing key kept the old chunk records, so `get`
   returned the **previous** object's bytes, and a key re-used after `evict`
   stayed marked removed. A re-put now deletes and forgets the old chunks and
   clears the removal flag; a live key owned by another user is refused with
   409. `evict` deletes every chunk and replica, not only those a read uses.
7. The gateway stored metadata and data for keys the catalog service rejects;
   it now refuses keys outside `[0-9A-Za-z-]{32,256}` with 400 first.
   Catalog registration failures no longer raise a `TypeError`.
8. The deployment scripts and README named `docker-compose-dev.yml` and mixed
   compose files; they now use `docker-compose.dev.yml`, honour
   `DYNOSTORE_PROJECT` and `DYNOSTORE_COMPOSE_FILE`, and the README notes
   `DOCKER_DEFAULT_PLATFORM=linux/amd64` for MySQL 5.7 on arm64.

With the patch, a deployment follows the README alone:

```bash
export DYNOSTORE_PROJECT=dynostore          # the -p name, if any
docker compose -f docker-compose.dev.yml -p "$DYNOSTORE_PROJECT" up -d
bash configure_services.sh
(umask 077; bash generate_admin.sh | awk '{print $NF}' > ~/.dynostore-admin-token)
bash create_nodes.sh "$(cat ~/.dynostore-admin-token)"
```

The [performance record](performance/adhoc_filesystems_2026-11-18.md) gives
the live verification. Without fix 6, a workflow that re-uses an object key
silently reads stale data.

## Portable emulation

Under `Workflow(portable_emulation=True)` no provider is started and no
library is preloaded. POSIX and preload paths (`DAGON_ADHOC_PATH` and the
provider's path variables), and the DAGonFS native namespace, are redirected to
`<scratch_dir_base>/.adhoc-emulated/<name>`; DynoStore tasks receive
`DYNOSTORE_EMULATED_DIR`; tasks see `DAGON_ADHOC_EMULATED=1`. Emulation
verifies the binding and the dataflow, never that the external system ran.

Run `python examples/adhoc/portable.py` for a deterministic, network-free run
of all five providers.

## Interoperability

- **CWL.** Ad-hoc storage is execution behaviour and is absent from CWL v1.2
  command graphs. CWL export keeps the task commands and dependencies but does
  not provision MPI or FUSE daemons, Slurm allocations, Docker deployments, or
  preload libraries; a command referring to `$DAGON_ADHOC_PATH` needs that
  variable from the CWL runner's environment.
- **FAIR and execution metadata.** `task.get_execution_metadata()` lists the
  bound resources' `metadata()` (provider, name, access mode, path, and
  provider settings such as the DAGonFS model and frontend). This records that
  the resource was configured, not that data was published or validated.
- **JSON workflows and checkpoints.** Resources are created in the workflow
  script and are not serialized into workflow JSON. A checkpointed task skipped
  on resume does not need the resource, but the resource is still started; data
  left on a volatile volume by an earlier run is not preserved across runs.
- **Pre-staging.** Pre-staging moves `workflow://` inputs on the submission
  host; it does not stage into ad-hoc storage.

## Evidence

The unit tests (`tests/test_adhoc_filesystems.py`) run each provider's
lifecycle against local stand-ins: a process speaking the DAGonFS native
protocol, CAPIO and Hercules scripts, a `docker` recorder, and a loopback
DynoStore gateway. Live results are recorded in
[`docs/performance/adhoc_filesystems_2026-11-18.md`](performance/adhoc_filesystems_2026-11-18.md),
which states for every provider whether it was exercised live and where.

For reproducible measurements, run

```bash
python tools/benchmark_adhoc_filesystems.py --output results.json \
    --dagonfs /path/to/dagonfs --dagonfs-python /path/to/DAGonFS/python \
    --dagonfs-preload /path/to/libdagonfs_preload.so
```

Each live backend is measured with the same DAGonStar workflow (one producer,
parallel readers that verify every byte), next to the plain scratch directory.
Backends are measured only when named on the command line
(`--dagonfs`, `--capio-server`, `--hercules-config`, `--dynostore-server`
with the token in `$DYNOSTORE_TOKEN`), and the report records
which commands were available, so emulation is never presented as throughput.
