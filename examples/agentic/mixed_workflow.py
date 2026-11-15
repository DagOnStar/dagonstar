"""AGENTIC consumes BATCH output and feeds NATIVE, IOT, and a second AGENTIC task."""
import sys
import tempfile
from pathlib import Path

from agentic_common import producer, quality_control, read, workflow
from dagon import Status
from dagon.task import DagonTask, TaskType

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    wf = workflow("AgenticMixed", scratch)
    wf.add_task(producer())
    first = quality_control()
    review = quality_control("review", tools=[], inputs={"source": "workflow:///quality_control/outputs/result.json"})
    count = DagonTask(TaskType.NATIVE, "count", "examples.tutorial.common.native_functions:count_records",
                      inputs={"input_file": "workflow:///review/outputs/result.json"},
                      outputs={"output_file": "count.json"})
    notify = DagonTask(TaskType.IOT, "notify", operation="observe", provider="mock",
                       request={"events": [{"evaluation": "workflow:///review/outputs/evaluation.json"}]},
                       completion={"mode": "first_event"}, outputs={"observations": "outputs/notice.json"})
    for task in (first, review, count, notify):
        wf.add_task(task)
    wf.run()
    assert all(task.status is Status.FINISHED for task in wf.tasks), [(t.name, t.status) for t in wf.tasks]
    assert review.prevs == [first]
    assert read(count, "outputs/count.json") == {"count": 4}
    print("mixed graph finished:", [type(task).__name__ for task in wf.tasks])
