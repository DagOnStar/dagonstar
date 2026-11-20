# Volume tasks on a live DAGonFS volume (20 November 2026)

This record covers the first live runs of `TaskType.VOLUME`
([volume tasks](../volume_tasks.md)) on a deployed ad-hoc file system. The
runs were manual and are not part of CI.

## Host and software

| Item | Value |
|---|---|
| Host | macOS 26.6.2 arm64 workstation, 16 cores, macFUSE |
| DAGonFS | `development` at `229b13f`, client-server model, 2 MPI ranks (Open MPI 5.0.11, `--oversubscribe`) |
| Python | 3.12.10 |
| DAGonStar | `development` after `78455d0`, with the fixes listed below |

## Command

```bash
python examples/adhoc/volume_task.py --live dagonfs \
    --option executable=/path/to/DAGonFS/build/dagonfs --option ranks=2 \
    --option 'mpirun_args=["--oversubscribe"]' --option python_path=/path/to/DAGonFS/python \
    --option frontend=FRONTEND [--option preload_library=/path/to/libdagonfs_preload.dylib]
```

The example runs two workflows on real volumes. In `shared-volume`, `Abc`
creates volume `xyz` and stages `Prep`'s data in. Then:

- `Square` and `Cube` write into the volume;
- `Emit` streams to `Sum` through it;
- `Del` stages `results/` out and destroys it;
- `Report` reads `Del`'s copy.

In `collected-volume` no task destroys the volume, which is released by
reference counting. With the native frontend, which has no POSIX path, the
example uses stage-in, the stream, stage-out (`Report` compares the
round-tripped file with the original), and attached tasks.

## Results

| Frontend | Access | Result | Wall time (both workflows) |
|---|---|---|---|
| `fuse3` | posix | passed: 5 verified rows read back from the volume, stream total 15, `destroyed by Del`; `Tmp` released after its last user and before `Later` | 25.0 s |
| `native` | client | passed: stage-in and stage-out through the socket client, round-tripped file identical, stream total 15, both release paths | 26.0 s |
| `preload` | preload | passed: tasks wrote through the interposed library, staging through the socket client, stream total 15, both release paths | 23.9 s |

After every run, no DAGonFS process or mount remained. The existing live
example `examples/adhoc/streaming.py --live dagonfs` still passed with the
`fuse3` and `native` frontends.

## Defects found and fixed

1. **Command paths into client volumes.** With the native frontend, a command
   such as `mkdir -p workflow:///Abc/xyz/results` was rewritten to the
   namespace path `/results` and acted on the host's root directory. Command
   tasks that open paths inside a `client` or `object` volume are now refused
   when dependencies are made. The refusal names the alternatives:
   `?stream=<volume>`, `attach()`, and `stage_in`/`stage_out`.
   Covered by `tests.test_volume_task.DiscoveryTests.test_command_paths_into_client_and_object_volumes_are_refused`.
2. **Preload root.** The staging helper called `stat` and then `mkdir` on the
   preload root `/dagonfs`, which only the interposer knows. On macOS this
   failed with `EINVAL`. The root is now left to the provider.
3. **Directory stage-out under preload.** The DAGonFS preload library
   intercepts file calls but not `stat` or directory listings, so `results/`
   could not be staged out. For a preload volume, the helper now uses
   DAGonFS's socket client when it is importable (`python_path`). Otherwise it
   lists directories without `stat`.
4. **Helper store selection.** POSIX and preload volumes now open their store
   through the adapter's `open_volume_store`. The plain file store remains the
   fallback when the adapter cannot be imported by the helper.

## Observations

- macOS removes `DYLD_INSERT_LIBRARIES` from system binaries (`/bin/bash`,
  `/bin/cat`, `/bin/mkdir`). A preloaded volume must therefore be read and
  written by a program the library is loaded into. The example uses the
  running Python interpreter. Shell redirections reach it only on systems
  that preload into the shell. The earlier E4 record reports the same
  constraint for CAPIO and Hercules.
- A `workflow://` reference ends at the next space, so a reference inside
  `$(...)` needs a space before `)`. The example was corrected after an
  emitter read nothing in the native run.

## Not run

- CAPIO and Hercules volume tasks: no Linux site was available for this
  session.
- DynoStore volume tasks: the local Docker stack was running, but no user
  token (`DYNOSTORE_TOKEN`) was available.

These providers are covered by unit tests with stand-in stores and by
portable emulation only.
