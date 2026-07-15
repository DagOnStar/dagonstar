"""Lesson 06: compare COPY and LINK input materialisation."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path
from dagon import DataMover
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import observation_command, workflow


def run(mode):
    scratch = tempfile.TemporaryDirectory(prefix="dagon-tutorial-06-")
    wf = workflow("Meteorology06" + mode.name, scratch.name); wf.set_data_mover(mode)
    producer = DagonTask(TaskType.BATCH, "prepare", observation_command())
    consumer = DagonTask(TaskType.BATCH, "consume", "cat workflow:///prepare/outputs/observations.csv > consumed.csv")
    wf.add_task(producer); wf.add_task(consumer); wf.run()
    staged = next(Path(consumer.working_dir).glob("**/prepare/outputs/observations.csv"))
    linked = staged.is_symlink()
    print(mode.name, "is_symlink=", linked, staged)
    return scratch, linked

copy_tmp, copied = run(DataMover.COPY); link_tmp, linked = run(DataMover.LINK)
assert copied is False and linked is True
copy_tmp.cleanup(); link_tmp.cleanup()
