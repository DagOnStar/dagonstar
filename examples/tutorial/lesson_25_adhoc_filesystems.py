"""Lesson 25: plug a new ad-hoc file system into DAGonStar, bind it at workflow and task scope,
and stream items between two tasks through it.  The built-in providers are only inspected
under portable emulation; no external storage software is started."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import os
import shutil
import tempfile
from pathlib import Path

from dagon.adhoc import AdHocFileSystem, available_providers, register_provider, unregister_provider
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow


class ScratchDirectory(AdHocFileSystem):
    """A node-local directory served through the common ad-hoc interface (no daemon)."""

    provider = "lesson25-directory"
    access = "posix"
    supports_streaming = True

    def __init__(self, workflow, name="default", path=None):
        super().__init__(workflow, name)
        self.path = path or os.path.join(workflow.get_scratch_dir_base(), ".lesson25-" + name)
        self.events = []

    @property
    def task_path(self):
        return self.path

    def start(self):
        if not self.started:
            os.makedirs(self.path, exist_ok=True)
            self._started = True
            self.events.append("start")

    def is_ready(self):
        return self.started and os.path.isdir(self.path)

    def stop(self):
        if not self.started:
            return None
        self._started = False
        shutil.rmtree(self.path, ignore_errors=True)
        self.events.append("stop")
        return 0


# 1. A new storage system is one class and one registration; built-in names are protected.
register_provider("lesson25-directory", ScratchDirectory, replace=True)
assert "lesson25-directory" in available_providers()
try:
    register_provider("dagonfs", ScratchDirectory)
except ValueError as error:
    protected = str(error)
else:
    raise AssertionError("a built-in provider name must not be replaced silently")

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-25-") as scratch:
    # 2. A workflow-scope default volume plus a task-scope volume exported under a chosen name.
    wf = workflow("Adhoc25", scratch, extra={"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "4"}})
    shared = wf.create_adhoc_filesystem("lesson25-directory", name="shared", default=True)
    write = DagonTask(TaskType.BATCH, "write", 'echo 42 > "$DAGON_ADHOC_SHARED_PATH/answer.txt"')
    read = DagonTask(TaskType.BATCH, "read",
                     'echo workflow:///write/ > /dev/null; '
                     'cp "$DAGON_ADHOC_SHARED_PATH/answer.txt" "$MYVOLUME/copy.txt"; '
                     'cat "$MYVOLUME/copy.txt" > answer.txt; echo "$DAGON_ADHOC_NAMES" > names.txt')
    wf.add_task(write)
    wf.add_task(read)
    private = read.create_adhoc_filesystem("lesson25-directory", name="private", export="MYVOLUME")
    wf.run()
    assert Path(read.working_dir, "answer.txt").read_text().strip() == "42"
    assert Path(read.working_dir, "names.txt").read_text().strip() == "private,shared"
    assert shared.events == ["start", "stop"] and private.events == ["start", "stop"]
    assert not os.path.exists(private.path), "a task-scope volume is removed after its task"
    print("workflow-scope 'shared' and task-scope 'private' (exported as $MYVOLUME) were bound to read")

    # 3. A stream: the consumer reads workflow:///produce/items?stream while the producer runs.
    stream = workflow("Stream25", scratch)
    produce = DagonTask(TaskType.BATCH, "produce",
                        'for i in 1 2 3 4; do echo $i > item-$i; '
                        '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i > /dev/null || exit 1; '
                        'done')
    consume = DagonTask(TaskType.BATCH, "consume",
                        'total=0; for item in $("$DAGON_PYTHON" -m dagon.adhoc stream items '
                        'workflow:///produce/items?stream --into got); do total=$((total + $(cat "$item"))); done; '
                        'echo $total > total.txt')
    stream.add_task(produce)
    stream.add_task(consume)
    channel = stream.create_adhoc_filesystem("lesson25-directory", name="channel")
    channel.bind(produce)
    channel.bind(consume)
    stream.run()
    assert consume.stream_prevs == [produce]
    assert Path(consume.working_dir, "total.txt").read_text().strip() == "10"
    print("consume received 4 verified items from produce through ?stream (total 10)")

    # 4. The built-in providers expose the same interface; under emulation none is started.
    emulated = workflow("Builtin25", scratch, portable_emulation=True)
    access = {
        "dagonfs": emulated.create_adhoc_filesystem("dagonfs", name="ram").access,
        "capio": emulated.create_adhoc_filesystem("capio", name="pipe").access,
        "hercules": emulated.create_adhoc_filesystem("hercules", name="tier", config="hercules.conf").access,
        "dynostore": emulated.create_adhoc_filesystem("dynostore", name="objects", catalog="lesson25").access,
    }
    assert access == {"dagonfs": "posix", "capio": "preload", "hercules": "preload", "dynostore": "object"}, access
unregister_provider("lesson25-directory")
print("built-in name protected:", protected)
print("built-in access modes:", ", ".join("%s=%s" % item for item in sorted(access.items())))
