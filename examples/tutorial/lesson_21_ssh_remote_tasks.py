"""Lesson 21: remote task construction, SSH ports, and quoted remote commands without a network."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import os
from types import SimpleNamespace
from unittest import mock

from dagon.batch import Batch, RemoteBatch
from dagon.remote import RemoteTask

with mock.patch("dagon.remote.SSHManager") as manager:
    default = Batch("collect", "hostname", ip="192.0.2.10", ssh_username="user", keypath="/tmp/key")
    custom = RemoteTask("collect2", "hostname", ip="192.0.2.10", ssh_username="user",
                        keypath="/tmp/key", ssh_port=2200)
    incomplete = RemoteTask("collect3", "hostname", ip="192.0.2.10", keypath="/tmp/key")
assert isinstance(default, RemoteBatch), type(default)
manager.assert_any_call("user", "192.0.2.10", os.path.abspath("/tmp/key"), port=22)
manager.assert_any_call("user", "192.0.2.10", os.path.abspath("/tmp/key"), port=2200)
assert manager.call_count == 2 and incomplete.ssh_connection is None, "no SSH without a username"

sent = []
custom.workflow = SimpleNamespace(logger=SimpleNamespace(error=lambda *args: None))
custom.ssh_connection = SimpleNamespace(execute_command=lambda command: sent.append(command) or {"code": 0})
custom.working_dir = "/scratch/run dir; rm -rf ~"
custom.mkdir_working_dir(custom.working_dir)
assert sent == ["mkdir -p '/scratch/run dir; rm -rf ~/.dagon'"], sent
print("ports:", default.ssh_port, custom.ssh_port, "| incomplete identity opens no connection")
print("quoted remote command:", sent[0])
