# CAPIO and Hercules on the E4 cluster: live verification (19 November 2026)

This record repeats the CAPIO and Hercules checks of the
[18 November records](adhoc_streaming_2026-11-18.md) on a second Slurm site,
with the `export=` option added to the
[ad-hoc interface](../adhoc_filesystems.md) since then. All runs were manual
and are not part of CI. The raw reports are in [`raw/`](raw/)
(`e4-hhcpu-1n-1090900-*.json`, home directories replaced by `~`).

## Host and software

| Host | System | Storage software |
|---|---|---|
| E4 cluster, partition `hhcpu`, node wn17 (56 cores; 8 CPUs and 16 GiB allocated, the rest held by other jobs), Rocky Linux 8.10, Slurm 23.11.3, Python 3.11 | local batch tasks inside a one-node Slurm job | CAPIO `91cd54d`; Hercules `a13da96` with `tools/adhoc/hercules-a13da96-fixes.patch` (applied cleanly). Both built with gcc-toolset-12, CMake Release, UCX 1.15 (`gcc-8.5.0/ucx-1.15.0`) |

The DAGonStar tree was the `development` branch at `915cd1b` plus the
then-uncommitted `export=` change, since committed as `9b02cbc`. Only one node of `hhcpu` had free CPUs, so
every run below is single-node; the two-node and cross-node results remain
those of PurpleJeans.

## Results (job 1090900, 20:26–20:32 UTC, unless stated)

| Check | CAPIO | Hercules |
|---|---|---|
| `examples/adhoc/streaming.py --live` (A, B1, B2, C, D; only B1 → B2 streams) | passed, first frame 4.59 s before B1 ended | passed, 5.58 s with the default UCX transports and 3.90 s with `UCX_TLS=tcp,self,sm` |
| Task-scope volume with `export="MYVOL"` | passed (`$MYVOL` = `DAGON_ADHOC_VOL_PATH` = the CAPIO directory; data verified; volume stopped after the task) | passed in job 1090904 (`$MYVOL=/mnt/hercules`; data verified; volume stopped) |
| Lifecycle benchmark, 16 × 8 MiB, 4 readers, byte-verified, median of 3 | workflow 6.72 s, write 474.1 MiB/s, read 4715.0 MiB/s, start 1.00 s | workflow 9.01 s, write 418.0 MiB/s, read 3863.7 MiB/s, start 2.73 s |
| Streaming benchmark, 16 × 1 MiB, 0.25 s work per item, median of 3 | stream 8.02 s against sequential 14.22 s; first item 0.01 s after it was published | stream 10.13 s against sequential 16.39 s; first item 0.02 s |
| `tools/check_adhoc_multivolume.py` with both | passed: the two volumes streamed concurrently, and the CAPIO/Hercules hop was split through a local file because the two preload libraries conflict | (same run) |

The local directory measured with the same workflow took 5.33 s (write
471.1 MiB/s, read 4969.3 MiB/s). The benchmark's "Real backend availability"
table lists CAPIO and Hercules as unavailable because their commands are not
on `PATH`; the live rows were measured with the explicit paths given on the
command line.

The A, B1, B2, C, D workflow written with an explicitly declared CAPIO resource
(`create_adhoc_filesystem("capio", ...)` bound to B1 and B2, B2 reading
`workflow:///B1/parts?stream --into parts-in`) passed three consecutive runs in
job 1090908: B2 staged all six parts while B1 ran, D received both branches,
and no CAPIO shared-memory file was left in `/dev/shm`.

Unlike on PurpleJeans (InfiniBand), the Hercules data server did not abort
on the UCX assertion with the default transports here; `UCX_TLS=tcp,self,sm`
was set for the later Hercules runs only to match the PurpleJeans procedure.

## Findings

- **Shell redirections bypass preload interception.** A task's own `>` and
  `<` are performed by the launcher shell, which starts before `LD_PRELOAD`
  is exported, so they are not intercepted. Writing `> "$MYVOL/data.txt"`
  failed on Hercules (`/mnt/hercules` does not exist on the node) and wrote
  the real CAPIO directory instead of going through CAPIO. Programs started
  by the command (`cp`, `tee`, `dd`, `cat`, Python) are intercepted.
- **Hercules lost data written by GNU `tee`.** `seq 1 1000 | tee FILE`
  returned 0 and created the file, but `cat` and `cp` then read 0 bytes;
  `cp` and `dd` of the same data were read back correctly (job 1090903). The
  cause was not investigated further; `tee` writes through C stdio, which
  a library that interposes only `write` may not see.
- **`cp` into CAPIO did not return.** With CAPIO preloaded, `cp FILE
  "$CAPIO_DIR/…"` blocked until it was killed (30 s, 120 s, and 900 s
  limits, jobs 1090904, 1090906, 1090907), while `tee` and `dd` of the same
  file succeeded and were read back correctly. The killed servers left their
  shared-memory files in `/dev/shm`; remove them (own files only) before the
  next run with the same workflow name.
- **Portable emulation accepted references that live runs reject.** The first
  version of the explicit-CAPIO workflow read `$(cat workflow:///A/ids.txt)`.
  Live staging ends a `workflow://` reference at the next space, as
  documented in [the workflow schema](../the_workflow_schema.md#whitespace-boundary-rule),
  so it looked for `ids.txt)`, B1 published nothing, and B2 received an empty
  stream; under portable emulation the reference ends at `)` too and the
  same workflow passed. Write a space before `)` (as `examples/adhoc/streaming.py`
  does). Since commit `47d0058`, portable emulation ends a reference where
  live runs do and fails such a task before its command runs.
