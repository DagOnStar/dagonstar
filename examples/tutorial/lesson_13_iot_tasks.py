"""Lesson 13: bounded IoT observation and the non-replay rule for uncertain actuation."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import tempfile
from pathlib import Path

from dagon.iot import IoTUnknownOutcomeError
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

try:
    DagonTask(TaskType.IOT, "unbounded", operation="observe", completion={})
except ValueError as error:
    print("unbounded observation rejected:", error)
else:
    raise AssertionError("an observation without a completion bound must be rejected")

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-13-") as scratch:
    wf = workflow("IoT13", scratch)
    observe = DagonTask(TaskType.IOT, "observe_temperature", operation="observe", provider="mock",
                        target={"device_id": "station-01"}, resource="temperature",
                        request={"events": [{"sequence": n, "value": 20.0 + n / 10, "unit": "Cel"}
                                            for n in (1, 2, 3)]},
                        completion={"mode": "sample_count", "count": 3, "timeout_seconds": 10},
                        outputs={"observations": "outputs/observations.json"})
    wf.add_task(observe)
    wf.run()
    result = json.loads(Path(observe.working_dir, "outputs/observations.json").read_text(encoding="utf-8"))
    assert [event["sequence"] for event in result["events"]] == [1, 2, 3]
    assert observe.reuse_checkpoint(), "valid output hashes allow checkpoint reuse"
    Path(observe.working_dir, "outputs/observations.json").unlink()
    assert not observe.reuse_checkpoint(), "a missing output invalidates the checkpoint"

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-13-") as scratch:
    wf = workflow("actuate", scratch)
    valve = DagonTask(TaskType.IOT, "valve", operation="actuate", action="close",
                      completion={"mode": "acknowledged", "timeout_seconds": 2},
                      delivery={"max_attempts": 1}, provider_options={"unknown_outcome": True})
    wf.add_task(valve)
    try:
        valve.execute()
    except IoTUnknownOutcomeError:
        certainty = wf.checkpoints["actuate.valve"]["outcome_certainty"]
    else:
        raise AssertionError("an unacknowledged non-idempotent actuation must fail")
    assert certainty == "unknown", certainty
print("observed sequences: [1, 2, 3] | uncertain actuation recorded as:", certainty)
