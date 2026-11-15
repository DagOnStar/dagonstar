"""Lesson 30: an edge-to-cloud synthesis graph: IoT -> Native -> agentic QC -> FaaS, original types kept."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "agentic"))
import json
import tempfile
from pathlib import Path

from agentic_common import quality_control, read, workflow  # noqa: E402
from dagon import Status  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

EVENTS = [{"id": n, "station": "SYN00%d" % (1 + n % 2), "temperature_c": 11.0 + n} for n in (1, 2, 3, 4)]

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-30-") as scratch:
    wf = workflow("Continuum30", scratch)
    edge = DagonTask(TaskType.IOT, "edge", operation="observe", provider="mock",
                     target={"device_id": "station-01"}, resource="temperature",
                     request={"events": [dict(item, sequence=item["id"]) for item in EVENTS]},
                     completion={"mode": "sample_count", "count": 4, "timeout_seconds": 10},
                     outputs={"observations": "outputs/observations.json"})
    normalise = DagonTask(TaskType.NATIVE, "normalise",
                          "examples.tutorial.common.native_functions:events_to_observations",
                          inputs={"input_file": "workflow:///edge/outputs/observations.json"},
                          outputs={"output_file": "observations.json"})
    # The agent treats the normalised table as untrusted data and is evaluated independently.
    qc = quality_control("qc", tools=[], inputs={"source": "workflow:///normalise/outputs/observations.json"})
    publish = DagonTask(TaskType.FAAS, "publish", provider="mock", function="archive",
                        inputs={"table": {"document": "workflow:///qc/outputs/result.json"}},
                        outputs={"receipt": "receipt.json"},
                        provider_options={"mock": {"response": {"status": "succeeded",
                                                                "outputs": {"receipt": {"stored": True}}}}})
    for task in (edge, normalise, qc, publish):
        wf.add_task(task)
    wf.run()
    states = {task.name: task.status for task in wf.tasks}
    assert all(state is Status.FINISHED for state in states.values()), states
    assert [type(task).__name__ for task in wf.tasks] == ["IoTTask", "NativeTask", "AgenticTask", "FaaSTask"]
    assert read(qc, "outputs/evaluation.json")["accepted"] is True
    assert len(read(qc, "outputs/result.json")["observations"]) == 4
    receipt = json.loads(Path(publish.working_dir, "outputs", "receipt.json").read_text(encoding="utf-8"))
    assert receipt == {"stored": True}
print("continuum graph:", " -> ".join(type(task).__name__ for task in wf.tasks), "| QC accepted | receipt stored")
