#!/usr/bin/env python3
"""Use several live ad-hoc resources in one workflow at the same time.

Every backend named on the command line (the options of
``benchmark_adhoc_filesystems.py``) becomes one workflow-scope volume of the
same workflow, plus one task-scope ``scratch-directory`` volume.  A chain of
tasks moves a payload through all of them: task ``hop-i`` is bound to volume
``i`` and ``i+1``, reads the payload from the first, and writes it to the
second, so consecutive volumes are open in one task at once and every volume
is running for the whole workflow.  A stream then carries items between two
tasks over each streaming volume.  Every byte is verified by SHA-256.
``--order`` sets the chain order, which decides which volumes share a hop task.

    python tools/check_adhoc_multivolume.py --dagonfs build/dagonfs --dagonfs-frontends native \\
        --dagonfs-python DAGonFS/python --capio-server capio_server --capio-library libcapio_posix.so
"""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dagon import Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
from benchmark_adhoc_filesystems import live_backends, workflow_config  # noqa: E402
import benchmark_adhoc_streaming  # noqa: E402,F401  (registers "scratch-directory")

HOP = r'''
import hashlib, os, sys
sys.path.insert(0, os.environ["DAGON_SOURCE"])
source, target, expected, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

def volume(name):
    suffix = name.upper().replace("-", "_").replace(".", "_")
    access = os.environ["DAGON_ADHOC_%s_ACCESS" % suffix]
    provider = os.environ["DAGON_ADHOC_%s_PROVIDER" % suffix]
    path = os.environ["DAGON_ADHOC_%s_PATH" % suffix]
    key = hashlib.sha256(("multivolume/" + os.environ["RUN_TAG"] + "/" + name).encode()).hexdigest()
    if access == "object":
        from dagon.adhoc import DynoStoreClient
        client = DynoStoreClient.from_environment()
        return (lambda data: client.put_bytes(data, key)), (lambda: client.get_bytes(key))
    if access == "client":
        sys.path.insert(0, os.environ["DAGONFS_PYTHON"])
        from dagonfs.native import Client
        client = Client(path).connect()
        return (lambda data: client.write_bytes("/" + key, data)), (lambda: client.read_bytes("/" + key))
    def write(data):
        with open(path + "/" + key, "wb", buffering=0) as stream:
            stream.write(data)
    def read():
        with open(path + "/" + key, "rb", buffering=0) as stream:
            return stream.read()
    return write, read

data = bytes(range(256)) * 4096 if source == "-" else volume(source)[1]()
if hashlib.sha256(data).hexdigest() != expected:
    sys.exit("payload changed before %s" % target)
if target != "-":
    volume(target)[0](data)
with open(out, "w") as stream:
    stream.write("%s -> %s ok\n" % (source, target))
'''

PRODUCE = ('for i in 1 2 3 4; do head -c 65536 /dev/zero | tr "\\0" "$i" > item-$i.bin; '
           '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i.bin > /dev/null || exit 1; '
           'sleep 0.3; done')
CONSUME = ('set -o pipefail; "$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///%s/items?stream=%s '
           '--into items | wc -l > count.txt && test "$(cat count.txt | tr -d " ")" = 4')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for option in ("--dagonfs", "--dagonfs-python", "--dagonfs-preload", "--capio-server", "--capio-library-dir",
                   "--hercules-config", "--hercules-library-dir", "--dynostore-server"):
        parser.add_argument(option)
    parser.add_argument("--dagonfs-frontends", default="native")
    parser.add_argument("--dagonfs-ranks", type=int, default=2)
    parser.add_argument("--mpirun", default="mpirun")
    parser.add_argument("--mpirun-arg", action="append", default=[])
    parser.add_argument("--capio-library", default="libcapio_posix.so")
    parser.add_argument("--hercules-launcher", default="hercules")
    parser.add_argument("--dynostore-catalog", default="dagonstar-multivolume")
    parser.add_argument("--socket-dir", default="/tmp" if os.path.isdir("/tmp") else None)
    parser.add_argument("--order", help="comma-separated backend labels giving the chain order "
                        "(consecutive volumes share a hop task); default: as named")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    backends = [(label, provider, options) for label, provider, options in live_backends(args) if provider]
    if args.order:
        rank = {label: index for index, label in enumerate(args.order.split(","))}
        backends.sort(key=lambda backend: rank.get(backend[0], len(rank)))
    import hashlib
    expected = hashlib.sha256(bytes(range(256)) * 4096).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        script = root / "hop.py"
        script.write_text(HOP, encoding="utf-8")
        workflow = Workflow("adhoc-multivolume-" + uuid.uuid4().hex[:8], config=workflow_config(root / "scratch"), max_threads=8)
        volumes = []
        for index, (label, provider, options) in enumerate(backends):
            options = dict(options)
            if provider == "dagonfs":
                suffix = "" if options["frontend"] == "fuse3" else ".sock"
                options["mountpoint"] = tempfile.mktemp(prefix="dfs", suffix=suffix, dir=args.socket_dir)
            volumes.append(workflow.create_adhoc_filesystem(provider, name="v%d-%s" % (index, label), **options))
        names = ["-"] + [volume.name for volume in volumes] + ["-"]
        previous = None
        prefix = "export DAGON_SOURCE=%s RUN_TAG=%s; " % (ROOT, root.name)
        hops = []
        for index in range(len(names) - 1):
            source, target = names[index], names[index + 1]
            link = "echo workflow:///%s/ok.txt > /dev/null; " % previous.name if previous else ""
            task = DagonTask(TaskType.BATCH, "hop-%d" % index, prefix + link + "%s -B %s %s %s %s ok.txt"
                             % (sys.executable, script, source, target, expected))
            workflow.add_task(task)
            for volume in volumes:
                if volume.name in (source, target):
                    volume.bind(task)
            hops.append(task)
            previous = task
        # A task-scope volume next to the workflow-scope ones.
        private = hops[-1].create_adhoc_filesystem("scratch-directory", name="private")
        streams = []
        for volume in volumes:
            if not volume.supports_streaming:
                continue
            producer = DagonTask(TaskType.BATCH, "produce-" + volume.name, PRODUCE)
            consumer = DagonTask(TaskType.BATCH, "consume-" + volume.name, CONSUME % (producer.name, volume.name))
            for task in (producer, consumer):
                workflow.add_task(task)
                volume.bind(task)
            streams.append(consumer)
        started = time.perf_counter()
        workflow.run()
        seconds = time.perf_counter() - started
        failed = {task.name: (getattr(task, "result", None) or {}).get("message", "")[-1500:]
                  for task in workflow.tasks if (getattr(task, "result", None) or {"code": 1}).get("code")}
        report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "host": os.uname().nodename.split(".")[0], "workflow_seconds": seconds,
                  "volumes": [volume.metadata() for volume in volumes] + [private.metadata()],
                  "hops": [task.name for task in hops], "streams": [task.name for task in streams],
                  "overlapping_stream_consumers": [task.name for task in streams if task.stream_prevs],
                  "failed": failed, "passed": not failed}
        for volume in volumes:
            for key in ("streams",):
                report["volumes"][volumes.index(volume)].pop(key, None)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
