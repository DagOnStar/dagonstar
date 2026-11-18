# Ad-hoc file systems: live evaluation, 16–18 November 2026

This record states, for each provider of `Workflow.create_adhoc_filesystem`,
whether it was exercised live, where, and with what result. Every live number
comes from `tools/benchmark_adhoc_filesystems.py`: a real DAGonStar workflow
starts the resource, one producer task writes deterministic files, parallel
reader tasks verify every byte by SHA-256, and the workflow stops the resource.
The plain scratch directory is measured with the same workflow as `local`.
Values are medians of three runs unless stated. The raw reports are in
[`raw/`](raw/) (home directories replaced by `~`).

## Summary

| Provider | Live evidence | Hosts |
|---|---|---|
| DAGonFS (FUSE3, native, preload) | yes: lifecycle, three frontends, byte verification | macOS 26.6 arm64 (macFUSE); PurpleJeans, 1 and 2 nodes |
| CAPIO | yes: lifecycle, interception, byte verification | PurpleJeans, 1 node |
| DynoStore | yes: put, exists, get, evict, workflow tasks | macOS 26.6 arm64, Docker Desktop |
| Hercules | yes, with the fixes in `tools/adhoc/hercules-a13da96-fixes.patch`: lifecycle, interception, byte verification | PurpleJeans, 1 and 2 nodes |
| BeeOND | no new run (no BeeOND or Docker on PurpleJeans) | earlier four-node production run of the BeeOND integration; CI emulation |

PurpleJeans: Rocky Linux 8 (kernel 4.18), 32 cores per node, Slurm partition
`low-wn`, Open MPI 4.1.4 (`gcc-12.2.1/ompi-4.1.4_nccl`), Python 3.11.

## DAGonFS

DAGonFS `development` with this change set's Python native client
(`python/dagonfs/native.py`). Client-server model; `mpirun` started the ranks.

macOS 26.6.2 arm64, 16 cores, macFUSE, 4 ranks (`--oversubscribe`),
16 x 4 MiB, 4 readers ([raw](raw/dagonfs_macos_2026-11-18.json)):

| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---:|---:|---:|---:|---:|
| local | 4.97 | 562.0 | 8573.9 | — | — |
| dagonfs-fuse3 | 5.55 | 363.3 | 4093.6 | 0.42 | 0.03 |
| dagonfs-native | 5.84 | 314.2 | 498.0 | 0.21 | 0.02 |
| dagonfs-preload | 5.50 | 360.0 | 1256.1 | 0.21 | 0.02 |

PurpleJeans, one node (job 19789), 4 ranks, 32 x 16 MiB, 8 readers
([raw](raw/purplejeans-dagonfs-1n-19789.json)):

| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---:|---:|---:|---:|---:|
| local | 16.34 | 257.1 | 2966.8 | — | — |
| dagonfs-fuse3 | 17.99 | 210.3 | 1972.9 | 0.30 | 0.17 |
| dagonfs-native | 18.79 | 195.0 | 1543.8 | 0.30 | 0.16 |
| dagonfs-preload | 18.44 | 211.5 | 1603.6 | 0.30 | 0.16 |

PurpleJeans, two nodes (job 19787, wn02–wn03), 8 ranks, 32 x 16 MiB,
8 readers ([raw](raw/purplejeans-dagonfs-2n-19787.json)):

| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---:|---:|---:|---:|---:|
| local | 16.61 | 256.7 | 2840.9 | — | — |
| dagonfs-fuse3 | 19.12 | 205.2 | 1733.3 | 0.70 | 0.27 |
| dagonfs-native | 19.02 | 190.3 | 1711.2 | 0.70 | 0.26 |
| dagonfs-preload | 19.37 | 205.8 | 1489.2 | 0.60 | 0.26 |

The local reference is the node's scratch directory (page cache included), so
the comparison bounds the cost of the in-memory distributed volume rather than
ranking storage media. The single-task native client on macOS reads through one
socket connection per reader, which explains its lower aggregate read rate
there. DAGonFS improvements made for this evaluation: a dependency-free Python
client of the native protocol with a command-line interface, readiness and
shutdown through the protocol in the Python volume helper, and macOS fixes to
the mounted test suite (`flock` layout). Three mounted-suite cases still fail
on macFUSE (FIFO open, `flock`/POSIX lock interaction, blocked-lock
interrupt); `docs/TESTING.md` in DAGonFS records them.

## CAPIO

CAPIO built from source on PurpleJeans (`capio_server`, `libcapio_posix.so`
with `libsyscall_intercept`), one server, no CAPIO-CL configuration
(`--no-config`). Job 20024, 32 x 16 MiB, 8 readers
([raw](raw/purplejeans-capio-1n-20024.json)):

| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---:|---:|---:|---:|---:|
| local | 16.35 | 257.6 | 2967.3 | — | — |
| capio | 18.10 | 263.1 | 2841.6 | 1.01 | 0.02 |

Two adapter defects were found live and fixed: the server must receive the
same `CAPIO_WORKFLOW_NAME` as its clients (otherwise the first intercepted
`open` waits forever; job 19791 was cancelled for this), and readiness is now
the server's "Server instance successfully started" log line rather than a
fixed delay. The library directory is prepended to `LD_LIBRARY_PATH` because
`libcapio_posix.so` loads `libsyscall_intercept.so.0` from it. An earlier
small run (job 19792, 4 x 2 MiB) is kept in [raw](raw/purplejeans-capio-1n-19792.json).

## Hercules

Hercules built from source on PurpleJeans at upstream commit `a13da96`
(`hercules_server`, `libhercules_posix.so`, UCX 1.15), configuration from
`conf/hercules.conf.sample` with `HERCULES_PATH` set to the source tree.

### As released: no usable deployment

| Job | Nodes | Host selection | Observation |
|---|---:|---|---|
| 19790 | 2 | Slurm (automatic) | `hercules start` reported `STATUS = OK`; the metadata server crashed and clients were refused on port 7500 |
| 20024, 20027 | 1 | Slurm (automatic) | no data server was started; `hercules start` still returned 0 |
| 20028 | 1 | Slurm, `UCX_TLS=tcp,self` | deployment did not finish within 15 minutes |
| 20039 | 1 | explicit `-m`/`-d` host files | the data server never registered; clients could not read the metadata host file |
| 20040 | 3 | Slurm (automatic) | deployment did not finish within 15 minutes |

In every DAGonStar run the adapter's `ready_command` kept the workflow from
running tasks against an absent file system.

### Diagnosis and fixes

The failures were reproduced in a held two-node allocation and diagnosed with
a debug build under `gdb`. The fixes are in
[`tools/adhoc/hercules-a13da96-fixes.patch`](../../tools/adhoc/hercules-a13da96-fixes.patch),
which applies cleanly to upstream `a13da96`:

1. **Metadata-server crash** (`src/workers.c`, `SETSERVER`). When a data
   server registers, the metadata server connects back to it on port `85000`
   (above 65535, so port 19464 on the wire) instead of the configured
   `DATA_PORT`, and its error path formats `new_imss.info.ips[...]` from an
   uninitialised structure (`SIGSEGV` in `stat_worker_helper`). Fixed: connect
   to `DATA_PORT`; report the request's own address on error.
2. **Reads past end of file** (`fuse/imss_posix_api.c`, `imss_sread`). Only the
   first block was clamped to the file size, so a 1 MiB `read` at the tail of a
   3 MB file returned 1 MiB, and a 4 MB `read` returned 4 MB. Fixed: clamp the
   request to the bytes remaining before the block loop.
3. **Placement** (`scripts/hercules`). Automatic Slurm placement puts data
   servers only on nodes after the metadata nodes, so one node started none;
   it now completes the list with the other allocated nodes (one data server
   per node). Explicit `-m`/`-d` files are now copied to the per-job host files
   that the per-job configuration names, which servers and clients read.
4. **Stop** (`scripts/hercules`, `scripts/check-servers.sh`). `stop` sent
   `SIGUSR1` to every `hercules_server` on a node, so a co-located metadata
   server stopped early and its status file was then deleted and awaited
   forever; it now signals only `hercules_server <type> <id>`. The server
   rewrites its status file in place, so a poll could read it empty and fail;
   `check-servers.sh` now waits (with a sleep instead of a busy loop) until
   the status is `OK` or `ERROR`. `stop -d FILE` deleted the stopped hosts from
   the user's `FILE`; it now works on a copy.

With the patch, a stand-alone start, client, stop cycle passed on one node
(automatic and explicit host files), on two nodes, and on two nodes with two
data servers: `cp`, `cat`, `stat`, `cmp`, `dd`, `mkdir`, listing, and nine
write/read chunk-size combinations (128 KiB to 4 MB) returned exactly the
written bytes, `hercules stop` returned 0, and no server was left running.

### DAGonStar workflows

The adapter needed one change found here: inside an allocation `stop` passes
only the per-job configuration (never the user's host files). Jobs 20054 (one
node, one data server) and 20056 (two nodes, two data servers), 32 x 16 MiB,
8 readers ([raw 1 node](raw/purplejeans-hercules-1n-20054.json),
[raw 2 nodes](raw/purplejeans-hercules-2n-20056.json)):

| Run | Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---|---:|---:|---:|---:|---:|
| 1 node | local | 16.37 | 257.8 | 2966.3 | — | — |
| 1 node | hercules | 25.54 | 196.0 | 2226.9 | 3.23 | 2.50 |
| 2 nodes | local | 16.47 | 258.0 | 2961.2 | — | — |
| 2 nodes | hercules | 26.06 | 193.8 | 2300.7 | 3.79 | 2.46 |

Start and stop (the deployment script's `srun` steps and status-file polling)
account for about 6 s of the 9 s difference in workflow time. For about a
minute, job 20054 overlapped with a job that was then cancelled and that used
the same `HERCULES_PATH/tmp`; its results agree with the
isolated job 20056. Hercules keeps server status files in that shared
directory without a job identifier, so concurrent deployments from one
Hercules tree are not supported.

## DynoStore

DynoStore `docker-compose.dev.yml` (gateway, authentication, metadata,
catalog, ten data containers) on Docker Desktop, macOS 26.6.2 arm64; the MySQL
5.7 image ran under amd64 emulation. The workflow attached to the running
gateway (no managed compose lifecycle). Each file is one object; 16 x 4 MiB,
4 readers ([raw](raw/dynostore_macos_2026-11-18.json)):

| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |
|---|---:|---:|---:|---:|---:|
| local | 4.94 | 607.3 | 8586.1 | — | — |
| dynostore | 18.54 | 6.9 | 59.7 | 0.01 | 0.00 |

A separate probe verified `put`, `exists`, `get` (SHA-256 identical),
`evict`, and `exists` returning false afterwards. The gateway erasure-codes
each upload into five chunks synchronously, so write throughput reflects that
work on one laptop, not a distributed deployment.

The live run found two adapter defects, both fixed with tests: the metadata
service answers `200 {"exists": false}` for absent objects (the adapter had
treated any 200 as present), and the catalog service accepts only keys of 32
to 256 letters, digits, or hyphens, while the gateway stores other keys before
failing (the adapter now refuses such keys before any request). The test
deployment also needed site steps outside DAGonStar: creating the metadata
tables from the service's SQLAlchemy models, registering the data containers
directly with the metadata service (the gateway posts to `/api/servers`, which
the FastAPI service does not route, and reports success regardless), setting
`ENABLE_KAGIO=false` (placement otherwise waits on an unreachable analytics
host), and patching, in the scratch clone only, the gateway's `DELETE` route
(wrong call signature) and the metadata `exists` route (unreachable
"not found" branch). These are upstream DynoStore defects as of this date.

## Interface overhead and limitations

Portable emulation (`examples/adhoc/portable.py`) and the unit tests run on
every platform without the external software; they verify binding, the task
environment, ordering, and cleanup, never that a provider ran. Live runs used
three repeats on shared nodes and one laptop; they are evidence
that the integration works and of its relative cost on those hosts, not
storage rankings. Multi-node CAPIO (one server per node through
`server_launcher`) was not run.
