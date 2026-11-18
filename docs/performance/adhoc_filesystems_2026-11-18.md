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
| Hercules | attempted; Hercules did not reach a usable state, and the adapter's readiness check failed each run cleanly | PurpleJeans, 1 and 3 nodes |
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

Hercules built from source on PurpleJeans (`hercules_server`,
`libhercules_posix.so`, UCX 1.15), configuration from
`conf/hercules.conf.sample` with `HERCULES_PATH` set to the source tree. No
attempt produced a usable file system:

| Job | Nodes | Host selection | Observation |
|---|---:|---|---|
| 19790 | 2 | Slurm (automatic) | `hercules start` reported `STATUS = OK`; the metadata server crashed (segmentation fault in its UCX stat worker) and clients were refused on port 7500 |
| 20024, 20027 | 1 | Slurm (automatic) | the script places data servers only on nodes after the metadata nodes, so a one-node allocation starts none; `hercules start` still returned 0 and clients failed to create their resources |
| 20028 | 1 | Slurm, `UCX_TLS=tcp,self` | deployment did not finish within the 15-minute limit |
| 20039 | 1 | explicit `-m`/`-d` host files (same node) | the data server never registered (`Waiting for server -1`); `hercules start` returned 1 |
| 20040 | 3 | Slurm (automatic) | deployment did not finish within the 15-minute limit |

In every DAGonStar run the `ready_command` (a listing of the mount point under
the Hercules preload library) kept the workflow from running tasks against an
absent file system, and the workflow failed with the provider log. Two adapter
improvements came from these runs: `hercules stop` is now given the per-job
configuration (`<config>_<SLURM_JOB_ID>`), because the script does not derive
it when stopping, and the benchmark keeps the last 40 kB of a failed
provider's log. Whether the failures come from this site's UCX and Slurm setup
or from Hercules itself was not determined; no Hercules throughput is claimed.

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
`server_launcher`) and multi-node Hercules were not run.
