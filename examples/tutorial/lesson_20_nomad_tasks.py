"""Lesson 20: Nomad job specification, polling, logs, and purge against a mocked HTTP API."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from unittest import mock

from dagon.nomad_task import NomadTask
from dagon.task import DagonTask, TaskType


class Response:
    def __init__(self, payload=None, text=""):
        self.payload, self.text, self.status_code = payload, text, 200

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


task = DagonTask(TaskType.NOMAD, "forecast", "python forecast.py", image="python:3.12-slim",
                 nomad_address="http://nomad.invalid:4646", cpu=500, memory=1024, datacenter="edge")
assert isinstance(task, NomadTask)
task.workflow = mock.Mock()
allocations = [{"ID": "alloc-1", "TaskStates": {"dagon-task": {
    "State": "dead", "Events": [{"Type": "Terminated", "ExitCode": 0}]}}}]
with mock.patch("dagon.nomad_task.requests.post", return_value=Response({"EvalID": "e1"})) as post, \
        mock.patch("dagon.nomad_task.requests.get", side_effect=[
            Response({"Status": "running"}), Response({"Status": "dead"}), Response(allocations),
            Response(text="forecast done\n")]) as get, \
        mock.patch("dagon.nomad_task.requests.delete", return_value=Response()) as delete, \
        mock.patch("dagon.nomad_task.time.sleep"):
    task._submit_job()
    spec = post.call_args.kwargs["json"]["Job"]
    result = task._wait_for_completion(timeout=30)
    logs = task._get_logs()
    task._cleanup_job()
assert spec["Datacenters"] == ["edge"] and spec["TaskGroups"][0]["Tasks"][0]["Resources"]["CPU"] == 500
assert result["code"] == 0 and task.allocation_id == "alloc-1" and logs == "forecast done\n"
assert get.call_count == 4
delete.assert_called_once_with("http://nomad.invalid:4646/v1/job/" + task.job_id,
                               params={"purge": "true"}, timeout=10)
print("job", task.job_id, "-> exit", result["code"], "| logs:", logs.strip(), "| purged (mocked API)")
