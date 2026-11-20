"""Lesson 26: TaskType.VOLUME creates an ad-hoc volume that sibling tasks address as
workflow:///<task>/<volume>/..., streams through it, and releases it either with a destroy
volume task (staging results out) or by reference counting.  Built-in providers run under
portable emulation: a local directory stands in for the volume and no provider is started."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path

from dagon import Status
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

EXTRA = {"batch": {"run_base": "", "threads": "6"}}


def flow(name, scratch):
    extra = {"batch": dict(EXTRA["batch"], scratch_dir_base=scratch)}
    return workflow(name, scratch, extra=extra, portable_emulation=True)


with tempfile.TemporaryDirectory(prefix="dagon-tutorial-26-") as scratch:
    # 1. Create, share, destroy with stage-out (DAGonFS, emulated).
    wf = flow("Volume26", scratch)
    prep = DagonTask(TaskType.BATCH, "Prep", "mkdir -p data; seq 1 4 > data/n.txt")
    abc = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz",
                    stage_in={"in": "workflow:///Prep/data"})
    square = DagonTask(TaskType.BATCH, "Square", "mkdir -p workflow:///Abc/xyz/out ; "
                       "for i in $(cat workflow:///Abc/xyz/in/n.txt ); do echo $((i * i)); done "
                       "> workflow:///Abc/xyz/out/square.txt")
    emit = DagonTask(TaskType.BATCH, "Emit",
                     'for i in $(cat workflow:///Abc/xyz/in/n.txt ); do echo $i > item-$i; '
                     '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i > /dev/null; done')
    total = DagonTask(TaskType.BATCH, "Sum",
                      'total=0; for item in $("$DAGON_PYTHON" -m dagon.adhoc stream items '
                      'workflow:///Emit/numbers?stream=xyz --into got); do total=$((total + $(cat "$item"))); done; '
                      'echo $total > sum.txt')
    delete = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                       stage_out={"kept": {"path": "out", "type": "directory"}})
    report = DagonTask(TaskType.BATCH, "Report", "cp workflow:///Del/kept/square.txt square.txt")
    for task in (prep, abc, square, emit, total, delete, report):
        wf.add_task(task)
    wf.make_dependencies()
    assert {task.name for task in delete.prevs} >= {"Square", "Emit", "Sum"}, delete.prevs
    assert abc in square.prevs and prep in abc.prevs
    wf.run()
    assert all(task.status is Status.FINISHED for task in wf.tasks)
    assert Path(report.working_dir, "square.txt").read_text().split() == ["1", "4", "9", "16"]
    assert Path(total.working_dir, "sum.txt").read_text().strip() == "10"
    assert total.stream_prevs == [emit] and abc.released == "destroyed by Del", abc.released
    print("Del waited for %s; Report read Del's staged-out copy; Sum streamed through xyz"
          % ", ".join(sorted(task.name for task in delete.prevs)))

    # 2. No destroy task: the last finished user releases the volume (reference counting).
    gc = flow("Collected26", scratch)
    tmp = DagonTask(TaskType.VOLUME, "Tmp", provider="capio", volume="tmp")
    write = DagonTask(TaskType.BATCH, "Write", "seq 1 3 > workflow:///Tmp/tmp/n.txt")
    read = DagonTask(TaskType.BATCH, "Read", "wc -l < workflow:///Tmp/tmp/n.txt > count.txt")
    for task in (tmp, write, read):
        gc.add_task(task)
    read.add_dependency_to(write)
    gc.run()
    assert tmp.released == "no task refers to it", tmp.released
    assert Path(read.working_dir, "count.txt").read_text().strip() == "3"
    print("Tmp (CAPIO, emulated) released by reference counting:", tmp.released)

    # 3. A task that runs after the destroy task cannot use the volume.
    bad = flow("Refused26", scratch)
    owner = DagonTask(TaskType.VOLUME, "Own", provider="dagonfs", volume="v")
    drop = DagonTask(TaskType.VOLUME, "Drop", action="destroy", volume="workflow:///Own/v")
    late = DagonTask(TaskType.BATCH, "Late", "cat workflow:///Own/v/x.txt")
    for task in (owner, drop, late):
        bad.add_task(task)
    late.add_dependency_to(drop)
    try:
        bad.make_dependencies()
    except ValueError as error:
        refused = str(error)
    else:
        raise AssertionError("a user after the destroy task must be refused")
print("refused:", refused)
