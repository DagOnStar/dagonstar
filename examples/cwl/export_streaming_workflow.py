"""Export a workflow with a streaming edge as CWL v1.2 and optionally run it.

CWL v1.2 has no concurrency between steps, so the exporter materializes the
stream: the producer's stream becomes a ``Directory`` output (items plus
markers, ended by ``dagon.adhoc stream close``) and the consumer reads it with
the same ``dagon.adhoc stream items`` command after the producer completes.
The ``dagon:Stream`` hint records the streaming intent.  The consumer checks
that it received all three items, so a successful CWL run verifies the stream.
Commands avoid ``$(...)``, which CWL reads as an expression.  The run needs
DAGonStar importable by ``python3`` in the CWL runner's environment
(``pip install -e .``)::

    python examples/cwl/export_streaming_workflow.py --output /tmp/streaming.cwl
    cwltool --validate /tmp/streaming.cwl
    cwltool /tmp/streaming.cwl
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType

PRODUCE = ('for i in 1 2 3; do echo "item $i" > item-$i.txt; '
           '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i.txt > /dev/null; done')
CONSUME = ('"$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///produce/items?stream --into in | '
           'while read -r item; do cat "$item"; done > received.txt && test "`grep -c item received.txt`" = 3')


def build_workflow(scratch):
    config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
              "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
    workflow = Workflow("DAGonStar CWL streaming", config=config, portable_emulation=True)
    produce = DagonTask(TaskType.BATCH, "produce", PRODUCE)
    consume = DagonTask(TaskType.BATCH, "consume", CONSUME)
    workflow.add_task(produce)
    workflow.add_task(consume)
    volume = workflow.create_adhoc_filesystem("dagonfs", name="ram")
    volume.bind(produce)
    volume.bind(consume)
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, help="CWL file to write (default: in a new temporary directory)")
    options = parser.parse_args()
    if options.output is None:
        options.output = Path(tempfile.mkdtemp(prefix="dagon-cwl-")) / "streaming-workflow.cwl"
    with tempfile.TemporaryDirectory() as scratch:
        build_workflow(scratch).saveAsCWL(str(options.output))
    document = json.loads(options.output.read_text(encoding="utf-8"))
    steps = document["steps"]
    steps = steps.items() if isinstance(steps, dict) else ((step["id"], step) for step in steps)
    hinted = sorted(name for name, step in steps if "dagon:Stream" in step["run"].get("hints", {}))
    print("Wrote %s (%d bytes)" % (options.output, os.path.getsize(options.output)))
    print("dagon:Stream hint on: %s" % ", ".join(hinted))


if __name__ == "__main__":
    main()
