"""Scheduler-aware pre-staging for RemoteSlurm tasks without a network connection.

``SSHManager`` is replaced by :class:`LoopbackSSH`, which stands in for the
remote login host: it records every command and file it is asked to create and
runs them with the local bash in a temporary directory.  ``sbatch`` commands
are intercepted and recorded together with what existed on the "remote"
scratch at submission time.  This tests the ordering and the SSH code path; it
is not evidence about any real cluster.
"""
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dagon import Workflow
from dagon.batch import Batch, RemoteSlurm, Slurm
from dagon.platform_support import bash_executable
from dagon.prestage import MARKER_NAME, SchedulerSubmissionError, StageInFailedError
from dagon.task import Task

from tests.helpers import canned_context_script, scratch_config


class LoopbackSSH:
    """A fake SSH connection whose remote host is the local machine."""

    instances = []

    def __init__(self, username, host, keypath, port=22):
        self.username, self.host, self.keypath, self.port = username, host, keypath, port
        self.events = []
        self.fail_on = None          # substring of a command that raises (disconnect)
        self.fail_create = None      # substring of a filepath whose creation fails
        self.reject_sbatch = False
        self.omit_job_id = False     # exit 0 without printing a job identifier
        LoopbackSSH.instances.append(self)

    def create_file(self, filepath, content):
        self.events.append(("create", os.path.basename(filepath)))
        if self.fail_create and self.fail_create in filepath:
            raise IOError("Failed to create file %s" % filepath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", newline="\n") as stream:
            stream.write(content)

    def execute_command(self, command):
        if self.fail_on and self.fail_on in command:
            self.events.append(("disconnect", command))
            raise EOFError("SSH session not active")
        argv = shlex.split(command) if not command.startswith("if ") else []
        if argv and argv[0] == "sbatch":
            directory = argv[argv.index("-D") + 1]
            script = argv[argv.index("-W") + 1]
            self.events.append(("sbatch", {
                "options": argv[1:argv.index("-J")],
                "marker_present": os.path.isfile(os.path.join(directory, ".dagon", MARKER_NAME)),
                "inputs": sorted(str(path.relative_to(directory)) for path in
                                 Path(directory, ".dagon", "inputs").rglob("*") if path.is_file()),
            }))
            if self.reject_sbatch:
                return {"code": 1, "output": "", "message": "sbatch: error: invalid account"}
            completed = subprocess.run([bash_executable(), script], cwd=directory, capture_output=True, text=True)
            banner = "77\n" if "--parsable" in argv else "Submitted batch job 77\n"
            if self.omit_job_id:
                return {"code": 0, "output": "", "message": ""}
            return {"code": completed.returncode, "output": banner + completed.stdout,
                    "message": completed.stderr}
        if argv[:2] == ["bash", "-c"]:
            # Inline scripts (checkpoint identity check, lock release) write no file.
            self.events.append(("command", "bash -c"))
        elif argv and argv[0] == "bash":
            self.events.append(("bash", os.path.basename(argv[-1])))
        else:
            self.events.append(("command", argv[0] if argv else command.split()[0]))
        completed = subprocess.run([bash_executable(), "-c", command], capture_output=True, text=True)
        return {"code": completed.returncode, "output": completed.stdout, "message": completed.stderr}


@unittest.skipIf(os.name == "nt", "the loopback SSH host emulates a POSIX login node")
class RemoteSlurmPreStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.remote = os.path.join(self.tmp.name, "remote-scratch")
        LoopbackSSH.instances = []
        patcher = mock.patch("dagon.remote.SSHManager", LoopbackSSH)
        patcher.start()
        self.addCleanup(patcher.stop)
        context = mock.patch.object(Task, "get_how_im_script", canned_context_script)
        context.start()
        self.addCleanup(context.stop)
        # Fail loudly if anything tried to run a script on the local machine.
        local = mock.patch.object(Batch, "execute_command", side_effect=AssertionError("local execution"))
        local.start()
        self.addCleanup(local.stop)

    def build(self, workflow_pre_stage=True, consumer_pre_stage=None, producer_command="echo alpha > a.txt",
              ssh_port=22):
        workflow = Workflow("wf", config=scratch_config(os.path.join(self.tmp.name, "local")),
                            pre_stage=workflow_pre_stage)
        common = dict(ip="192.0.2.10", ssh_username="hpc-user", keypath=os.path.join(self.tmp.name, "key"),
                      ssh_port=ssh_port)
        producer = Slurm("A", producer_command, working_dir=os.path.join(self.remote, "A"), **common)
        consumer = Slurm("C", "cat workflow:///A/a.txt > c.txt", working_dir=os.path.join(self.remote, "C"),
                         ntasks=200, partition="compute", pre_stage=consumer_pre_stage, **common)
        self.assertIsInstance(consumer, RemoteSlurm)
        workflow.add_task(producer)
        workflow.add_task(consumer)
        return workflow, producer, consumer

    def events(self, task):
        return [event for event in task.ssh_connection.events if event[0] in ("create", "bash", "sbatch",
                                                                             "disconnect")]

    def run_workflow(self, workflow, fails=False):
        if fails:
            with self.assertLogs(level="ERROR"):
                workflow.run()
        else:
            workflow.run()

    def test_pre_stage_survives_the_multiple_inheritance_constructor(self):
        _workflow, _producer, consumer = self.build(consumer_pre_stage=True, ssh_port=2222)
        self.assertIs(True, consumer.pre_stage)
        self.assertTrue(consumer.pre_stage_capable)
        self.assertEqual(2222, consumer.ssh_connection.port)
        self.assertEqual(22, RemoteSlurm("x", "true", ip="192.0.2.1", ssh_username="u",
                                         keypath="/tmp/k").ssh_connection.port)

    def test_stage_in_runs_over_ssh_before_remote_sbatch(self):
        workflow, producer, consumer = self.build()
        self.run_workflow(workflow)
        self.assertEqual("FINISHED", consumer.status.name)
        names = [(kind, detail if kind != "sbatch" else "sbatch") for kind, detail in self.events(consumer)]
        self.assertEqual([("create", "context.sh"), ("bash", "context.sh"),
                          ("create", "stage_in.sh"), ("bash", "stage_in.sh"),
                          ("create", MARKER_NAME + ".tmp"),
                          ("create", "launcher.sh"), ("sbatch", "sbatch")], names)
        submission = self.events(consumer)[-1][1]
        self.assertTrue(submission["marker_present"])
        self.assertEqual([".dagon/inputs/wf/A/a.txt"], submission["inputs"])
        self.assertIn("--ntasks=200", submission["options"])
        self.assertEqual("alpha\n", Path(consumer.working_dir, "c.txt").read_text())
        marker = json.loads(Path(consumer.working_dir, ".dagon", MARKER_NAME).read_text())
        self.assertEqual("RemoteSlurm", marker["task_type"])

    def test_legacy_remote_slurm_is_unchanged(self):
        workflow, _producer, consumer = self.build(workflow_pre_stage=False)
        self.run_workflow(workflow)
        names = [detail if kind != "sbatch" else "sbatch" for kind, detail in self.events(consumer)]
        self.assertEqual(["context.sh", "context.sh", "launcher.sh", "sbatch"], names)
        submission = self.events(consumer)[-1][1]
        self.assertFalse(submission["marker_present"])
        self.assertEqual([], submission["inputs"])
        self.assertEqual("FINISHED", consumer.status.name)

    def test_remote_staging_failure_never_submits(self):
        workflow, _producer, consumer = self.build(producer_command="true")  # a.txt is never created
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertNotIn("sbatch", [kind for kind, _detail in self.events(consumer)])
        self.assertFalse(Path(consumer.working_dir, ".dagon", MARKER_NAME).exists())

    def test_ssh_disconnect_during_stage_in_never_submits(self):
        workflow, _producer, consumer = self.build()
        consumer.ssh_connection.fail_on = "stage_in.sh"
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        kinds = [kind for kind, _detail in self.events(consumer)]
        self.assertIn("disconnect", kinds)
        self.assertNotIn("sbatch", kinds)

    def test_failed_remote_script_creation_never_submits(self):
        workflow, _producer, consumer = self.build()
        consumer.ssh_connection.fail_create = "stage_in.sh"
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertNotIn("sbatch", [kind for kind, _detail in self.events(consumer)])

    def test_failed_marker_write_never_submits(self):
        workflow, _producer, consumer = self.build()
        consumer.ssh_connection.fail_create = MARKER_NAME
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertNotIn("sbatch", [kind for kind, _detail in self.events(consumer)])

    def test_failed_remote_sbatch_is_a_submission_failure(self):
        workflow, _producer, consumer = self.build()
        consumer.ssh_connection.reject_sbatch = True
        self.run_workflow(workflow, fails=True)
        self.assertEqual("submission", consumer.failure_phase)
        self.assertTrue(Path(consumer.working_dir, ".dagon", MARKER_NAME).exists())

    def test_errors_are_typed(self):
        workflow, _producer, consumer = self.build(producer_command="true")
        workflow.make_dependencies()
        workflow.tasks[0].execute()
        with self.assertRaises(StageInFailedError):
            consumer.execute()
        workflow, _producer, consumer = self.build()
        workflow.make_dependencies()
        workflow.tasks[0].execute()
        consumer.ssh_connection.reject_sbatch = True
        with self.assertRaises(SchedulerSubmissionError):
            consumer.execute()

    def test_dry_run_never_contacts_the_remote_host(self):
        workflow, producer, consumer = self.build()
        workflow.set_dry(True)
        with self.assertLogs(level="INFO"):
            self.run_workflow(workflow)
        for task in (producer, consumer):
            self.assertEqual([], task.ssh_connection.events)  # no file, command, or sbatch over SSH
        self.assertFalse(os.path.exists(self.remote))
        self.assertEqual(4, len(consumer.prepared_task.planned_order()))

    def test_changed_remote_input_invalidates_a_successful_checkpoint(self):
        checkpoint = os.path.join(self.tmp.name, "checkpoint.json")

        def build():
            workflow, producer, consumer = self.build()
            workflow.checkpoint_file = checkpoint
            return workflow, producer, consumer

        workflow, producer, consumer = build()
        self.run_workflow(workflow)
        self.assertEqual("alpha\n", Path(consumer.working_dir, "c.txt").read_text())

        workflow, producer, consumer = build()  # unchanged input: reused, re-verified over SSH
        workflow.run(resume_checkpoint_file=checkpoint)
        self.assertTrue(consumer.fair_checkpoint_reused)
        self.assertNotIn("sbatch", [kind for kind, _detail in consumer.ssh_connection.events])

        Path(producer.working_dir, "a.txt").write_text("omega\n")
        workflow, producer, consumer = build()
        with self.assertLogs(level="WARNING") as logs:
            workflow.run(resume_checkpoint_file=checkpoint)
        self.assertIn("content of at least one input changed", "\n".join(logs.output))
        self.assertFalse(consumer.fair_checkpoint_reused)
        self.assertIn("sbatch", [kind for kind, _detail in consumer.ssh_connection.events])
        self.assertEqual("omega\n", Path(consumer.working_dir, "c.txt").read_text())

    def test_remote_submission_uses_parsable_output(self):
        workflow, _producer, consumer = self.build()
        self.run_workflow(workflow)
        self.assertIn("--parsable", self.events(consumer)[-1][1]["options"])
        self.assertEqual("77", consumer.get_execution_metadata()["pre_stage"]["scheduler_job_id"])

    def test_remote_success_without_job_identifier_fails(self):
        workflow, _producer, consumer = self.build()
        consumer.ssh_connection.omit_job_id = True
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("submission", consumer.failure_phase)
        self.assertNotEqual(0, workflow.checkpoints[consumer.checkpoint_key()]["code"])

    def test_remote_lock_is_released_over_ssh(self):
        workflow, _producer, consumer = self.build()
        self.run_workflow(workflow)
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertFalse(Path(consumer.working_dir, ".dagon", "stage-in.lock").exists())
        self.assertTrue(Path(consumer.working_dir, ".dagon", "stage-in-destinations.txt").exists())

    def test_remote_example_with_loopback_ssh(self):
        import importlib
        import sys
        directory = str(Path(__file__).resolve().parents[1] / "examples" / "dataflow" / "slurm")
        if directory not in sys.path:
            sys.path.insert(0, directory)
        example = importlib.import_module("pre_stage_remote")
        argv = ["pre_stage_remote.py", "--host", "192.0.2.10", "--user", "hpc-user", "--key",
                os.path.join(self.tmp.name, "key"), "--port", "2222", "--remote-scratch", self.remote]
        with mock.patch("sys.argv", argv):
            self.assertEqual(0, example.main())
        sbatch = [event for connection in LoopbackSSH.instances for event in connection.events
                  if event[0] == "sbatch"]
        self.assertEqual(4, len(sbatch))
        self.assertTrue(all(connection.port == 2222 for connection in LoopbackSSH.instances))


if __name__ == "__main__":
    unittest.main()
