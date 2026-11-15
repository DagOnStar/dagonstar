"""Lesson 31: operations: service API registration (mocked), runner environments, platform helpers,
JSON round trips, and the packaged agent runner."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from dagon import Workflow
from dagon.platform_support import bash_executable, shell_path
from dagon.runtime_env import PACKAGE_ROOT, runner_environment
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import config


class Response:
    status_code, reason = 201, "Created"

    def json(self):
        return {"id": 7}


with tempfile.TemporaryDirectory(prefix="dagon-tutorial-31-") as scratch:
    service = config(scratch, {"dagon_service": {"use": "True", "route": "http://dagon-service.invalid"}})
    with mock.patch("dagon.api.requests.head") as head, \
            mock.patch("dagon.api.requests.post", return_value=Response()) as post:
        registered = Workflow("Ops31", config=service)
        registered.add_task(DagonTask(TaskType.BATCH, "hello", "echo hello > hello.txt"))
    head.assert_called_once_with("http://dagon-service.invalid/check")
    assert registered.workflow_id == 7 and post.call_args_list[0].args[0].endswith("/create")
    assert post.call_args_list[1].args[0].endswith("/add_task/7")

    offline = Workflow("Ops31Offline", config=config(scratch))
    offline.add_task(DagonTask(TaskType.BATCH, "hello", "echo hello > hello.txt"))
    restored = Workflow("placeholder", config=config(scratch), jsonload=offline.as_json())
    assert [task.name for task in restored.tasks] == ["hello"], "JSON round trip keeps the graph"

environment = runner_environment({"DAGON_EXAMPLE": "1"}, base={"PYTHONPATH": "/site/first"})
assert environment["PYTHONPATH"].split(os.pathsep) == ["/site/first", PACKAGE_ROOT]
assert environment["DAGON_EXAMPLE"] == "1"
assert isinstance(shell_path(str(Path.cwd())), str) and bash_executable()

runner = shutil.which("dagon-agent-runner")
if runner:
    completed = subprocess.run([runner, "--help"], capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0 and "run" in completed.stdout
    print("packaged console script found:", Path(runner).name)
else:
    print("dagon-agent-runner not on PATH: install with 'python -m pip install -e .' (check skipped)")
print("service registration mocked: workflow id", registered.workflow_id,
      "| runner PYTHONPATH keeps user entries first")
print(json.dumps({"bash": bash_executable(), "package_root_appended": True}))
