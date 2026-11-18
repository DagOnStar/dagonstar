# Ad-hoc file-system interface

`portable.py` binds one producer and one consumer to each of the five supported
providers (DAGonFS with the FUSE3 and native frontends, CAPIO, Hercules,
DynoStore, and BeeOND on Slurm tasks) under portable emulation, and checks that
each consumer reads what its producer wrote through the provider's path:

```bash
python examples/adhoc/portable.py
```

No external runtime is started: emulation redirects every path to
`<scratch>/.adhoc-emulated/<name>` and drops preload libraries, so the run is
not evidence that DAGonFS, BeeOND, Hercules, CAPIO, or DynoStore ran.

For live deployments, follow
[`docs/adhoc_filesystems.md`](../../docs/adhoc_filesystems.md) and provide the
site-specific executables, configuration files, host files, launcher arguments,
and mount or socket paths. To measure a live backend with the same
producer/readers workflow, run, for example:

```bash
python tools/benchmark_adhoc_filesystems.py --live-only \
    --dagonfs /path/to/DAGonFS/build/dagonfs \
    --dagonfs-python /path/to/DAGonFS/python \
    --dagonfs-preload /path/to/DAGonFS/build/libdagonfs_preload.so
```

Other live backends are named the same way: `--capio-server` with
`--capio-library`, `--hercules-config` with `--hercules-launcher`, and
`--dynostore-server HOST:PORT` with the user token in `$DYNOSTORE_TOKEN`.
Hercules needs the fixes in
[`tools/adhoc/hercules-a13da96-fixes.patch`](../../tools/adhoc/hercules-a13da96-fixes.patch)
applied to its source tree; DynoStore needs
[`tools/adhoc/dynostore-b9dedd7-fixes.patch`](../../tools/adhoc/dynostore-b9dedd7-fixes.patch)
for a deployment from its README steps.
Measured results, with hosts, dates, and limitations, are recorded in
[`docs/performance/adhoc_filesystems_2026-11-18.md`](../../docs/performance/adhoc_filesystems_2026-11-18.md).
