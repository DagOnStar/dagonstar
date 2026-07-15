"""Lesson 05: inspect task artifacts without guessing a /tmp path."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import observation_command, workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-05-") as scratch:
    wf = workflow("Meteorology05", scratch)
    task = DagonTask(TaskType.BATCH, "prepare", observation_command())
    wf.add_task(task); wf.run()
    meta = Path(task.working_dir, ".dagon")
    names = sorted(path.name for path in meta.iterdir())
    assert Path(task.working_dir, "outputs/observations.csv").is_file()
    assert names
    print("task directory:", task.working_dir); print(".dagon files:", names)
