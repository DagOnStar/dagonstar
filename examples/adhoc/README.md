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

`custom_adapter.py` is a complete adapter (`local-directory`) written outside
the `dagon` package and registered with `register_provider`; its run binds a
workflow-scope default volume and a task-scope volume to the same task:

```bash
python examples/adhoc/custom_adapter.py
```

`streaming.py` runs the workflow `A → {B1, C}`, `B1 → B2`, `{B2, C} → D` in
which only `B1 → B2` is a stream (`workflow:///B1/frames?stream`): B2 starts
while B1 runs and processes each frame as soon as it is published. It uses the
`local-directory` adapter by default, `--emulate PROVIDER` for portable
emulation of a built-in provider, or `--live PROVIDER --option KEY=VALUE` for a
deployed system (values are decoded as JSON):

```bash
python examples/adhoc/streaming.py
python examples/adhoc/streaming.py --emulate capio
python examples/adhoc/streaming.py --live dagonfs --option executable=/path/to/dagonfs \
    --option frontend=native --option python_path=/path/to/DAGonFS/python
DYNOSTORE_TOKEN=... python examples/adhoc/streaming.py --live dynostore \
    --option server=127.0.0.1:8070 --option catalog=streaming
```

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
`tools/benchmark_adhoc_streaming.py` compares the same producer/consumer
dataflow sequentially and as a stream on each backend, and
`tools/check_adhoc_multivolume.py` uses all named backends as volumes of one
workflow at the same time; both take the backend options above.
Measured results, with hosts, dates, and limitations, are recorded in
[`docs/performance/adhoc_filesystems_2026-11-18.md`](../../docs/performance/adhoc_filesystems_2026-11-18.md)
and [`docs/performance/adhoc_streaming_2026-11-18.md`](../../docs/performance/adhoc_streaming_2026-11-18.md).
