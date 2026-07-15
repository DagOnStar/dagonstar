"""Lesson 08: launch asynchronously and observe lifecycle events."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-08-") as scratch:
    wf = workflow("Meteorology08", scratch); events = []
    wf.add_listener("on_workflow_start", lambda _: events.append("workflow_start"))
    wf.add_listener("on_workflow_end", lambda _: events.append("workflow_end"))
    wf.add_task(DagonTask(TaskType.BATCH, "analyse", "sleep 0.05; true"))
    thread = wf.launch(); assert thread.is_alive() or events
    assert wf.wait(5); assert events == ["workflow_start", "workflow_end"]
    print("events:", events)
