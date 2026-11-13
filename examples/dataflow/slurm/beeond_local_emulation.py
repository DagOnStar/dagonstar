"""Self-contained BeeOND example under portable emulation (no Slurm required).

Run from the repository root (no ``dagon.ini`` is required)::

    python3 examples/dataflow/slurm/beeond_local_emulation.py                 # temporary scratch
    python3 examples/dataflow/slurm/beeond_local_emulation.py --scratch DIR   # keep results in DIR

The workflow has the shape of a real BeeOND workflow:

* ``nodes`` uses a per-task volume, writes one file per "node" into
  ``$DAGON_BEEOND``, and its volume is persisted to ``<working_dir>/beeond``;
* ``combine`` reads the persisted files with ``workflow:///nodes/beeond/...``;
* ``stage`` and ``analyse`` share the per-workflow volume ``shared``;
* ``report`` consumes the analysis result.

With ``portable_emulation=True`` no scheduler is contacted: ``$DAGON_BEEOND``
points straight at the persistent directory, so the data paths and
dependencies behave as on a cluster while volume speed, multi-node sharing,
and the holder job are not emulated.  See ``docs/beeond.md``.
"""
import argparse
import os
import sys
import tempfile

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def local_config(scratch: str) -> dict:
    """Return an inline configuration with BeeOND defaults for the demo site."""
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
        # The same values a real site would put in the [beeond] section.
        "beeond": {"comment": "beeond-fs", "partition": "xxcpu", "nodelist": "wn[01-04]",
                   "ntasks_per_node": "1", "verify": "list"},
    }


def build_workflow(scratch: str) -> Workflow:
    workflow = Workflow("BeeOND-Demo", config=local_config(scratch), portable_emulation=True)
    workflow.create_beeond_volume("shared", time="01:00:00")

    nodes = DagonTask(
        TaskType.SLURM, "nodes",
        'for host in wn01 wn02 wn03 wn04; do '
        'echo "This is node $host writing its own output." > "$DAGON_BEEOND/node_$host.txt"; done',
        nodelist="wn[01-04]", ntasks_per_node=1, beeond="task")
    combine = DagonTask(TaskType.SLURM, "combine",
                        "cat workflow:///nodes/beeond/node_wn01.txt workflow:///nodes/beeond/node_wn02.txt "
                        "workflow:///nodes/beeond/node_wn03.txt workflow:///nodes/beeond/node_wn04.txt > out")
    stage = DagonTask(TaskType.SLURM, "stage", 'cp workflow:///combine/out "$DAGON_BEEOND/input.txt"',
                      beeond="workflow:shared")
    analyse = DagonTask(TaskType.SLURM, "analyse", 'wc -l < "$DAGON_BEEOND/input.txt" > lines.txt',
                        beeond="workflow:shared")
    report = DagonTask(TaskType.BATCH, "report", "cp workflow:///analyse/lines.txt report.txt")
    for task in (nodes, combine, stage, analyse, report):
        workflow.add_task(task)
    workflow.make_dependencies()
    # Data on a shared workflow volume is not a workflow:// reference: order it explicitly.
    analyse.add_dependency_to(stage)
    return workflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="scratch directory to keep (default: temporary)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dagon-beeond-") as temporary:
        scratch = os.path.abspath(args.scratch or temporary)
        os.makedirs(scratch, exist_ok=True)
        workflow = build_workflow(scratch)
        workflow.run()
        failed = [task.name for task in workflow.tasks if task.status.name != "FINISHED"]
        if failed:
            print("Failed tasks:", ", ".join(failed))
            return 1
        tasks = {task.name: task for task in workflow.tasks}
        persisted = sorted(os.listdir(os.path.join(tasks["nodes"].working_dir, "beeond")))
        with open(os.path.join(tasks["combine"].working_dir, "out")) as stream:
            combined = stream.read()
        with open(os.path.join(tasks["report"].working_dir, "report.txt")) as stream:
            lines = int(stream.read().strip())
        shared = workflow.get_beeond_volume("shared").persist_dir()
        print("Task-scope volume persisted:", ", ".join(persisted))
        print(combined, end="")
        print("Workflow volume persisted to:", shared, "->", sorted(os.listdir(shared)))
        print("Line count from the shared volume:", lines)
        expected = ["node_wn01.txt", "node_wn02.txt", "node_wn03.txt", "node_wn04.txt"]
        ok = persisted == expected and lines == 4 and os.listdir(shared) == ["input.txt"]
        print("Verification:", "ok" if ok else "FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
