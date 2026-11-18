"""Stream partial results between two tasks of a larger workflow.

The workflow is ``A -> {B1, C}``, ``B1 -> B2`` and ``{B2, C} -> D``.  Only the
edge ``B1 -> B2`` is a stream: B2's command reads ``workflow:///B1/frames?stream``,
and both tasks are bound to a streaming ad-hoc resource.  B2 starts while B1
is still running and processes each frame as soon as B1 publishes it; every
other edge keeps the ordinary semantics (the consumer waits for the producer to
finish and its files are staged).

By default the stream runs on the ``local-directory`` adapter defined in
``custom_adapter.py`` (a real local resource, not emulation).  With
``--emulate PROVIDER`` the same workflow runs under portable emulation with a
built-in provider (``dagonfs``, ``capio``, ``hercules``, ``dynostore``), which
verifies the planning and the protocol but not the external system.  With
``--live PROVIDER`` and ``--option KEY=VALUE`` it runs on a deployed system::

    python examples/adhoc/streaming.py
    python examples/adhoc/streaming.py --emulate capio
    python examples/adhoc/streaming.py --live dagonfs --option executable=/opt/dagonfs/bin/dagonfs \
        --option frontend=native --option python_path=/opt/DAGonFS/python

B2 copies every item, verified against the SHA-256 in its marker, into its own
``frames-in`` directory with ``python -m dagon.adhoc stream items --into``, so
the same command works for mounted, preloaded, socket, and object stores.

The run checks that B2 received the first frame before B1 finished, that every
frame arrived verified and in order, and that D saw both branches.
"""

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dagon import Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
import custom_adapter  # noqa: E402,F401  (registers "local-directory")

FRAMES = 8
NOW = '"$DAGON_PYTHON" -c "import time; print(time.time())"'

A = 'echo %d > count.txt' % FRAMES
B1 = ('n=$(cat workflow:///A/count.txt ); for i in $(seq 1 "$n"); do '
      'echo "frame $i" > "frame-$i.txt"; '
      '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" "frame-$i.txt" > /dev/null || exit 1; '
      'sleep 0.25; done; ' + NOW + ' > finished.txt')
B2 = ('set -o pipefail; "$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///B1/frames?stream --into frames-in | '
      'while read -r item; do cat "$item" >> received.txt; ' + NOW + ' >> arrivals.txt; done')
C = 'wc -c < workflow:///A/count.txt > size.txt'
D = 'cat workflow:///B2/received.txt workflow:///C/size.txt > summary.txt'


def build(scratch: str, emulate: str = "", live: str = "", options: dict = None) -> Workflow:
    config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "8"},
              "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
    workflow = Workflow("streaming-example", config=config, portable_emulation=bool(emulate))
    tasks = {name: DagonTask(TaskType.BATCH, name, command)
             for name, command in (("A", A), ("B1", B1), ("B2", B2), ("C", C), ("D", D))}
    for task in tasks.values():
        workflow.add_task(task)
    if live:
        volume = workflow.create_adhoc_filesystem(live, **dict({"name": "frames"}, **(options or {})))
    else:
        defaults = {"hercules": {"config": "site-hercules.conf"},
                    "dynostore": {"catalog": "streaming-example"}}.get(emulate, {})
        volume = workflow.create_adhoc_filesystem(emulate or "local-directory", name="frames", **defaults)
    volume.bind(tasks["B1"])
    volume.bind(tasks["B2"])
    return workflow


def check(workflow: Workflow) -> None:
    tasks = {task.name: task for task in workflow.tasks}
    failed = [task.name for task in workflow.tasks if (getattr(task, "result", None) or {}).get("code")]
    assert not failed, failed

    def read(task: str, name: str) -> str:
        with open(os.path.join(tasks[task].working_dir, name), encoding="utf-8") as stream:
            return stream.read()

    assert tasks["B2"].stream_prevs == [tasks["B1"]], "only B1 -> B2 is a streaming edge"
    received = read("B2", "received.txt").split("\n")[:-1]
    assert received == ["frame %d" % i for i in range(1, FRAMES + 1)], received
    first_arrival = float(read("B2", "arrivals.txt").split()[0])
    finished = float(read("B1", "finished.txt"))
    assert first_arrival < finished, "B2 consumed the first frame while B1 was still producing"
    assert read("D", "summary.txt").startswith("frame 1\n")
    print("B2 received frame 1 %.2f s before B1 finished; %d frames verified in order"
          % (finished - first_arrival, len(received)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--emulate", choices=("dagonfs", "capio", "hercules", "dynostore"), default="")
    parser.add_argument("--live", default="", help="run on a deployed provider (registered name)")
    parser.add_argument("--option", action="append", default=[], metavar="KEY=VALUE",
                        help="provider option for --live (JSON values are decoded)")
    parser.add_argument("--scratch", help="scratch directory (default: a temporary one)")
    options = parser.parse_args()
    provider_options = {}
    for item in options.option:
        key, _, value = item.partition("=")
        try:
            provider_options[key] = json.loads(value)
        except ValueError:
            provider_options[key] = value
    with tempfile.TemporaryDirectory(dir=options.scratch) as scratch:
        workflow = build(scratch, options.emulate, options.live, provider_options)
        workflow.run()
        check(workflow)
        print("Verification: ok")


if __name__ == "__main__":
    main()
