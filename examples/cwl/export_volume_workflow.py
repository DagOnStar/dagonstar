"""Export a workflow with volume tasks as CWL v1.2 and optionally run it.

The workflow is ``prepare -> scratch (create volume "shared") -> {left, right}
-> drop (destroy, stage out) -> check``.  CWL v1.2 has no shared, mutable
storage between steps, so the exporter materializes the volume: the create
step copies its staged-in content into ``shared/`` of its working directory
(the ``volume`` Directory output, and what ``workflow:///scratch/shared/...``
names), consumers read it as an input, and the destroy step copies its
``stage_out`` entries from it.  A ``dagon:Volume`` hint records the provider,
volume, action, and release policy.  Data that sibling steps write into the
volume during a DAGonStar run is *not* exchanged through CWL, so the commands
here only read the volume.

``--portable`` (the default) exports with portable emulation, which is
directly runnable; ``--standard`` exports the backend form, in which command
tasks keep their ``workflow://`` text.  ``--run`` executes the portable
document with ``cwltool --no-container`` when ``cwltool`` is installed::

    python examples/cwl/export_volume_workflow.py --output /tmp/volume.cwl --run
    cwltool --validate /tmp/volume.cwl
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def build_workflow(scratch, portable=True):
    config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
              "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
    workflow = Workflow("DAGonStar CWL volume", config=config, portable_emulation=portable)
    prepare = DagonTask(TaskType.BATCH, "prepare", "mkdir -p data; seq 1 4 > data/n.txt")
    scratch_volume = DagonTask(TaskType.VOLUME, "scratch", provider="dagonfs", volume="shared",
                               stage_in={"inputs/n.txt": {"path": "workflow:///prepare/data/n.txt",
                                                          "type": "file"}})
    left = DagonTask(TaskType.BATCH, "left", "head -n 2 workflow:///scratch/shared/inputs/n.txt > left.txt")
    right = DagonTask(TaskType.BATCH, "right", "tail -n 2 workflow:///scratch/shared/inputs/n.txt > right.txt")
    drop = DagonTask(TaskType.VOLUME, "drop", action="destroy", volume="workflow:///scratch/shared",
                     stage_out={"kept.txt": {"path": "inputs/n.txt", "type": "file"}})
    check = DagonTask(TaskType.BATCH, "check", "test `wc -l < workflow:///drop/kept.txt` -eq 4")
    for task in (prepare, scratch_volume, left, right, drop, check):
        workflow.add_task(task)
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, help="CWL file to write (default: in a new temporary directory)")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--portable", dest="portable", action="store_true", default=True)
    form.add_argument("--standard", dest="portable", action="store_false")
    parser.add_argument("--run", action="store_true", help="execute the document with cwltool")
    options = parser.parse_args()
    if options.output is None:
        options.output = Path(tempfile.mkdtemp(prefix="dagon-cwl-")) / "volume-workflow.cwl"
    with tempfile.TemporaryDirectory() as scratch:
        build_workflow(scratch, options.portable).saveAsCWL(str(options.output))
    document = json.loads(options.output.read_text(encoding="utf-8"))
    hinted = {name: step["run"]["hints"]["dagon:Volume"]["action"] for name, step in document["steps"].items()
              if "dagon:Volume" in step["run"].get("hints", {})}
    print("Wrote %s (%d bytes)" % (options.output, os.path.getsize(options.output)))
    print("dagon:Volume hint on: %s" % ", ".join("%s (%s)" % item for item in sorted(hinted.items())))
    assert hinted == {"scratch": "create", "drop": "destroy"}, hinted
    if shutil.which("cwltool"):
        subprocess.run(["cwltool", "--validate", str(options.output)], check=True, capture_output=True)
        print("cwltool --validate: ok")
        if options.run and options.portable:
            with tempfile.TemporaryDirectory() as outdir:
                completed = subprocess.run(["cwltool", "--no-container", "--outdir", outdir, str(options.output)],
                                           capture_output=True, text=True)
            if completed.returncode:
                sys.stderr.write(completed.stderr[-3000:])
                raise SystemExit(completed.returncode)
            print("cwltool run: ok")
    elif options.run:
        print("cwltool is not installed: the document was not run")
    print("Verification: ok")


if __name__ == "__main__":
    main()
