"""Deterministic bounded observation with no device or network dependency."""
import json
import tempfile
from pathlib import Path
from dagon import Workflow
from dagon.task import DagonTask, TaskType

with tempfile.TemporaryDirectory(prefix="dagonstar-iot-") as scratch:
    config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
              "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"},
              "slurm": {"partition": ""}}
    workflow = Workflow("IoTObserve", config=config)
    observe = DagonTask(TaskType.IOT, "observe_temperature", operation="observe", provider="mock",
        target={"device_id": "station-01"}, resource="temperature",
        request={"events": [{"sequence": 1, "value": 20.1, "unit": "Cel"},
                            {"sequence": 2, "value": 20.4, "unit": "Cel"},
                            {"sequence": 3, "value": 20.8, "unit": "Cel"}]},
        completion={"mode": "sample_count", "count": 3, "timeout_seconds": 10},
        outputs={"observations": "outputs/observations.json"})
    workflow.add_task(observe); workflow.run()
    result = json.loads(Path(observe.working_dir, "outputs/observations.json").read_text())
    assert [event["sequence"] for event in result["events"]] == [1, 2, 3]
    print(json.dumps(result, sort_keys=True))
