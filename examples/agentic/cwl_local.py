"""Export an executable CWL v1.2 graph with an agentic step; run it with cwltool when available."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from agentic_common import producer, quality_control, workflow, write_ini
from dagon.task import DagonTask, TaskType

with tempfile.TemporaryDirectory(prefix="dagon-agentic-cwl-") as scratch:
    def build():
        wf = workflow("AgenticCWL", scratch)
        wf.add_task(producer())
        wf.add_task(quality_control())
        copy = "mkdir -p outputs; cp workflow:///quality_control/outputs/result.json outputs/table.json"
        wf.add_task(DagonTask(TaskType.BATCH, "consume", copy))
        return wf

    first, second = Path(scratch, "a.cwl"), Path(scratch, "b.cwl")
    build().saveAsCWL(first)
    build().saveAsCWL(second)
    assert first.read_text() == second.read_text(), "export must be deterministic"
    document = json.loads(first.read_text())
    assert document["inputs"] == {"dagon_config": "File"}
    assert document["steps"]["quality_control"]["run"]["baseCommand"] == ["dagon-agent-runner", "run"]
    assert scratch not in first.read_text(), "no scratch path may be exported"
    if shutil.which("cwltool") and shutil.which("dagon-agent-runner"):
        job = Path(scratch, "job.json")
        job.write_text(json.dumps({"dagon_config": {"class": "File", "path": str(write_ini(scratch))}}))
        completed = subprocess.run(["cwltool", "--no-container", "--outdir", str(Path(scratch, "out")),
                                    str(first), str(job)], capture_output=True, text=True, cwd=scratch)
        assert completed.returncode == 0, completed.stderr[-2000:]
        outputs = json.loads(completed.stdout)
        evaluation = json.loads(Path(outputs["quality_control_evaluation"]["path"]).read_text())
        assert evaluation["accepted"] is True
        print("cwltool executed producer -> agent -> consumer; accepted")
    else:
        print("exported and checked; cwltool or dagon-agent-runner not installed, execution skipped")
