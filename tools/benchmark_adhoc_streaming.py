#!/usr/bin/env python3
"""Measure streaming between two tasks through DAGonStar's ad-hoc interface.

A producer task P makes ``--items`` items of ``--item-kib`` KiB (spending
``--delay`` seconds of simulated computation before each) and a consumer task C
verifies each item by SHA-256 (spending ``--delay`` seconds after each).  Two
dataflows are measured on every backend, with the same tasks and bytes:

``sequential``
    the ordinary ad-hoc dataflow: P writes the items to the resource, C has a
    plain ``workflow://`` edge, so it starts after P has finished;
``stream``
    C reads ``workflow:///P/items?stream`` and starts while P runs; each item
    is published with :class:`dagon.streaming.StreamWriter` and consumed as
    soon as its marker appears.

Timestamps are taken inside the tasks (same host clock, or NTP-synchronised
nodes), so the report separates the data path from DAGonStar's orchestration:
``pipeline`` runs from P's first instruction to C's last, ``work`` is P's
duration plus C's (a sequential run with no orchestration gap), and
``first_item_latency`` is the time from P publishing item 1 to C holding it
verified.  Backends are named exactly as in ``benchmark_adhoc_filesystems.py``;
``local`` (a directory adapter on the scratch file system) is always measured.
"""

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dagon import Workflow  # noqa: E402
from dagon.adhoc import AdHocFileSystem, register_provider  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
from benchmark_adhoc_filesystems import live_backends, workflow_config  # noqa: E402


class ScratchDirectory(AdHocFileSystem):
    """Reference backend: a plain directory, registered like any third-party adapter."""

    provider = "scratch-directory"
    access = "posix"
    supports_streaming = True

    def __init__(self, workflow, name="default", path=None):
        super().__init__(workflow, name)
        self.path = path or os.path.join(workflow.get_scratch_dir_base(), ".scratch-" + name)

    @property
    def task_path(self):
        return self.path

    def start(self):
        os.makedirs(self.path, exist_ok=True)
        self._started = True


register_provider("scratch-directory", ScratchDirectory, replace=True)

TASK = r'''
import hashlib, json, os, random, sys, time
role, mode, items, size, delay, result = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
sys.path.insert(0, os.environ.get("DAGON_SOURCE", ""))
started = time.time()
def payload(index):
    return random.Random(index).randbytes(size)
def name(index):
    return "item-%05d.bin" % index
record = {"role": role, "mode": mode, "started": started, "events": []}
if mode == "stream":
    from dagon import streaming
    if role == "producer":
        writer = streaming.writer(os.environ["DAGON_STREAM_OUT"])
        for index in range(items):
            time.sleep(delay)
            data = payload(index)
            writer.publish_bytes(name(index), data)
            record["events"].append(time.time())
    else:
        reader = streaming.reader(os.environ["DAGON_STREAM_IN"])
        for index, item in enumerate(reader):
            data = reader.read(item)
            if item.name != name(index) or hashlib.sha256(data).digest() != hashlib.sha256(payload(index)).digest():
                sys.exit("item %d did not verify" % index)
            record["events"].append(time.time())
            time.sleep(delay)
        if len(record["events"]) != items:
            sys.exit("received %d of %d items" % (len(record["events"]), items))
else:
    access = os.environ.get("DAGON_ADHOC_ACCESS", "posix")
    root = os.environ.get("DAGON_ADHOC_PATH", "") + "/sequential-" + os.environ["RUN_TAG"]
    if access == "object":
        from dagon.adhoc import DynoStoreClient
        client = DynoStoreClient.from_environment()
        key = lambda index: hashlib.sha256((root + name(index)).encode()).hexdigest()
        write = lambda index, data: client.put_bytes(data, key(index))
        read = lambda index: client.get_bytes(key(index))
        prepare = lambda: None
    elif access == "client":
        sys.path.insert(0, os.environ["DAGONFS_PYTHON"])
        from dagonfs.native import Client
        client = Client(os.environ["DAGONFS_SOCKET"]).connect()
        root = "/sequential-" + os.environ["RUN_TAG"]
        write = lambda index, data: client.write_bytes(root + "/" + name(index), data)
        read = lambda index: client.read_bytes(root + "/" + name(index))
        prepare = lambda: client.makedirs(root)
    else:
        def write(index, data):
            with open(root + "/" + name(index), "wb", buffering=0) as stream:
                view = memoryview(data)
                while view:
                    view = view[stream.write(view):]
        def read(index):
            with open(root + "/" + name(index), "rb", buffering=0) as stream:
                return stream.read()
        def prepare():
            try:
                os.mkdir(root)
            except FileExistsError:
                pass
    if role == "producer":
        prepare()
        for index in range(items):
            time.sleep(delay)
            write(index, payload(index))
            record["events"].append(time.time())
    else:
        for index in range(items):
            if hashlib.sha256(read(index)).digest() != hashlib.sha256(payload(index)).digest():
                sys.exit("item %d did not verify" % index)
            record["events"].append(time.time())
            time.sleep(delay)
record["finished"] = time.time()
with open(result, "w") as stream:
    json.dump(record, stream)
'''


def summary(values):
    ordered = sorted(values)
    return {"samples": values, "median": statistics.median(values), "minimum": ordered[0],
            "maximum": ordered[-1]}


def run_once(label, provider, options, args, root, mode):
    scratch, results = root / "scratch", root / "results"
    results.mkdir(parents=True)
    script = root / "stream_task.py"
    script.write_text(TASK, encoding="utf-8")
    workflow = Workflow("adhoc-stream-" + uuid.uuid4().hex[:8], config=workflow_config(scratch), max_threads=4)
    options = dict(options)
    if provider == "dagonfs":
        suffix = "" if options["frontend"] == "fuse3" else ".sock"
        options["mountpoint"] = tempfile.mktemp(prefix="dfs", suffix=suffix, dir=args.socket_dir)
    filesystem = workflow.create_adhoc_filesystem(provider or "scratch-directory", name="data", **options)
    size = args.item_kib * 1024
    base = "%s -B %s %%s %s %d %d %s %s/%%s.json" % (sys.executable, script, mode, args.items, size,
                                                     args.delay, results)
    producer = DagonTask(TaskType.BATCH, "P", "export DAGON_SOURCE=%s RUN_TAG=%s; " % (ROOT, root.name)
                         + base % ("producer", "producer") + " && touch done.txt")
    link = "workflow:///P/items?stream" if mode == "stream" else "workflow:///P/done.txt"
    consumer = DagonTask(TaskType.BATCH, "C", "export DAGON_SOURCE=%s RUN_TAG=%s; echo %s > /dev/null; "
                         % (ROOT, root.name, link) + base % ("consumer", "consumer"))
    for task in (producer, consumer):
        workflow.add_task(task)
        filesystem.bind(task)
    started = time.perf_counter()
    try:
        workflow.run()
    except Exception:
        for log in scratch.glob(".adhoc-*.log"):
            print("---- %s\n%s" % (log.name, log.read_text(errors="replace")[-20000:]), file=sys.stderr)
        raise
    total = time.perf_counter() - started
    failed = [task.name for task in workflow.tasks if (getattr(task, "result", None) or {"code": 1}).get("code")]
    if failed:
        messages = {task.name: (getattr(task, "result", None) or {}).get("message", "")[-2000:] for task in workflow.tasks}
        raise RuntimeError("%s %s run failed in %s: %s" % (label, mode, failed, messages))
    p = json.loads((results / "producer.json").read_text())
    c = json.loads((results / "consumer.json").read_text())
    if mode == "stream" and consumer.stream_prevs != [producer]:
        raise RuntimeError("the stream edge was not planned")
    latencies = [received - published for published, received in zip(p["events"], c["events"])]
    mib = args.items * size / (1 << 20)
    return {"workflow_seconds": total,
            "pipeline_seconds": c["finished"] - p["started"],
            "work_seconds": (p["finished"] - p["started"]) + (c["finished"] - c["started"]),
            "consumer_start_after_producer_seconds": c["started"] - p["started"],
            "first_item_latency_seconds": latencies[0],
            "median_item_latency_seconds": statistics.median(latencies),
            "producer_mib_s": mib / max(1e-9, (p["finished"] - p["started"]) - args.items * args.delay),
            "consumer_mib_s": mib / max(1e-9, (c["finished"] - c["started"]) - args.items * args.delay
                                        - (c["events"][0] - c["started"] if mode == "stream" else 0))}


def markdown(report):
    lines = ["| Backend | Dataflow | Workflow (s) | Pipeline (s) | Work (s) | C starts after P (s) | "
             "First-item latency (s) | Median latency (s) | P MiB/s | C MiB/s |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, modes in report["results"].items():
        for mode, values in modes.items():
            row = [values[key]["median"] for key in (
                "workflow_seconds", "pipeline_seconds", "work_seconds", "consumer_start_after_producer_seconds",
                "first_item_latency_seconds", "median_item_latency_seconds", "producer_mib_s", "consumer_mib_s")]
            lines.append("| %s | %s | %s |" % (label, mode, " | ".join("%.2f" % value for value in row)))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--items", type=int, default=16)
    parser.add_argument("--item-kib", type=int, default=1024)
    parser.add_argument("--delay", type=float, default=0.25, help="seconds of simulated work per item and side")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--modes", default="sequential,stream")
    parser.add_argument("--skip-local", action="store_true")
    live = parser.add_argument_group("backends (as in benchmark_adhoc_filesystems.py)")
    live.add_argument("--dagonfs")
    live.add_argument("--dagonfs-frontends", default="fuse3,native,preload")
    live.add_argument("--dagonfs-ranks", type=int, default=4)
    live.add_argument("--dagonfs-python")
    live.add_argument("--dagonfs-preload")
    live.add_argument("--mpirun", default="mpirun")
    live.add_argument("--mpirun-arg", action="append", default=[])
    live.add_argument("--capio-server")
    live.add_argument("--capio-library", default="libcapio_posix.so")
    live.add_argument("--capio-library-dir")
    live.add_argument("--hercules-config")
    live.add_argument("--hercules-launcher", default="hercules")
    live.add_argument("--hercules-library-dir")
    live.add_argument("--dynostore-server")
    live.add_argument("--dynostore-catalog", default="dagonstar-streaming")
    live.add_argument("--socket-dir", default="/tmp" if os.path.isdir("/tmp") else None)
    args = parser.parse_args()
    if min(args.items, args.item_kib, args.repeats) < 1 or args.delay < 0:
        parser.error("items, item size, and repeats must be positive; delay must not be negative")
    backends = [(label, provider, options) for label, provider, options in live_backends(args)
                if not (args.skip_local and provider is None)]
    report = {"schema_version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "environment": {"platform": platform.platform(), "python": platform.python_version(),
                              "cpus": os.cpu_count(), "host": platform.node().split(".")[0]},
              "parameters": {key: (str(value) if isinstance(value, Path) else value)
                             for key, value in vars(args).items()},
              "results": {}}
    with tempfile.TemporaryDirectory() as temporary:
        for label, provider, options in backends:
            for mode in args.modes.split(","):
                runs = [run_once(label, provider, options, args,
                                 Path(temporary) / ("%s-%s-%d" % (label, mode, repeat)), mode)
                        for repeat in range(args.repeats)]
                report["results"].setdefault(label, {})[mode] = {key: summary([run[key] for run in runs])
                                                                 for key in runs[0]}
                print("%s %s done" % (label, mode), file=sys.stderr, flush=True)
    rendered = markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.output.with_suffix(".md").write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
