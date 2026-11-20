"""Lesson 32: deterministic CWL v1.2 export, file versus ordering edges, and optional cwltool checks."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow


def build(scratch):
    wf = workflow("CWL29", scratch)
    wf.add_task(DagonTask(TaskType.BATCH, "measure", "mkdir -p out; echo 12.5 > out/t.txt"))
    wf.add_task(DagonTask(TaskType.BATCH, "summarise", "cat workflow:///measure/out/t.txt > summary.txt"))
    later = DagonTask(TaskType.BATCH, "announce", "echo done > done.txt")
    wf.add_task(later)
    later.add_dependency_to(wf.find_task_by_name("CWL29", "summarise"))
    return wf


with tempfile.TemporaryDirectory(prefix="dagon-tutorial-32-") as scratch:
    first, second = Path(scratch, "a.cwl"), Path(scratch, "b.cwl")
    build(scratch).saveAsCWL(str(first))
    build(scratch).saveAsCWL(str(second))
    assert first.read_text() == second.read_text(), "export must be deterministic"
    document = json.loads(first.read_text())
    assert document["cwlVersion"] == "v1.2" and document["class"] == "Workflow"
    assert set(document["steps"]) == {"measure", "summarise", "announce"}
    assert scratch not in first.read_text(), "no scratch path may be exported"
    inputs = document["steps"]["announce"]["in"]
    assert any("summarise" in json.dumps(value) for value in inputs.values()), inputs  # ordering-only edge
    if shutil.which("cwltool"):
        completed = subprocess.run(["cwltool", "--validate", str(first)], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr[-2000:]
        print("cwltool --validate: ok")
    else:
        print("cwltool not installed: validation skipped (optional)")
print("steps:", sorted(document["steps"]), "| deterministic export, no scratch paths")
