"""Lesson 22: cloud task configuration with deferred provider import; nothing is provisioned."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import builtins
from unittest import mock

from dagon.remote import CloudTask
from dagon.task import DagonTask, TaskType

already_loaded = "libcloud" in sys.modules
task = DagonTask(TaskType.CLOUD, "regional_model", "hostname", provider="dummy",
                 ssh_username="cloud-user", key_options={"key_path": "/tmp/key"},
                 instance_flavour={"image": "image-id", "size": "small"},
                 instance_name="dagon-teaching", stop_instance=True)
assert isinstance(task, CloudTask)
assert task.node is None and task.ssh_connection is None, "construction must not create or reach a host"
assert already_loaded or "libcloud" not in sys.modules, "the provider SDK is imported lazily"

task.workflow = mock.Mock(name="workflow")
task.workflow.name = "workflow"
real_import = builtins.__import__


def without_libcloud(name, *args, **kwargs):
    if name == "libcloud" or name.startswith("libcloud."):
        error = ImportError("No module named 'libcloud'")
        error.name = "libcloud"
        raise error
    return real_import(name, *args, **kwargs)


previous = sys.modules.pop("dagon.cloud", None)
try:
    with mock.patch("builtins.__import__", side_effect=without_libcloud):
        try:
            task.execute()
        except ImportError as error:
            message = str(error)
        else:
            raise AssertionError("execution without the cloud extra must fail with guidance")
finally:
    if previous is not None:
        sys.modules["dagon.cloud"] = previous
    else:
        sys.modules.pop("dagon.cloud", None)
assert "dagonstar[cloud]" in message, message
print("constructed without provisioning; missing extra reported as:", message)
