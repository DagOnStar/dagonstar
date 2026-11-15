"""Lesson 18: Apptainer image preparation and execution commands with subprocess mocked."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import os
import tempfile
from unittest import mock

from dagon.apptainer_task import ApptainerTask
from dagon.task import DagonTask, TaskType

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-18-") as scratch:
    task = DagonTask(TaskType.APPTAINER, "regrid", "python regrid.py",
                     image="docker://python:3.12-slim", tmp_dir=scratch)
    assert isinstance(task, ApptainerTask)
    task.workflow = mock.Mock()
    task.work_dir = scratch
    completed = mock.Mock(stdout="ok", stderr="", returncode=0)
    with mock.patch("dagon.apptainer_task.subprocess.run", return_value=completed) as run:
        task._prepare_sif_image()
        build = list(run.call_args[0][0])
        task.overlay_file = os.path.join(scratch, "overlay.img")
        task.staging_dir = os.path.join(scratch, "staging")
        task.bind_paths = []
        assert task.exec_in_container("python regrid.py") == "ok"
        execute = list(run.call_args[0][0])
    assert "apptainer" in build and "build" in build and "docker://python:3.12-slim" in build, build
    assert "apptainer" in execute and "exec" in execute and "--overlay" in execute, execute
    assert task.sif_file.endswith(".sif")
    with mock.patch("dagon.apptainer_task.subprocess.run") as run, \
            mock.patch("dagon.apptainer_task.os.path.exists", return_value=True):
        task.image = os.path.join(scratch, "prebuilt.sif")
        task._prepare_sif_image()
        run.assert_not_called()
print("image build and exec commands generated (subprocess mocked); a prebuilt SIF is reused without a build")
