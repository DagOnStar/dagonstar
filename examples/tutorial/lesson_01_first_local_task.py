"""Lesson 01: execute one deterministic local task."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.meteorological_data import CSV
from examples.tutorial.common.support import observation_command, require_text, workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-01-") as scratch:
    wf = workflow("Meteorology01", scratch)
    task = DagonTask(TaskType.BATCH, "prepare_observations", observation_command())
    wf.add_task(task)
    wf.run()
    result = Path(task.working_dir, "outputs", "observations.csv")
    require_text(result, CSV)
    print("verified", result)
