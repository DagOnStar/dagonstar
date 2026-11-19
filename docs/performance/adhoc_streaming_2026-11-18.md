# Ad-hoc streaming, multiple volumes, and adapters: live verification (18 November 2026)

This record covers the inter-task streaming (`workflow:///P/path?stream`), the
task and workflow scopes, several simultaneous volumes, and the adapter
registry described in [Ad-hoc file systems](../adhoc_filesystems.md). It
complements [the lifecycle record](adhoc_filesystems_2026-11-18.md). All runs
were manual; none is part of CI. Raw results are in [`raw/`](raw/).

## Hosts and software

| Host | System | Storage software |
|---|---|---|
| MacBook Pro (`MacBook-Pro-410`), 16 cores, macOS 26.6.2 arm64, Python 3.12.10 | local batch tasks | DAGonFS (development branch with the preload fix below; macFUSE, Open MPI from Homebrew), DynoStore `b9dedd7` with `tools/adhoc/dynostore-b9dedd7-fixes.patch` (Docker Desktop, `docker-compose.dev.yml`, gateway on port 8070) |
| PurpleJeans (`wn01`, `wn02`), Slurm partition `low-wn`, Linux, `gcc-12.2.1/ompi-4.1.4_nccl` | local batch tasks inside a Slurm job (`--ntasks-per-node=4 --cpus-per-task=4`) | DAGonFS (same fix), CAPIO, Hercules `a13da96` with `tools/adhoc/hercules-a13da96-fixes.patch` (including the new standard-output fix) |

No real BeeOND deployment was available. BeeOND streaming is covered by the
launcher-text unit tests and by the `stream` scenario of
`tools/ci_beeond_slurm.py`, which runs on the CI's emulated BeeOND site.

In the two-node jobs of the tables below, the DAGonFS ranks and the Hercules
servers span both nodes (`mpirun --map-by node`, Hercules's Slurm steps),
while the DAGonStar tasks run as local batch tasks on the first node. Those
results therefore show streaming through a distributed file system. Runs with
producer and consumer on different nodes are reported
[separately](#producer-and-consumer-on-different-nodes).

## The A, B1, B2, C, D workflow

`python examples/adhoc/streaming.py --live PROVIDER --option …` runs
`A → {B1, C}`, `B1 → B2`, `{B2, C} → D`, with only `B1 → B2` streaming. B1
publishes eight frames 0.25 s apart; the check requires every frame to arrive
verified and in order, B2's first arrival to precede B1's end, and D to see
both branches.

| Host | Resource | Nodes | Result | First frame before B1 ended |
|---|---|---:|---|---:|
| macOS | `local-directory` adapter (`examples/adhoc/custom_adapter.py`) | 1 | passed | 2.9 s |
| macOS | DAGonFS `fuse3` | 1 | passed | 1.7 s |
| macOS | DAGonFS `native` | 1 | passed | 2.8 s |
| macOS | DAGonFS `preload` | 1 | passed | 3.0 s |
| macOS | DynoStore | 1 | passed | 16.1 s |
| PurpleJeans | DAGonFS `native` (job 20200 / 20201) | 1 / 2 | passed | 3.2 s / 3.0 s |
| PurpleJeans | CAPIO with generated CAPIO-CL rules (job 20200, and three repeats) | 1 | passed | 5.5 s (5.6–6.2 s) |
| PurpleJeans | Hercules (job 20200 / 20201) | 1 / 2 | passed | 8.2 s / 8.8 s |

DynoStore's large margin reflects its slow object puts (B1 takes longer to
publish), not a faster consumer.

## Sequential versus streaming dataflow

`tools/benchmark_adhoc_streaming.py --items 16 --item-kib 1024 --delay 0.25
--repeats 3` runs a producer P (0.25 s of simulated work before each 1 MiB
item) and a consumer C (SHA-256 verification and 0.25 s of work after each
item), once with an ordinary `workflow://` edge and once with a stream, on the
same resource. Medians of three runs; times in seconds. *Pipeline* is P's
first instruction to C's last; *C starts* is the delay between the starts of P
and C; *first item* is the time from P publishing item 1 to C holding it
verified.

| Host, nodes | Backend | Pipeline sequential | Pipeline stream | C starts (seq / stream) | First item (seq / stream) |
|---|---|---:|---:|---:|---:|
| macOS, 1 | local | 10.58 | 4.60 | 6.43 / 0.19 | 6.17 / 0.03 |
| macOS, 1 | DAGonFS fuse3 | 10.57 | 4.61 | 6.42 / 0.20 | 6.16 / 0.09 |
| macOS, 1 | DAGonFS native | 10.70 | 4.63 | 6.46 / 0.18 | 6.21 / 0.06 |
| macOS, 1 | DAGonFS preload | 10.62 | 4.61 | 6.44 / 0.19 | 6.18 / 0.08 |
| macOS, 1 | DynoStore | 22.33 | 20.93 | 14.70 / 0.18 | 14.13 / 0.37 |
| PurpleJeans, 1 | local | 10.51 | 4.61 | 6.38 / 0.31 | 6.13 / 0.05 |
| PurpleJeans, 1 | DAGonFS fuse3 | 10.60 | 4.67 | 6.43 / 0.33 | 6.19 / 0.09 |
| PurpleJeans, 1 | DAGonFS native | 10.67 | 4.66 | 6.50 / 0.32 | 6.25 / 0.05 |
| PurpleJeans, 1 | DAGonFS preload | 10.67 | 4.63 | 6.50 / 0.26 | 6.26 / 0.03 |
| PurpleJeans, 1 | CAPIO | 11.17 | 4.80 | 7.03 / 0.28 | 6.79 / 0.03 |
| PurpleJeans, 1 | Hercules | 12.10 | 5.40 | 7.92 / 0.28 | 7.67 / 0.05 |
| PurpleJeans, 2 | local | 10.58 | 4.65 | 6.44 / 0.32 | 6.20 / 0.10 |
| PurpleJeans, 2 | DAGonFS fuse3 | 10.67 | 4.68 | 6.51 / 0.31 | 6.24 / 0.03 |
| PurpleJeans, 2 | DAGonFS native | 10.73 | 4.81 | 6.55 / 0.46 | 6.27 / 0.21 |
| PurpleJeans, 2 | DAGonFS preload | 10.72 | 4.63 | 6.55 / 0.30 | 6.28 / 0.04 |
| PurpleJeans, 2 | Hercules | 12.01 | 5.36 | 7.83 / 0.41 | 7.58 / 0.13 |

Observations:

- With the work split evenly between P and C (4 s each), a stream overlaps
  them: the pipeline falls from about 10.6 s to about 4.6 s on every
  file-based backend. That is below the 8.2 s that P and C need back to back,
  because C works while P is still running. Sequential runs also include
  DAGonStar's orchestration gap between tasks (C starts about 6.4 s after P,
  of which about 4.1 s is P's run), which the stream removes.
- A published item reaches the consumer in 0.03–0.21 s; the reader's polling
  backs off to at most 0.2 s.
- DynoStore gains little (22.3 s to 20.9 s) because each object put and get
  takes much longer than the simulated work, so the transfer, not the
  computation, bounds the pipeline. Streaming over an object store pays off
  only when items are large compared with the request latency.
- The throughput columns of the raw files (`producer_mib_s`,
  `consumer_mib_s`) subtract the simulated work; in stream mode the
  consumer's figure also includes waiting for the producer, so it is not a
  storage throughput. `work_seconds` likewise counts that waiting twice in
  stream mode.

## Several volumes in one workflow

`tools/check_adhoc_multivolume.py` makes every named backend one
workflow-scope volume of a single workflow, adds a task-scope volume, passes a
payload through all volumes with hop tasks bound to two consecutive volumes
(verified by SHA-256 at each hop), and streams four items over every streaming
volume at the same time.

| Host, job | Volumes | Result |
|---|---|---|
| macOS | DAGonFS fuse3, native, preload, DynoStore, task-scope directory | passed, 4 concurrent streams |
| PurpleJeans 1 node, job 20211 (`--order capio,dagonfs-fuse3,dagonfs-native,dagonfs-preload,hercules`) | CAPIO, DAGonFS fuse3, native, preload, Hercules, task-scope directory | passed in 25.1 s, 5 concurrent streams |
| PurpleJeans 2 nodes, job 20201 | DAGonFS fuse3, native, preload, Hercules, task-scope directory | passed in 22.5 s, 4 concurrent streams |
| PurpleJeans 1 node, job 20200 (default order) | as job 20211 | failed at the one task bound to **both** CAPIO and Hercules |
| PurpleJeans 1 node, job 20290 (default order, after the fix below) | as job 20211 | passed in 33.3 s, 5 concurrent streams; the CAPIO → Hercules hop ran as two tasks |

In job 20200, the task whose process loaded the CAPIO and the Hercules
preload libraries together failed: `mkdir` of an existing directory outside
both prefixes returned `EINVAL`, so DAGonStar's input staging could not
proceed. The task that combined the DAGonFS preload library with CAPIO
passed. A follow-up probe (one task bound to both, each command run with each
library order) showed that the pair does not work in one process at all:
with Hercules first even `/bin/true` hung, with CAPIO first it crashed. The
cause inside the libraries was not investigated. CAPIO and Hercules now
declare each other in `preload_conflicts`, so binding both to one task fails
when the workflow is built. `tools/check_adhoc_multivolume.py` splits such a
hop into a task that copies the payload out of the first volume and a task
that copies it into the second, and job 20290 passed with the default order.

## Producer and consumer on different nodes

Run 19 November 2026 (UTC) on PurpleJeans, two nodes (wn01, wn02), with
`python examples/adhoc/streaming.py --scratch <shared directory> --wrap
"B1=srun --overlap -N1 -n1 -c1 -w wn01" --wrap "B2=srun --overlap -N1 -n1 -c1
-w wn02" --live …`. DAGonStar ran on wn01; B1's commands ran on wn01 and B2's
on wn02 (recorded by each task). The node clocks were compared for the
first-arrival check. Log excerpts are in
[`raw/purplejeans-crossnode-2026-11-19.txt`](raw/purplejeans-crossnode-2026-11-19.txt).

| Job | Resource | Result | First frame before B1 ended |
|---|---|---|---:|
| 20289 | DAGonFS `fuse3` peer-to-peer, two ranks (one per node) | passed | 4.1 s |
| 20314 | Hercules, default UCX transports | streaming passed; `hercules stop` failed | 16.3 s |
| 20316 | Hercules, `UCX_TLS=^ud` | as 20314 | 15.8 s |
| 20318 | Hercules, `UCX_TLS=tcp,self,sm` | passed, clean stop | 6.8 s |

For DAGonFS peer-to-peer, B2 reached the stream through wn02's rank-1 mount:
rank 0's mount path also existed on wn02, as an empty directory, so a
consumer that used the recorded path there would have waited forever. That
DAGonFS's `native` and `preload` frontends are reachable only on the node of
rank 0 is a property of their Unix socket; they were not run across nodes.

With Hercules, the data server on wn02, the node of the consumer, aborted on a
UCX assertion (`ud_ep.c:267`, in `uct_ud_ep_deferred_timeout_handler` called
from `hercules_ucx_server`) after the stream had been fully consumed;
`hercules stop` then found no server to stop and DAGonStar reported the stop
failure. Excluding UCX's UD transport did not help; `UCX_TLS=tcp,self,sm`
did. Earlier two-node runs, where no client ran on the data server's node, had
not shown it. The UCX or Hercules cause was not investigated. Note that UCX
prints its warnings (for example about an unknown `UCX_*` variable) on the
standard output of intercepted processes.

## Defects found and fixed

- **DAGonStar.** The stream close in the launcher epilogue was skipped when a
  command left the launcher early (for example `|| exit 1` inside a loop); an
  `EXIT` trap now ends the streams. A host-side close that raised a store error
  killed the producer's task thread before the producer-ended signal was
  written, so the consumer waited forever (observed with an unreachable
  DynoStore gateway); the signal is now written first and the host-side close
  cannot raise. Benchmark repeats reused a CAPIO workflow name and tripped
  CAPIO's shared-memory canary after an earlier run was killed; the tools now
  use unique names.
- **DAGonFS.** The preload interposer used descriptor 0 as its free-slot
  marker, so reading stdin or a local file that received descriptor 0 was sent
  to DAGonFS (`tee: read error`, `touch: failed to close`). Fixed in DAGonFS
  commit `229b13f` (development branch) with a regression check in
  `tests/native_frontend.py`; it was seen on Linux only.
- **Hercules.** Every intercepted process printed its prefetch setting on
  standard output; added to `tools/adhoc/hercules-a13da96-fixes.patch`, which
  still applies to `a13da96`.

## Site notes

- The Hercules script ran each server as a Slurm step with
  `--cpus-per-task=4` and its readiness check as a further step: with four
  CPUs in the allocation the check waited forever ("Requested nodes are
  busy"), and fewer than four CPUs per node were refused. The fixes patch now
  runs every step with `--overlap` and bounds the server CPUs by the
  allocation (`HERCULES_SERVER_CPUS`). Afterwards the streaming example passed
  with four CPUs in all (B2's first frame 5.3 s early) and with one CPU and
  `--mem=8G` (20.4 s early); with one CPU and the site's 1 GiB per CPU the
  servers were killed for lack of memory. Two Hercules deployments on one
  node collide on Hercules's fixed ports (`HERCULES_ERR_DISPATCHER_BIND`).
- A CAPIO server killed with its job leaves its shared-memory files in
  `/dev/shm` (named after the CAPIO workflow); the next server with that name
  refuses to start. The job script removes the user's own leftovers first.
- `salloc` runs its command on the login node, where FUSE is unavailable;
  live checks were submitted with `sbatch`.
- DynoStore's `docker-compose.dev.yml` puts the gateway on port 8070 (8095 is
  its metadata service, which answers 404 to object requests), and an image
  rebuild after patching needs `up -d --build`. DAGonStar now recognises the
  metadata service by its OpenAPI title and fails the start with the gateway
  ports in the message (checked against the local stack on both ports), and
  `compose_build=True` runs `up -d --build`.

## Reproduce

```bash
python examples/adhoc/streaming.py --live dagonfs --option executable=$DAGONFS/build/dagonfs \
    --option frontend=native --option python_path=$DAGONFS/python
python tools/benchmark_adhoc_streaming.py --items 16 --item-kib 1024 --delay 0.25 --repeats 3 \
    --dagonfs $DAGONFS/build/dagonfs --dagonfs-python $DAGONFS/python \
    --dagonfs-preload $DAGONFS/build/libdagonfs_preload.so --output streaming.json
python tools/check_adhoc_multivolume.py --dagonfs $DAGONFS/build/dagonfs \
    --dagonfs-frontends fuse3,native,preload --dagonfs-python $DAGONFS/python \
    --dagonfs-preload $DAGONFS/build/libdagonfs_preload.so --output multivolume.json
```

CAPIO, Hercules, and DynoStore are added with the options of
`tools/benchmark_adhoc_filesystems.py` (`--capio-server`, `--hercules-config`,
`--dynostore-server` with the token in `$DYNOSTORE_TOKEN`).

Raw files: `raw/streaming_macos_2026-11-18.json`,
`raw/multivolume_macos_2026-11-18.json`, and
`raw/purplejeans-stream-{1n-20200,2n-20201}-*.json`,
`raw/purplejeans-stream-1n-20211-multivolume.json`,
`raw/purplejeans-stream-1n-20290-multivolume.json`, and
`raw/purplejeans-crossnode-2026-11-19.txt`.
