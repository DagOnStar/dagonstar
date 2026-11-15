"""Lesson 17: Docker task construction and command generation with a mocked Docker client."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import os
from unittest import mock

try:
    from dagon.docker_task import DockerRemoteTask, DockerTask
except ImportError as error:  # the docker extra is optional
    assert "dagonstar[docker]" in str(error), error
    print("skipped (optional docker extra not installed):", error)
    raise SystemExit(0)
from dagon.task import DagonTask, TaskType

with mock.patch("dagon.docker_task.docker.from_env") as from_env:
    task = DagonTask(TaskType.DOCKER, "stats", "python stats.py", image="python:3.12-slim",
                     working_dir="/work dir", remove=True)
    assert isinstance(task, DockerTask) and from_env.called, "a client is created; no container yet"
    task.container = mock.Mock(id="c0ffee")
    wrapped = task.include_command("python stats.py")
    assert "docker exec -t c0ffee" in wrapped and "'/work dir'" in wrapped, wrapped
    with mock.patch("dagon.docker_task.docker.DockerClient") as remote_client, \
            mock.patch("dagon.remote.SSHManager") as ssh:
        remote = DockerRemoteTask("remote_stats", "python stats.py", image="python:3.12-slim",
                                  ip="192.0.2.10", ssh_username="user", keypath="/tmp/key",
                                  working_dir="/home/user/work", ssh_port=2200, pull=False)
    ssh.assert_called_once_with("user", "192.0.2.10", os.path.abspath("/tmp/key"), port=2200)
    remote_client.assert_called_once_with(base_url="ssh://user@192.0.2.10:2200", timeout=300)
    assert remote.pull is False
print("local exec wrapper:", wrapped.splitlines()[0][:80])
print("remote Docker endpoint: ssh://user@192.0.2.10:2200 (mocked; no daemon contacted)")
