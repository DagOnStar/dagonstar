"""Export a workflow containing a meta-task as CWL v1.2 and optionally run it.

    python examples/cwl/export_meta_workflow.py --output /tmp/meta.cwl
    cwltool --validate /tmp/meta.cwl
    python examples/cwl/export_meta_workflow.py --output /tmp/meta.cwl --run

The meta-task becomes a ``CommandLineTool`` that runs ``dagon-meta-runner run``
with the credential-free specification embedded through
``InitialWorkDirRequirement``.  Its ``workflow://`` input is bound to the
producer step's ``File`` output (``--bind REFERENCE=$(inputs.in_0.path)``) and
each declared output is a CWL output (``outputs/<path>``).  A ``dagon:MetaTask``
hint records the engine and the SHA-256 of the external workflow definition.

Boundary: the external engine and the workflow definition named in the
specification must be installed on the CWL execution host (here the
engine-free ``examples/meta/workflows/tiny_engine.py`` and ``python3``), and
``dagon-meta-runner`` must be on ``PATH`` (``pip install -e .``).  Without
``--run`` the script only exports and, when ``cwltool`` is installed, validates.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dagon import Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

ENGINE = ROOT / "examples" / "meta" / "workflows" / "tiny_engine.py"


def build_workflow(scratch: str) -> Workflow:
    config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
              "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
    workflow = Workflow("DAGonStar CWL meta-task", config=config)
    workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                "mkdir -p data; printf 'sea wind sea\\n' > data/text.txt"))
    workflow.add_task(DagonTask(TaskType.META, "wordcount", engine="command", workflow=str(ENGINE),
                                inputs={"text": "workflow:///producer/data/text.txt", "top": 1},
                                outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}},
                                engine_options={"command": ["python3", "{workflow}", "{parameters_file}"]}))
    return workflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", help="CWL file to write (default: a temporary file)")
    parser.add_argument("--run", action="store_true", help="also run the exported workflow with cwltool")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dagon-cwl-meta-") as scratch:
        target = Path(arguments.output or Path(scratch, "meta.cwl"))
        build_workflow(scratch).saveAsCWL(str(target))
        document = json.loads(target.read_text(encoding="utf-8"))
        step = document["steps"]["wordcount"]
        assert step["run"]["baseCommand"] == ["dagon-meta-runner", "run"]
        assert step["in"]["in_0"].startswith("producer/")
        print("exported", target, "meta step hint:", json.dumps(step["run"]["hints"]["dagon:MetaTask"], sort_keys=True))
        if shutil.which("cwltool"):
            subprocess.run(["cwltool", "--validate", str(target)], check=True, capture_output=True, text=True)
            print("cwltool --validate: ok")
        if arguments.run:
            if not (shutil.which("cwltool") and shutil.which("dagon-meta-runner")):
                print("--run needs cwltool and dagon-meta-runner on PATH (pip install -e .)")
                return 1
            outdir = Path(scratch, "out")
            completed = subprocess.run(["cwltool", "--outdir", str(outdir), str(target)],
                                       capture_output=True, text=True)
            if completed.returncode:
                print(completed.stderr[-3000:])
                return completed.returncode
            print("cwltool run: ok; counts =", Path(outdir, "counts.tsv").read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
