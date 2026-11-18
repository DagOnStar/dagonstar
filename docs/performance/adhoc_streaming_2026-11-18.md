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

BeeOND was not available for these runs; BeeOND streaming is covered only by
the launcher-text unit tests.

In the two-node jobs the DAGonFS ranks and the Hercules servers span both
nodes (`mpirun --map-by node`, Hercules's Slurm steps), while the DAGonStar
tasks run as local batch tasks on the first node. Two-node results therefore
show streaming through a distributed file system, not producer and consumer on
different nodes.

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

In job 20200, the task whose process loaded the CAPIO and the Hercules
preload libraries together failed: `mkdir` of an existing directory outside
both prefixes returned `EINVAL`, so DAGonStar's input staging could not
proceed. The task that combined the DAGonFS preload library with CAPIO
passed. The two interception libraries are not composable in one process on
this system; DAGonStar does not limit how many resources a task uses, but
bind CAPIO and Hercules to different tasks. The cause inside the libraries was
not investigated.

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

- The Hercules script runs each server as a Slurm step with
  `--cpus-per-task=4` and its readiness check as a further step: with four
  CPUs in the allocation the check waited forever ("Requested nodes are
  busy"). `--ntasks-per-node=4 --cpus-per-task=4` worked.
- A CAPIO server killed with its job leaves its shared-memory files in
  `/dev/shm` (named after the CAPIO workflow); the next server with that name
  refuses to start. The job script removes the user's own leftovers first.
- `salloc` runs its command on the login node, where FUSE is unavailable;
  live checks were submitted with `sbatch`.
- DynoStore's `docker-compose.dev.yml` puts the gateway on port 8070 (8095 is
  its metadata service, which answers 404 to object requests), and an image
  rebuild after patching needs `up -d --build`.

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
`raw/purplejeans-stream-1n-20211-multivolume.json`.
