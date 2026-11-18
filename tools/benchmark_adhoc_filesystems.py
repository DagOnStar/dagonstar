#!/usr/bin/env python3
"""Benchmark DAGonStar's common ad-hoc file-system interface.

The default run is deterministic and needs no external service.  It measures
workflow overhead with each provider in portable emulation and three verified
I/O patterns on the local scratch filesystem.  Availability records prevent an
emulated run from being mistaken for real backend throughput.

Live backends are measured only when their software is named explicitly, for
example ``--dagonfs /path/to/dagonfs --dagonfs-python /path/to/DAGonFS/python``
or ``--capio-server capio_server --capio-library libcapio_posix.so``, or
``--dynostore-server HOST:PORT`` with the user token in ``$DYNOSTORE_TOKEN``.  Each live
run is a real DAGonStar workflow: the resource is started by the workflow, one
producer task writes ``--live-files`` files through ``$DAGON_ADHOC_PATH`` (or
the DAGonFS socket client, or DynoStore objects), ``--live-readers`` parallel tasks read and verify
every byte, and the workflow stops the resource.  The plain scratch directory
is measured with the same workflow as the ``local`` reference.
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


IO_TASK = r'''
import hashlib, json, os, random, sys, time
mode, root, files, size, result = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
access = os.environ.get("DAGON_ADHOC_ACCESS", "posix")
if access == "object":
    # DynoStore has no namespace: each file is one object in the catalog.
    from dagon.adhoc import DynoStoreClient
    client = DynoStoreClient.from_environment()
    def mkdir(path):
        pass
    def write(path, data):
        client.put_bytes(data, hashlib.sha256(path.encode()).hexdigest())
    def read(path):
        return client.get_bytes(hashlib.sha256(path.encode()).hexdigest())
elif access == "client":
    sys.path.insert(0, os.environ["DAGONFS_PYTHON"])
    from dagonfs.native import Client
    client = Client(os.environ["DAGONFS_SOCKET"]).connect()
    def mkdir(path):
        client.makedirs(path)
    def write(path, data):
        client.write_bytes(path, data)
    def read(path):
        return client.read_bytes(path)
else:
    def mkdir(path):
        try:
            os.mkdir(path)      # the DAGonFS interposer does not intercept stat
        except FileExistsError:
            pass
    def write(path, data):
        with open(path, "wb", buffering=0) as stream:
            view = memoryview(data)
            while view:
                view = view[stream.write(view):]
    def read(path):
        with open(path, "rb", buffering=0) as stream:
            chunks = []
            while True:
                chunk = stream.read(4 << 20)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
def payload(index):
    return random.Random(index).randbytes(size)
expected = [hashlib.sha256(payload(i)).hexdigest() for i in range(files)] if mode == "read" else None
started = time.perf_counter()
if mode == "write":
    mkdir(root)
    for index in range(files):
        write("%s/f%04d.bin" % (root, index), payload(index))
else:
    for index in range(files):
        if hashlib.sha256(read("%s/f%04d.bin" % (root, index))).hexdigest() != expected[index]:
            sys.exit("verification failed for file %d" % index)
seconds = time.perf_counter() - started
with open(result, "w") as stream:
    json.dump({"mode": mode, "seconds": seconds, "bytes": files * size}, stream)
'''


PROVIDERS = {
    "dagonfs": ("dagonfs", "mpirun"),
    "beeond": ("sbatch",),
    "hercules": ("hercules",),
    "capio": ("capio_server",),
    "dynostore": ("docker",),
}


def summary(values):
    ordered = sorted(values)
    return {"samples": values, "median": statistics.median(values),
            "minimum": ordered[0], "maximum": ordered[-1]}


def workflow_config(scratch):
    return {"batch": {"scratch_dir_base": str(scratch), "run_base": "", "threads": "16"},
            "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}


def interface_once(provider, tasks, scratch):
    workflow = Workflow("adhoc-performance", config=workflow_config(scratch),
                        max_threads=min(tasks, 16), portable_emulation=True)
    if provider == "baseline":
        filesystem = None
    elif provider == "dagonfs":
        filesystem = workflow.create_adhoc_filesystem("dagonfs", mountpoint=str(scratch / "dagonfs"))
    elif provider == "beeond":
        filesystem = workflow.create_adhoc_filesystem("beeond")
    elif provider == "hercules":
        filesystem = workflow.create_adhoc_filesystem("hercules", config="benchmark-hercules.conf")
    elif provider == "dynostore":
        filesystem = workflow.create_adhoc_filesystem("dynostore", catalog="benchmark")
    else:
        filesystem = workflow.create_adhoc_filesystem("capio", directory=str(scratch / "capio"))
    for index in range(tasks):
        task_type = TaskType.SLURM if provider == "beeond" else TaskType.BATCH
        task = DagonTask(task_type, "task-%03d" % index, "true")
        workflow.add_task(task)
        if filesystem is not None:
            filesystem.bind(task)
    started = time.perf_counter()
    workflow.run()
    elapsed = time.perf_counter() - started
    if any(task.result.get("code") for task in workflow.tasks):
        raise RuntimeError("interface benchmark task failed")
    return elapsed


def sequential_io(root, size_mib):
    target = root / "sequential.bin"
    block = bytes(1024 * 1024)
    started = time.perf_counter()
    with target.open("wb", buffering=1024 * 1024) as stream:
        for _ in range(size_mib):
            stream.write(block)
        stream.flush()
        os.fsync(stream.fileno())
    write_seconds = time.perf_counter() - started
    started = time.perf_counter()
    read = 0
    with target.open("rb", buffering=1024 * 1024) as stream:
        while True:
            data = stream.read(len(block))
            if not data:
                break
            read += len(data)
    read_seconds = time.perf_counter() - started
    if read != size_mib * 1024 * 1024:
        raise RuntimeError("sequential read verification failed")
    target.unlink()
    return {"size_mib": size_mib, "write_seconds": write_seconds, "read_seconds": read_seconds,
            "write_mib_s": size_mib / write_seconds, "read_mib_s": size_mib / read_seconds}


def small_file_io(root, files, bytes_per_file):
    directory = root / "small"
    directory.mkdir()
    payload = b"x" * bytes_per_file
    started = time.perf_counter()
    for index in range(files):
        (directory / ("file-%06d" % index)).write_bytes(payload)
    create_seconds = time.perf_counter() - started
    started = time.perf_counter()
    total = sum(path.stat().st_size for path in directory.iterdir())
    scan_seconds = time.perf_counter() - started
    if total != files * bytes_per_file:
        raise RuntimeError("small-file verification failed")
    shutil.rmtree(directory)
    return {"files": files, "bytes_per_file": bytes_per_file,
            "create_seconds": create_seconds, "scan_seconds": scan_seconds,
            "create_files_s": files / create_seconds, "scan_files_s": files / scan_seconds}


def copy_io(root, size_mib, copies):
    source = root / "source.bin"
    source.write_bytes(bytes(size_mib * 1024 * 1024))
    started = time.perf_counter()
    destinations = []
    for index in range(copies):
        destination = root / ("copy-%02d.bin" % index)
        shutil.copyfile(source, destination)
        destinations.append(destination)
    seconds = time.perf_counter() - started
    expected = source.stat().st_size
    if any(path.stat().st_size != expected for path in destinations):
        raise RuntimeError("fan-out copy verification failed")
    source.unlink()
    for path in destinations:
        path.unlink()
    moved_mib = size_mib * copies
    return {"source_mib": size_mib, "copies": copies, "seconds": seconds,
            "aggregate_mib_s": moved_mib / seconds}


def live_backends(args):
    """Resources named on the command line, as (label, provider, options)."""
    backends = [("local", None, {})]
    if args.dagonfs:
        for frontend in args.dagonfs_frontends.split(","):
            if frontend == "preload" and not args.dagonfs_preload:
                continue
            if frontend == "native" and not args.dagonfs_python:
                continue
            options = {"executable": args.dagonfs, "ranks": args.dagonfs_ranks, "frontend": frontend,
                       "mpirun": args.mpirun, "mpirun_args": args.mpirun_arg,
                       "python_path": args.dagonfs_python, "startup_timeout": 60}
            if frontend == "preload":
                options["preload_library"] = args.dagonfs_preload
            backends.append(("dagonfs-" + frontend, "dagonfs", options))
    if args.capio_server:
        backends.append(("capio", "capio", {"server": args.capio_server, "library": args.capio_library,
                                            "library_dir": args.capio_library_dir or (
                                                os.path.dirname(args.capio_library)
                                                if os.path.isabs(args.capio_library) else None),
                                            "startup_delay": 1.0}))
    if args.hercules_config:
        mount = "/mnt/hercules"
        if os.path.isfile(args.hercules_config):
            from dagon.adhoc import read_hercules_config
            mount = read_hercules_config(args.hercules_config).get("MOUNT_POINT", mount).rstrip("/")
        backends.append(("hercules", "hercules", {"config": args.hercules_config,
                                                  "launcher": args.hercules_launcher,
                                                  "library_dir": args.hercules_library_dir,
                                                  "ready_command": ["ls", mount + "/"],
                                                  "startup_timeout": 300}))
    if args.dynostore_server:
        backends.append(("dynostore", "dynostore", {"server": args.dynostore_server,
                                                    "catalog": args.dynostore_catalog,
                                                    "request_timeout": 300}))
    return backends


def live_once(label, provider, options, args, root):
    scratch = root / "scratch"
    results = root / "results"
    results.mkdir(parents=True)
    script = root / "io_task.py"
    # Tasks import dagon.adhoc (DynoStore client) from this checkout.
    source = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script.write_text("import sys\nsys.path.insert(0, %r)\n" % source + IO_TASK, encoding="utf-8")
    workflow = Workflow("adhoc-live", config=workflow_config(scratch), max_threads=args.live_readers + 1)
    filesystem = None
    if provider == "dagonfs":
        options = dict(options)
        suffix = "" if options["frontend"] == "fuse3" else ".sock"
        # Unix sockets are limited to ~104 bytes; keep them short.
        options["mountpoint"] = tempfile.mktemp(prefix="dfs", suffix=suffix, dir=args.socket_dir)
    if provider is not None:
        filesystem = workflow.create_adhoc_filesystem(provider, **options)
        timings = {}
        for name in ("start", "stop"):
            original = getattr(filesystem, name)

            def timed(original=original, name=name):
                started = time.perf_counter()
                try:
                    return original()
                finally:
                    timings[name] = time.perf_counter() - started
            setattr(filesystem, name, timed)
    data_root = '"$DAGON_ADHOC_PATH/run"' if provider else str(scratch / "local-run")
    if provider == "dynostore":
        data_root = "run-%s" % os.path.basename(str(root))
    if provider == "dagonfs" and options["frontend"] == "native":
        data_root = "/run"
    python = sys.executable + " -B"
    size = args.live_size_mib * 1024 * 1024
    command = "%s %s %%s %s %d %d %s/%%s.json" % (python, script, data_root, args.live_files, size, results)
    producer = DagonTask(TaskType.BATCH, "producer", command % ("write", "producer"))
    workflow.add_task(producer)
    readers = []
    for index in range(args.live_readers):
        reader = DagonTask(TaskType.BATCH, "reader-%02d" % index,
                           "echo workflow:///producer/ > /dev/null; " + command % ("read", "reader-%02d" % index))
        workflow.add_task(reader)
        readers.append(reader)
    for task in [producer] + readers:
        if filesystem is not None:
            filesystem.bind(task)
    workflow.make_dependencies()
    started = time.perf_counter()
    try:
        workflow.run()
        if any(getattr(task, "result", {"code": -1}).get("code") for task in workflow.tasks):
            raise RuntimeError("%s live run: a task failed" % label)
    except Exception:
        # The scratch directory is temporary: keep the provider's log in the job output.
        for log in scratch.glob(".adhoc-*.log"):
            print("---- %s\n%s" % (log.name, log.read_text(errors="replace")[-40000:]), file=sys.stderr)
        raise
    total = time.perf_counter() - started
    failed = [task.name for task in workflow.tasks if getattr(task, "result", {"code": -1}).get("code")]
    if failed:
        raise RuntimeError("%s live run failed in %s" % (label, failed))
    measured = {path.stem: json.loads(path.read_text()) for path in results.glob("*.json")}
    if len(measured) != args.live_readers + 1:
        raise RuntimeError("%s live run did not report every task" % label)
    mib = args.live_files * args.live_size_mib
    reads = [value["seconds"] for key, value in measured.items() if key.startswith("reader")]
    return {"workflow_seconds": total, "write_seconds": measured["producer"]["seconds"],
            "write_mib_s": mib / measured["producer"]["seconds"],
            "read_seconds_max": max(reads),
            "aggregate_read_mib_s": mib * len(reads) / max(reads),
            "start_seconds": timings.get("start", 0.0) if provider else 0.0,
            "stop_seconds": timings.get("stop", 0.0) if provider else 0.0}


def live_benchmark(args, root):
    report = {}
    for label, provider, options in live_backends(args):
        runs = []
        for repeat in range(args.live_repeats):
            runs.append(live_once(label, provider, options, args, root / ("live-%s-%d" % (label, repeat))))
        report[label] = {key: summary([run[key] for run in runs]) for key in runs[0]}
        report[label]["options"] = {key: value for key, value in options.items()
                                    if key in ("frontend", "ranks", "startup_delay")}
    return report


def markdown(report):
    lines = ["# Ad-hoc filesystem performance results", "",
             "Generated: `%s`" % report["generated_at"], "",
             "## Environment", "",
             "- Platform: `%s`" % report["environment"]["platform"],
             "- Python: `%s`" % report["environment"]["python"],
             "- Logical CPUs: `%s`" % report["environment"]["cpus"], "",
             "## Real backend availability", "",
             "| Provider | Available | Missing commands |", "|---|---:|---|"]
    for provider, state in report["availability"].items():
        lines.append("| %s | %s | %s |" %
                     (provider, "yes" if state["available"] else "no", ", ".join(state["missing"]) or "—"))
    lines += ["", "> Unavailable providers were measured only in portable emulation; those numbers are interface overhead, not filesystem throughput."]
    if report["interface"]:
        lines += ["", "## Common-interface workflow overhead", "",
                  "| Provider | Median (s) | Per task (ms) | Relative to baseline |", "|---|---:|---:|---:|"]
        baseline = report["interface"]["baseline"]["median"]
        tasks = report["parameters"]["tasks"]
        for provider, data in report["interface"].items():
            lines.append("| %s | %.6f | %.3f | %.3fx |" %
                         (provider, data["median"], 1000 * data["median"] / tasks, data["median"] / baseline))
    if report.get("live"):
        parameters = report["parameters"]
        lines += ["", "## Live backends through a DAGonStar workflow", "",
                  "One producer writes %d x %d MiB; %d readers verify every byte in parallel. "
                  "Medians of %d runs." % (parameters["live_files"], parameters["live_size_mib"],
                                           parameters["live_readers"], parameters["live_repeats"]), "",
                  "| Backend | Workflow (s) | Write (MiB/s) | Aggregate read (MiB/s) | Start (s) | Stop (s) |",
                  "|---|---:|---:|---:|---:|---:|"]
        for label, data in report["live"].items():
            lines.append("| %s | %.2f | %.1f | %.1f | %.2f | %.2f |" % (
                label, data["workflow_seconds"]["median"], data["write_mib_s"]["median"],
                data["aggregate_read_mib_s"]["median"], data["start_seconds"]["median"],
                data["stop_seconds"]["median"]))
    io = report["local_io"]
    lines += ["", "## Verified local-filesystem I/O reference", "",
              "| Workload | Result |", "|---|---:|",
              "| Sequential write + fsync | %.1f MiB/s |" % io["sequential"]["write_mib_s"],
              "| Sequential cached read | %.1f MiB/s |" % io["sequential"]["read_mib_s"],
              "| Small-file create | %.0f files/s |" % io["small_files"]["create_files_s"],
              "| Small-file metadata scan | %.0f files/s |" % io["small_files"]["scan_files_s"],
              "| Fan-out copies | %.1f aggregate MiB/s |" % io["fanout_copy"]["aggregate_mib_s"], "",
              "## Interpretation", "",
              "The local I/O section is a host reference, not a result for an unavailable provider. Run this same tool on a node with the desired runtime installed before comparing real backend throughput.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=int, default=32)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--size-mib", type=int, default=128)
    parser.add_argument("--small-files", type=int, default=2000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-interface", action="store_true", help="omit the emulated overhead section")
    live = parser.add_argument_group("live backends (measured only when named)")
    live.add_argument("--dagonfs", help="dagonfs executable")
    live.add_argument("--dagonfs-frontends", default="fuse3,native,preload")
    live.add_argument("--dagonfs-ranks", type=int, default=4)
    live.add_argument("--dagonfs-python", help="DAGonFS python/ directory (native frontend)")
    live.add_argument("--dagonfs-preload", help="libdagonfs_preload library (preload frontend)")
    live.add_argument("--mpirun", default="mpirun")
    live.add_argument("--mpirun-arg", action="append", default=[], help="repeatable mpirun argument")
    live.add_argument("--capio-server")
    live.add_argument("--capio-library", default="libcapio_posix.so")
    live.add_argument("--capio-library-dir", help="directory with libsyscall_intercept (default: the library's)")
    live.add_argument("--hercules-config")
    live.add_argument("--hercules-launcher", default="hercules")
    live.add_argument("--hercules-library-dir")
    live.add_argument("--dynostore-server", help="DynoStore gateway HOST:PORT (token in $DYNOSTORE_TOKEN)")
    live.add_argument("--dynostore-catalog", default="dagonstar-benchmark")
    live.add_argument("--live-files", type=int, default=16)
    live.add_argument("--live-size-mib", type=int, default=8)
    live.add_argument("--live-readers", type=int, default=4)
    live.add_argument("--live-repeats", type=int, default=3)
    live.add_argument("--socket-dir", default="/tmp" if os.path.isdir("/tmp") else None)
    live.add_argument("--live-only", action="store_true", help="measure only the named live backends")
    args = parser.parse_args()
    if min(args.tasks, args.repeats, args.size_mib, args.small_files) < 1:
        parser.error("all numeric parameters must be positive")
    availability = {}
    for provider, commands in PROVIDERS.items():
        missing = [command for command in commands if shutil.which(command) is None]
        availability[provider] = {"available": not missing, "missing": missing,
                                  "commands": {command: shutil.which(command) for command in commands}}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        interface = {}
        live = live_benchmark(args, root) if (args.dagonfs or args.capio_server or args.hercules_config
                                                   or args.dynostore_server) else {}
        for provider in () if args.skip_interface or args.live_only else ("baseline", *PROVIDERS):
            values = [interface_once(provider, args.tasks, root / (provider + "-%d" % repeat))
                      for repeat in range(args.repeats)]
            interface[provider] = summary(values)
        io_root = root / "io"
        io_root.mkdir()
        local_io = {"sequential": sequential_io(io_root, args.size_mib),
                    "small_files": small_file_io(io_root, args.small_files, 4096),
                    "fanout_copy": copy_io(io_root, max(1, args.size_mib // 4), 4)}
    report = {"schema_version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "environment": {"platform": platform.platform(), "python": platform.python_version(),
                              "cpus": os.cpu_count()},
              "parameters": vars(args) | {"output": str(args.output) if args.output else None},
              "availability": availability, "interface": interface, "local_io": local_io,
              "live": live}
    rendered = markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.output.with_suffix(".md").write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
