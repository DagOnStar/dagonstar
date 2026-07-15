"""Lesson 03: infer and stage a workflow data dependency."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json, tempfile
from pathlib import Path
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import observation_command, workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-03-") as scratch:
    wf = workflow("Meteorology03", scratch)
    prepare = DagonTask(TaskType.BATCH, "prepare", observation_command())
    command = "mkdir -p outputs; awk -F, 'NR>1{s+=$3;n++}END{print s/n}' workflow:///prepare/outputs/observations.csv > outputs/mean.txt"
    mean = DagonTask(TaskType.BATCH, "mean", command)
    wf.add_task(prepare); wf.add_task(mean)
    print("logical command:", mean.command)
    wf.make_dependencies()
    assert [task.name for task in mean.prevs] == ["prepare"]
    wf.run()
    result = Path(mean.working_dir, "outputs/mean.txt").read_text().strip()
    assert result == "13"
    print("staged mean:", result, "in", mean.working_dir)
