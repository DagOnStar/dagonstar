"""Lesson 07: create and reuse checkpoint state."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-07-") as scratch:
    checkpoint = Path(scratch, "checkpoint.json")
    wf = workflow("Meteorology07", scratch, checkpoint_file=str(checkpoint))
    task = DagonTask(TaskType.BATCH, "calculate", "mkdir -p outputs; printf 13 > outputs/mean.txt")
    wf.add_task(task); wf.run(); assert checkpoint.is_file()
    first_dir = task.working_dir
    resumed = workflow("Meteorology07", scratch, checkpoint_file=str(checkpoint))
    second = DagonTask(TaskType.BATCH, "calculate", "mkdir -p outputs; printf 13 > outputs/mean.txt")
    resumed.add_task(second); resumed.run(resume_checkpoint_file=str(checkpoint))
    assert Path(second.working_dir, "outputs/mean.txt").read_text() == "13"
    print("checkpoint:", checkpoint, "scratch reused:", first_dir == second.working_dir)
