"""A task's command exit status must decide the task status.

Launchers capture standard output with ``command | tee``.  The status of that
pipeline is the status of ``tee``, so failing commands used to be reported as
FINISHED.  These tests run real launchers locally (no Docker or Slurm).
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from dagon import Workflow
from dagon.batch import Batch, Slurm
from dagon.platform_support import bash_executable
from dagon.task import DagonTask, TaskType


def make_config(scratch):
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
    }


class LocalBatchExitStatusTests(unittest.TestCase):
    def run_workflow(self, *commands, fails=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        workflow = Workflow("exit-status", config=make_config(self.tmp.name))
        tasks = [DagonTask(TaskType.BATCH, "t%d" % index, command)
                 for index, command in enumerate(commands)]
        for task in tasks:
            workflow.add_task(task)
        workflow.make_dependencies()
        if fails:
            with self.assertLogs(level="ERROR"):
                workflow.run()
        else:
            workflow.run()
        return tasks

    def test_failing_command_fails_the_task(self):
        (task,) = self.run_workflow("echo before; sh -c 'exit 3'", fails=True)
        self.assertEqual("FAILED", task.status.name)
        with open(os.path.join(task.working_dir, ".dagon", "stdout.txt")) as stream:
            self.assertEqual("", stream.read())  # only the last command is piped

    def test_successful_command_finishes_and_keeps_stdout(self):
        (task,) = self.run_workflow("echo hello")
        self.assertEqual("FINISHED", task.status.name)
        with open(os.path.join(task.working_dir, ".dagon", "stdout.txt")) as stream:
            self.assertEqual("hello\n", stream.read())

    def test_failure_is_not_hidden_by_downstream_success(self):
        first, second = self.run_workflow("sh -c 'exit 3' > out.txt",
                                          "cat workflow:///t0/out.txt", fails=True)
        self.assertEqual("FAILED", first.status.name)
        self.assertNotEqual("FINISHED", second.status.name)


class LauncherFragmentExitStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, ".dagon"))

    def status_of(self, fragment):
        result = subprocess.run([bash_executable(), "-c", fragment + 'echo "rc=$?"\n'],
                                cwd=self.tmp.name, capture_output=True, text=True)
        return result.stdout.strip().splitlines()[-1]

    def test_batch_fragment_reports_command_status(self):
        task = Batch("b", "true", working_dir=self.tmp.name)
        self.assertEqual("rc=3", self.status_of(task.include_command("sh -c 'exit 3'")))
        self.assertEqual("rc=0", self.status_of(task.include_command("true")))

    @unittest.skipIf(os.name == "nt", "BeeOND launchers target Linux compute nodes")
    def test_slurm_beeond_background_fragment_reports_command_status(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = Workflow("wf", config=make_config(scratch))
            task = Slurm("s", "true", working_dir=self.tmp.name, beeond="task")
            workflow.add_task(task)
            self.assertEqual("rc=3", self.status_of(task.include_command("sh -c 'exit 3'")))
            self.assertEqual("rc=0", self.status_of(task.include_command("true")))

    @unittest.skipIf(os.name == "nt" or shutil.which("sh") is None, "POSIX sh is required")
    def test_docker_exec_body_reports_command_status(self):
        try:
            from dagon.docker_task import DockerTask
        except ImportError:
            self.skipTest("the optional docker extra is not installed")
        task = object.__new__(DockerTask)
        task.working_dir = self.tmp.name
        task.container = SimpleNamespace(id="abc123")
        for command, expected in (("echo out; sh -c 'exit 3'", 3), ("echo ok", 0)):
            argv = shlex.split(task.include_command(command))
            self.assertEqual(["docker", "exec", "-t", "abc123", "sh", "-c"], argv[:6])
            # Run the body the container would run, with the local sh.
            result = subprocess.run(["sh", "-c", argv[6]], capture_output=True, text=True)
            self.assertEqual(expected, result.returncode, result.stderr)
            with open(os.path.join(self.tmp.name, ".dagon", "stdout.txt")) as stream:
                self.assertIn("out" if expected else "ok", stream.read())


if __name__ == "__main__":
    unittest.main()
