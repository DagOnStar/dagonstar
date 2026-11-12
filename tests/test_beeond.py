"""BeeOND volume support: configuration, command generation, launchers, lifecycle.

The scheduler is never contacted.  Generated bash fragments are executed
locally against a temporary directory that stands in for the BeeOND mount.
"""

import json
import os
import signal
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from dagon import Workflow
from dagon.batch import RemoteSlurm, Slurm
from dagon.beeond import (BeeONDConfig, BeeONDVolume, background_command, persist_function_script,
                          resolve, task_epilogue, task_prologue)
from dagon.platform_support import bash_executable
from dagon.task import DagonTask, TaskType

POSIX_TOOLS = os.name != "nt"


def make_config(scratch, beeond=None):
    config = {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
    }
    if beeond is not None:
        config["beeond"] = beeond
    return config


class FakeHost:
    """Records holder control commands and simulates the holder job files."""

    def __init__(self, ready=True, done="0\n", alive=True):
        self.commands = []
        self.files = {}
        self.ready = ready
        self.done = done
        self.alive = alive

    def run(self, argv):
        self.commands.append(list(argv))
        if argv[0] == "sbatch":
            return {"code": 0, "output": "4242;cluster\n", "message": ""}
        if argv[0] == "squeue":
            return {"code": 0, "output": "RUNNING\n" if self.alive else "", "message": ""}
        return {"code": 0, "output": "", "message": ""}

    def makedirs(self, directory):
        self.commands.append(["mkdir", "-p", directory])

    def write_file(self, filepath, content):
        self.files[filepath] = content

    def read_file(self, filepath):
        if filepath.endswith("/ready") and self.ready:
            return "4242\n/mnt/beeond_user-jobid_4242\n"
        if filepath.endswith("/done") and "stop" in "".join(self.files):
            return self.done
        return self.files.get(filepath)


class BeeONDConfigTests(unittest.TestCase):
    def test_defaults_match_the_site_launcher_convention(self):
        config = BeeONDConfig()
        self.assertEqual("task", config.scope)
        self.assertEqual("beeond-fs", config.comment)
        self.assertEqual("/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}", config.mount_template)
        self.assertTrue(config.persist)
        self.assertTrue(config.persist_on_failure)

    def test_ini_strings_are_parsed_and_validated(self):
        config = BeeONDConfig.from_mapping({
            "scope": "workflow", "persist": "False", "mount_timeout": "30", "signal_grace": "",
            "nodes": "4", "nodelist": "wn[01-04]", "partition": "xxcpu", "sbatch_options": "--exclusive --qos=high",
            "step_options": "--overlap", "poll_interval": "0.5", "verify": "checksum"})
        self.assertEqual("workflow", config.scope)
        self.assertFalse(config.persist)
        self.assertEqual(30, config.mount_timeout)
        self.assertIsNone(config.signal_grace)
        self.assertEqual(4, config.nodes)
        self.assertEqual(["--exclusive", "--qos=high"], config.sbatch_options)
        self.assertEqual(["--overlap"], config.step_options)
        self.assertEqual(0.5, config.poll_interval)

    def test_invalid_options_are_rejected(self):
        with self.assertRaises(ValueError):
            BeeONDConfig.from_mapping({"persit": "true"})
        with self.assertRaises(ValueError):
            BeeONDConfig(scope="cluster")
        with self.assertRaises(ValueError):
            BeeONDConfig(mount_template="/mnt/$(id)")
        with self.assertRaises(ValueError):
            BeeONDConfig(mount_template='/mnt/"x"')
        with self.assertRaises(ValueError):
            BeeONDConfig(volume="a b")
        with self.assertRaises(ValueError):
            BeeONDConfig.from_mapping({"persist": "maybe"})


class SlurmCommandTests(unittest.TestCase):
    def test_task_scope_adds_beeond_comment_once_and_signal(self):
        task = Slurm("Sim", "run", comment=["beeond-fs", "other"], nodes=4, ntasks_per_node=1,
                     nodelist="wn[01-04]", partition="xxcpu", working_dir="/scratch/w",
                     sbatch_options=["--exclusive"],
                     beeond=BeeONDConfig(signal_grace=120))
        command = task.generate_command("launcher.sh")
        self.assertEqual(1, command.count("--comment=beeond-fs"))
        self.assertIn("--comment=other", command)
        self.assertIn("'--nodelist=wn[01-04]'", command)
        self.assertIn("--signal=B:USR1@120", command)
        self.assertIn("--exclusive", command)
        self.assertIn("-W /scratch/w/.dagon/launcher.sh", command)

    def test_task_without_beeond_keeps_previous_command(self):
        task = Slurm("Sim", "run", partition="debug", working_dir="/scratch/w")
        self.assertEqual("sbatch --partition=debug -J Sim -D /scratch/w -W /scratch/w/.dagon/launcher.sh",
                         task.generate_command("launcher.sh"))
        self.assertEqual("", task.launcher_prologue())
        self.assertEqual("", task.launcher_epilogue())
        self.assertNotIn("&", task.include_command("run"))

    def test_task_scope_launcher_fragments(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = Workflow("wf", config=make_config(scratch))
            task = Slurm("Sim", "run", working_dir=scratch + "/sim", beeond="task")
            workflow.add_task(task)
            prologue = task.launcher_prologue()
            self.assertIn('DAGON_BEEOND="/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}"', prologue)
            self.assertIn("dagon_beeond_persist()", prologue)
            self.assertIn("trap dagon_beeond_on_signal USR1 TERM", prologue)
            self.assertIn("dagon_beeond_persist || code=1", task.launcher_epilogue())
            self.assertIn("wait \"$DAGON_COMMAND_PID\"", task.include_command("run"))
            self.assertEqual(scratch + "/sim/beeond", task.beeond_persist_dir())

    def test_remote_slurm_accepts_beeond_and_ssh_ports(self):
        for port in (22, 2222):
            with mock.patch("dagon.remote.SSHManager") as manager:
                task = Slurm("R", "run", ip="192.0.2.5", ssh_username="user", keypath="/tmp/key",
                             ssh_port=port, comment="x", nodes=4, beeond="task", working_dir="/w")
            self.assertIsInstance(task, RemoteSlurm)
            manager.assert_called_once_with("user", "192.0.2.5", os.path.abspath("/tmp/key"), port=port)
            command = task.generate_command("launcher.sh")
            self.assertIn("--comment=x --comment=beeond-fs", command)
            self.assertIn("--nodes=4", command)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workflow = Workflow("wf", config=make_config(self.tmp.name, {"partition": "xxcpu", "nodes": "4"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_specifications(self):
        self.assertIsNone(resolve(None, self.workflow))
        self.assertIsNone(resolve(False, self.workflow))
        task_config = resolve(True, self.workflow)
        self.assertIsInstance(task_config, BeeONDConfig)
        self.assertEqual(("task", "xxcpu"), (task_config.scope, task_config.partition))
        volume = resolve("workflow", self.workflow)
        self.assertIsInstance(volume, BeeONDVolume)
        self.assertIs(volume, resolve("workflow:default", self.workflow))
        self.assertEqual(4, volume.config.nodes)
        other = resolve({"scope": "workflow", "volume": "big", "nodes": 8}, self.workflow)
        self.assertEqual(8, other.config.nodes)
        self.assertIs(other, resolve({"scope": "workflow", "volume": "big"}, self.workflow))
        with self.assertRaises(ValueError):
            resolve({"scope": "workflow", "volume": "big", "nodes": 2}, self.workflow)
        with self.assertRaises(ValueError):
            resolve("cluster", self.workflow)
        with self.assertRaises(ValueError):
            self.workflow.create_beeond_volume("big")

    def test_persist_and_state_directories(self):
        volume = self.workflow.create_beeond_volume("v", persist_dir="keep")
        base = self.workflow.get_scratch_dir_base()
        self.assertEqual(base + "/keep", volume.persist_dir())
        self.assertEqual(base + "/.dagon-beeond/wf-v", volume.state_dir())
        self.assertEqual(base + "/wf-beeond-default", self.workflow.get_beeond_volume().persist_dir())


class WorkflowVolumeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workflow = Workflow("wf", config=make_config(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_submits_holder_and_steps_use_its_allocation(self):
        volume = self.workflow.create_beeond_volume(
            nodes=4, nodelist="wn[01-04]", partition="xxcpu", time="02:00:00", ntasks_per_node=1,
            signal_grace=300, poll_interval=0)
        host = FakeHost()
        volume.ensure_started(host)
        volume.ensure_started(host)  # idempotent
        submissions = [command for command in host.commands if command[0] == "sbatch"]
        self.assertEqual(1, len(submissions))
        submit = submissions[0]
        for option in ("--parsable", "--comment=beeond-fs", "--nodes=4", "--nodelist=wn[01-04]",
                       "--partition=xxcpu", "--time=02:00:00", "--ntasks-per-node=1", "--signal=B:USR1@300"):
            self.assertIn(option, submit)
        self.assertEqual(volume.state_dir() + "/holder.sh", submit[-1])
        self.assertIn("dagon_beeond_persist", host.files[volume.state_dir() + "/holder.sh"])
        self.assertEqual("4242", volume.job_id)
        self.assertEqual("/mnt/beeond_user-jobid_4242", volume.mount)
        self.assertEqual(["srun", "--jobid=4242", "--overlap", "--nodes=1", "--ntasks=1", "-J", "T",
                          "-D", "/w", "bash", "/w/.dagon/launcher.sh"],
                         volume.step_argv("T", "/w", "/w/.dagon/launcher.sh"))
        prologue = volume.task_prologue()
        self.assertIn("DAGON_BEEOND=/mnt/beeond_user-jobid_4242", prologue)
        self.assertEqual({"default": 0}, self.workflow.stop_beeond_volumes())
        self.assertIn(volume.state_dir() + "/stop", host.files)
        self.assertEqual("stopped", volume.state)
        self.assertEqual({"default": 0}, self.workflow.stop_beeond_volumes())

    def test_failed_persistence_is_reported(self):
        volume = self.workflow.create_beeond_volume(poll_interval=0)
        volume.ensure_started(FakeHost(done="1\n"))
        with self.assertLogs(level="ERROR"), self.assertRaises(RuntimeError):
            self.workflow.stop_beeond_volumes()
        self.assertEqual(1, volume.persist_code)

    def test_holder_that_never_becomes_ready_is_cancelled(self):
        volume = self.workflow.create_beeond_volume(poll_interval=0, start_timeout=0)
        host = FakeHost(ready=False, alive=True)
        with self.assertRaises(RuntimeError):
            volume.ensure_started(host)
        self.assertIn(["scancel", "4242"], host.commands)
        self.assertEqual("failed", volume.state)

    def test_unstarted_volume_stops_without_scheduler_calls(self):
        self.workflow.create_beeond_volume()
        self.assertEqual({"default": None}, self.workflow.stop_beeond_volumes())

    def test_slurm_task_runs_as_step_of_the_workflow_volume(self):
        volume = self.workflow.create_beeond_volume(poll_interval=0)
        task = Slurm("T", "run", working_dir=self.tmp.name + "/t", beeond="workflow")
        self.workflow.add_task(task)
        os.makedirs(self.tmp.name + "/t/.dagon")
        host = FakeHost()
        with mock.patch("dagon.beeond.LocalHost", return_value=host), \
                mock.patch("dagon.batch.Batch.execute_command", return_value={"code": 0, "output": ""}) as run:
            task.on_execute("#!/bin/bash\n", "launcher.sh")
        self.assertIs(volume, task.beeond_volume())
        self.assertTrue(run.call_args[0][0].startswith("srun --jobid=4242 --overlap"))
        self.assertEqual("workflow", task.get_execution_metadata()["beeond"]["scope"])

    def test_remote_slurm_controls_the_holder_through_ssh(self):
        calls = []

        class Connection:
            def execute_command(self, command):
                calls.append(command)
                if command.startswith("sbatch"):
                    return {"code": 0, "output": "77\n"}
                if "ready" in command:
                    return {"code": 0, "output": "77\n\n/mnt/beeond_u-jobid_77\n"}
                return {"code": 0, "output": ""}

            def create_file(self, filepath, content):
                calls.append("create " + filepath)

        self.workflow.create_beeond_volume(poll_interval=0)
        with mock.patch("dagon.remote.SSHManager", return_value=Connection()):
            task = Slurm("T", "run", ip="192.0.2.5", ssh_username="u", keypath="/tmp/k",
                         working_dir="/remote/t", beeond="workflow")
        self.workflow.add_task(task)
        task.on_execute("#!/bin/bash\n", "launcher.sh")
        self.assertTrue(any(call.startswith("sbatch --parsable --comment=beeond-fs") for call in calls))
        self.assertEqual("srun --jobid=77 --overlap --nodes=1 --ntasks=1 -J T -D /remote/t bash "
                         "/remote/t/.dagon/launcher.sh", calls[-1])

    def test_json_round_trip_keeps_the_specification(self):
        task = DagonTask(TaskType.SLURM, "T", "run", beeond="workflow:big")
        self.workflow.add_task(task)
        data = self.workflow.as_json()
        self.assertEqual("workflow:big", data["tasks"]["T"]["beeond"])
        clone = Workflow("x", config=make_config(self.tmp.name), jsonload=json.loads(json.dumps(data)))
        self.assertEqual("workflow:big", clone.tasks[0].beeond)


@unittest.skipUnless(POSIX_TOOLS, "BeeOND launchers target Linux compute nodes")
class LauncherExecutionTests(unittest.TestCase):
    """Run generated fragments with bash against a stand-in mount directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mount = os.path.join(self.tmp.name, "mnt", "beeond_u-jobid_1")
        self.persist = os.path.join(self.tmp.name, "work dir", "beeond")
        self.report = os.path.join(self.tmp.name, "work dir", ".dagon")
        os.makedirs(self.mount)
        os.makedirs(self.report)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, **options):
        template = os.path.join(self.tmp.name, "mnt", "beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}")
        return BeeONDConfig(mount_template=template, mount_timeout=2, **options)

    def launcher(self, config, command):
        return ("code=0\n" + task_prologue(config, self.persist, self.report)
                + background_command(command) + "if [ $? -ne 0 ]; then code=1; fi\n"
                + task_epilogue(config) + "exit $code\n")

    def run_bash(self, script, **kwargs):
        env = dict(os.environ, SLURM_JOB_USER="u", SLURM_JOB_ID="1")
        return subprocess.run([bash_executable(), "-c", script], env=env, text=True,
                              capture_output=True, **kwargs)

    def test_task_volume_is_persisted_and_verified(self):
        for tool, verify in (("auto", "list"), ("cp", "checksum")):
            result = self.run_bash(self.launcher(
                self.config(persist_tool=tool, verify=verify),
                'mkdir -p "$DAGON_BEEOND/sub" && echo data > "$DAGON_BEEOND/sub/x.txt"'))
            self.assertEqual(0, result.returncode, result.stderr)
            with open(os.path.join(self.persist, "sub", "x.txt")) as stream:
                self.assertEqual("data\n", stream.read())
            with open(os.path.join(self.report, "beeond_persist.status")) as stream:
                self.assertIn("persist_code=0", stream.read())

    def test_failed_command_is_still_persisted_but_fails(self):
        result = self.run_bash(self.launcher(self.config(), 'echo partial > "$DAGON_BEEOND/p.txt"; false'))
        self.assertEqual(1, result.returncode)
        self.assertTrue(os.path.isfile(os.path.join(self.persist, "p.txt")))

    def test_persist_on_failure_can_be_disabled(self):
        result = self.run_bash(self.launcher(self.config(persist_on_failure=False),
                                             'echo partial > "$DAGON_BEEOND/p.txt"; false'))
        self.assertEqual(1, result.returncode)
        self.assertFalse(os.path.exists(os.path.join(self.persist, "p.txt")))

    def test_missing_mount_fails_fast(self):
        config = BeeONDConfig(mount_template=os.path.join(self.tmp.name, "absent"), mount_timeout=0)
        result = self.run_bash(self.launcher(config, "true"))
        self.assertEqual(1, result.returncode)
        self.assertIn("is not available", result.stderr)

    def test_verification_detects_missing_files(self):
        config = self.config(persist_tool="cp")
        script = ("DAGON_BEEOND=" + self.mount + "\n" + persist_function_script(config, self.persist, self.report)
                  + "echo a > \"$DAGON_BEEOND/a\"\n"
                  # Simulate a copy that silently drops a file.
                  + "cp() { mkdir -p \"$3\"; return 0; }\n"
                  + "dagon_beeond_persist\n")
        result = self.run_bash(script)
        self.assertEqual(1, result.returncode)
        self.assertIn("verification failed", result.stderr)

    def test_signal_persists_running_task(self):
        script = self.launcher(self.config(), 'echo early > "$DAGON_BEEOND/e.txt"; sleep 30')
        env = dict(os.environ, SLURM_JOB_USER="u", SLURM_JOB_ID="1")
        process = subprocess.Popen([bash_executable(), "-c", script], env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 10
        while not os.path.exists(os.path.join(self.mount, "e.txt")) and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(0.2)
        process.send_signal(signal.SIGUSR1)
        process.communicate(timeout=20)
        self.assertEqual(1, process.returncode)
        self.assertTrue(os.path.isfile(os.path.join(self.persist, "e.txt")))

    def test_holder_script_restores_waits_and_persists(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = Workflow("wf", config=make_config(scratch))
            template = os.path.join(self.tmp.name, "mnt", "beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}")
            volume = workflow.create_beeond_volume(mount_template=template, poll_interval=1, restore=True)
            os.makedirs(volume.persist_dir())
            with open(os.path.join(volume.persist_dir(), "old.txt"), "w") as stream:
                stream.write("previous run\n")
            os.makedirs(volume.state_dir())
            holder = os.path.join(volume.state_dir(), "holder.sh")
            with open(holder, "w", newline="\n") as stream:
                stream.write(volume.holder_script())
            env = dict(os.environ, SLURM_JOB_USER="u", SLURM_JOB_ID="1")
            process = subprocess.Popen([bash_executable(), holder], env=env, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ready = os.path.join(volume.state_dir(), "ready")
            deadline = time.time() + 10
            while not os.path.exists(ready) and time.time() < deadline:
                time.sleep(0.1)
            with open(ready) as stream:
                self.assertEqual(["1", self.mount], stream.read().split())
            self.assertTrue(os.path.isfile(os.path.join(self.mount, "old.txt")))
            with open(os.path.join(self.mount, "new.txt"), "w") as stream:
                stream.write("this run\n")
            open(os.path.join(volume.state_dir(), "stop"), "w").close()
            process.communicate(timeout=20)
            self.assertEqual(0, process.returncode)
            with open(os.path.join(volume.state_dir(), "done")) as stream:
                self.assertEqual("0", stream.read().strip())
            self.assertTrue(os.path.isfile(os.path.join(volume.persist_dir(), "new.txt")))


class PortableEmulationTests(unittest.TestCase):
    def test_task_and_workflow_volumes_are_emulated_with_persistent_directories(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = Workflow("wf", config=make_config(scratch), portable_emulation=True)
            producer = DagonTask(TaskType.SLURM, "Producer", 'echo hi > "$DAGON_BEEOND/a.txt"', beeond="task")
            shared = DagonTask(TaskType.SLURM, "Shared",
                               'cat workflow:///Producer/beeond/a.txt > "$DAGON_BEEOND/s.txt"',
                               beeond="workflow")
            reader = DagonTask(TaskType.SLURM, "Reader", 'cat "$DAGON_BEEOND/s.txt" > out.txt',
                               beeond="workflow")
            reader_dependency = DagonTask(TaskType.BATCH, "Done", "cat workflow:///Reader/out.txt")
            for task in (producer, shared, reader, reader_dependency):
                workflow.add_task(task)
            # The shared volume is not a workflow:// reference: order it explicitly.
            workflow.make_dependencies()
            reader.add_dependency_to(shared)
            workflow.run()
            self.assertEqual({"FINISHED"}, {task.status.name for task in workflow.tasks})
            with open(os.path.join(reader.working_dir, "out.txt")) as stream:
                self.assertEqual("hi\n", stream.read())
            self.assertTrue(os.path.isfile(os.path.join(producer.working_dir, "beeond", "a.txt")))
            checkpoint = workflow.checkpoints["wf.Shared"]["beeond"]
            self.assertEqual({"scope": "workflow", "volume": "default",
                              "persist_dir": workflow.get_beeond_volume().persist_dir()}, checkpoint)


if __name__ == "__main__":
    unittest.main()
