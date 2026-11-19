"""Contract tests for the common ad-hoc file-system interface.

External runtimes are replaced by small local stand-ins: a DAGonFS
native-protocol server, CAPIO and Hercules launch scripts, a ``docker``
recorder, and a loopback DynoStore gateway.  No network or site software is
required.
"""

import http.server
import json
import os
import pickle
import shutil
import stat
import sys
import tempfile
import textwrap
import threading
import unittest
import zlib
from unittest.mock import Mock, patch

from dagon import Workflow
from dagon.adhoc import (AdHocFileSystem, AdHocFileSystemError, BeeOND, Capio, DAGonFS, DYNOSTORE_KEY, DynoStore,
                         Hercules, PROVIDERS, create, decode_dynostore_object, encode_dynostore_object,
                         read_hercules_config)
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config


FAKE_DAGONFS = r'''
import os, socket, struct, sys
REQUEST = struct.Struct("=IHHIIIiI4xqq")
REPLY = struct.Struct("=IHHiIqQQIIIIqqq")
path = sys.argv[-1]
if os.environ.get("FAKE_DAGONFS_FAIL"):
    sys.exit(3)
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(path)
listener.listen(4)
with open(path + ".argv", "w") as stream:
    stream.write("\n".join(sys.argv[1:]))
while True:
    connection, _ = listener.accept()
    header = b""
    while len(header) < REQUEST.size:
        header += connection.recv(REQUEST.size - len(header))
    magic, version, opcode, length = REQUEST.unpack(header)[:4]
    name = connection.recv(length) if length else b""
    error = 0 if (opcode == 6 and name == b"/") or opcode == 12 else 2
    connection.sendall(REPLY.pack(magic, version, 0, error, 0, 0, 1, 0, 0o40755, 2, 0, 0, 0, 0, 0))
    connection.close()
    if opcode == 12:
        listener.close()
        os.unlink(path)
        sys.exit(0)
'''


# DAGonFS, CAPIO, and Hercules run on POSIX hosts only, and the provider and
# Docker stand-ins below are shebang scripts, which Windows cannot execute.
POSIX_ONLY = unittest.skipIf(os.name == "nt", "POSIX-only providers and executable stand-ins")


def write_script(directory, name, body):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("#!%s\n%s" % (sys.executable, textwrap.dedent(body)))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class RecordingFileSystem(AdHocFileSystem):
    provider = "recording"

    def __init__(self, workflow, name="recording"):
        super().__init__(workflow, name)
        self.events = []

    def start(self):
        self.events.append("start")
        super().start()

    def stop(self):
        self.events.append("stop")
        return super().stop()

    def provider_environment(self, task):
        return {"ADHOC_TEST": task.name}


class AdHocTestCase(unittest.TestCase):
    def setUp(self):
        # Unix socket paths are limited to ~104 bytes: keep the scratch short.
        self.scratch = tempfile.mkdtemp(prefix="adh")
        self.addCleanup(shutil.rmtree, self.scratch, True)

    def workflow(self, portable=True, name="adhoc-test"):
        config = minimal_config()
        config["batch"]["scratch_dir_base"] = self.scratch
        return Workflow(name, config=config, portable_emulation=portable)


class CommonContractTests(AdHocTestCase):
    def test_factory_knows_every_provider(self):
        # Further adapters may be registered (dagon.adhoc.register_provider); these are built in.
        self.assertTrue({"beeond", "capio", "dagonfs", "dynostore", "hercules"} <= set(PROVIDERS))
        with self.assertRaises(ValueError):
            create(self.workflow(), "lustre")
        with self.assertRaises(ValueError):
            DAGonFS(self.workflow(), name="bad name")

    def test_duplicate_names_are_rejected(self):
        workflow = self.workflow()
        workflow.create_adhoc_filesystem("capio", name="shared")
        with self.assertRaises(ValueError):
            workflow.create_adhoc_filesystem("dagonfs", name="shared")

    @POSIX_ONLY
    def test_common_and_per_name_variables(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "producer", "true")
        workflow.add_task(task)
        capio = workflow.create_adhoc_filesystem("CAPIO", name="fast", directory="/scratch/capio",
                                                 library="/opt/libcapio_posix.so")
        dagonfs = workflow.create_adhoc_filesystem("dagonfs", name="ram", mountpoint="/scratch/dfs")
        self.assertIsInstance(capio, Capio)
        self.assertIs(capio.bind(task), task)
        dagonfs.bind(task)
        environment = capio.task_environment(task)
        self.assertEqual(environment["DAGON_ADHOC_ACCESS"], "preload")
        self.assertEqual(environment["DAGON_ADHOC_FAST_PATH"], "/scratch/capio")
        self.assertEqual(environment["CAPIO_APP_NAME"], "producer")
        # Distinct CAPIO resources get distinct shared-memory channel names.
        self.assertEqual(environment["CAPIO_WORKFLOW_NAME"], "adhoc-test-fast")
        prologue = task.launcher_prologue()
        self.assertIn("export DAGON_ADHOC_FAST_PATH=/scratch/capio", prologue)
        self.assertIn("export DAGON_ADHOC_RAM_PATH=/scratch/dfs", prologue)
        # The last bound resource provides the generic variables.
        self.assertLess(prologue.index("DAGON_ADHOC_PATH=/scratch/capio"),
                        prologue.index("DAGON_ADHOC_PATH=/scratch/dfs"))
        providers = [item["provider"] for item in task.get_execution_metadata()["adhoc_filesystems"]]
        self.assertEqual(providers, ["capio", "dagonfs"])

    def test_credential_variables_are_never_exported(self):
        class Leaky(AdHocFileSystem):
            def provider_environment(self, task):
                return {"SERVICE_TOKEN": "x"}
        with self.assertRaises(ValueError):
            Leaky(self.workflow()).task_environment(None)

    def test_workflow_owns_lifecycle(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "task", 'test "$ADHOC_TEST" = task')
        workflow.add_task(task)
        filesystem = RecordingFileSystem(workflow)
        workflow.adhoc_filesystems[filesystem.name] = filesystem
        filesystem.bind(task)
        workflow.run()
        self.assertEqual(filesystem.events, ["start", "stop"])

    def test_resources_stop_after_a_failed_task(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "task", "false")
        workflow.add_task(task)
        filesystem = RecordingFileSystem(workflow)
        workflow.adhoc_filesystems[filesystem.name] = filesystem
        filesystem.bind(task)
        try:
            workflow.run()
        except Exception:
            pass
        self.assertEqual(filesystem.events, ["start", "stop"])
        self.assertFalse(filesystem.started)

    def test_portable_emulation_redirects_paths_and_drops_preloads(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "writer",
                         'test -z "$LD_PRELOAD" && echo ok > "$HERCULES_MOUNT_POINT/out.txt" '
                         '&& test "$DAGON_ADHOC_EMULATED" = 1')
        workflow.add_task(task)
        hercules = workflow.create_adhoc_filesystem("hercules", config="site.conf")
        hercules.bind(task)
        workflow.run()
        self.assertEqual(task.result["code"], 0)
        emulated = os.path.join(self.scratch, ".adhoc-emulated", "default", "out.txt")
        self.assertTrue(os.path.exists(emulated))

    def test_portable_emulation_does_not_start_external_runtimes(self):
        with patch("dagon.adhoc.subprocess.Popen") as popen, patch("dagon.adhoc.subprocess.run") as run:
            workflow = self.workflow()
            for provider, options in (("capio", {}), ("dagonfs", {}), ("hercules", {"config": "h.conf"}),
                                      ("dynostore", {"compose_file": "compose.yml"})):
                filesystem = create(workflow, provider, **options)
                filesystem.start()
                self.assertFalse(filesystem.started)
        popen.assert_not_called()
        run.assert_not_called()


@POSIX_ONLY
class DAGonFSTests(AdHocTestCase):
    def test_commands_follow_the_dagonfs_cli(self):
        workflow = self.workflow()
        fuse = DAGonFS(workflow, mountpoint="/scratch/dagonfs", ranks=4, executable="/opt/dagonfs",
                       mpirun_args=["--hostfile", "hosts"])
        self.assertEqual(fuse.start_command, ["mpirun", "-np", "4", "--hostfile", "hosts", "/opt/dagonfs",
                                              "--model", "client-server", "-f", "/scratch/dagonfs"])
        native = DAGonFS(workflow, mountpoint="/tmp/v.sock", frontend="native", config="DAGonFS.ini")
        self.assertEqual(native.start_command[-8:], ["--model", "client-server", "--frontend", "native",
                                                     "--config", "DAGonFS.ini", "-f", "/tmp/v.sock"])
        peer = DAGonFS(workflow, mountpoint="/scratch/peers", model="peer-to-peer")
        self.assertEqual(peer.task_environment(None)["DAGONFS_MOUNTPOINT"], "/scratch/peers/0")

    def test_frontend_validation(self):
        workflow = self.workflow()
        with self.assertRaises(ValueError):
            DAGonFS(workflow, frontend="nfs")
        with self.assertRaises(ValueError):
            DAGonFS(workflow, frontend="native", model="peer-to-peer")
        with self.assertRaises(ValueError):
            DAGonFS(workflow, frontend="preload")
        with self.assertRaises(ValueError):
            DAGonFS(workflow, frontend="native", mountpoint="/" + "x" * 120)

    def test_frontend_environments(self):
        workflow = self.workflow()
        native = DAGonFS(workflow, mountpoint="/tmp/v.sock", frontend="native", python_path="/opt/dfs/python")
        environment = native.task_environment(None)
        self.assertEqual(environment["DAGON_ADHOC_ACCESS"], "client")
        self.assertEqual(environment["DAGONFS_SOCKET"], "/tmp/v.sock")
        self.assertEqual(environment["DAGONFS_PYTHON"], "/opt/dfs/python")
        for platform, variable in (("linux", "LD_PRELOAD"), ("darwin", "DYLD_INSERT_LIBRARIES")):
            with patch("dagon.adhoc.sys.platform", platform):
                preload = DAGonFS(workflow, mountpoint="/tmp/p.sock", frontend="preload",
                                  preload_library="/opt/libdagonfs_preload.so", preload_root="/dfs/")
                environment = preload.task_environment(None)
                # Preload libraries are path lists, so several resources compose.
                self.assertEqual(preload.path_environment(None), {variable: "/opt/libdagonfs_preload.so"})
            self.assertNotIn(variable, environment)
            self.assertEqual(environment["DAGON_ADHOC_PATH"], "/dfs")
            self.assertEqual(environment["DAGON_ADHOC_ACCESS"], "preload")

    def native_volume(self, **options):
        fake = write_script(self.scratch, "fake-mpirun", FAKE_DAGONFS)
        workflow = self.workflow(portable=False)
        return workflow, DAGonFS(workflow, frontend="native", mpirun=fake, ranks=3,
                                 startup_timeout=10, **options)

    def test_native_volume_waits_for_readiness_and_shuts_down(self):
        workflow, volume = self.native_volume()
        volume.start()
        self.assertTrue(volume.started)
        self.assertTrue(volume.is_ready())
        with open(volume.mountpoint + ".argv", encoding="utf-8") as stream:
            self.assertIn("native", stream.read().split("\n"))
        process = volume._process
        self.assertEqual(volume.stop(), 0)
        self.assertEqual(process.returncode, 0, "the volume must exit through SHUTDOWN, not a signal")
        self.assertFalse(os.path.exists(volume.mountpoint))
        self.assertFalse(volume.started)

    def test_native_volume_startup_failure_is_reported_and_cleaned_up(self):
        workflow, volume = self.native_volume()
        with patch.dict(os.environ, {"FAKE_DAGONFS_FAIL": "1"}):
            with self.assertRaises(AdHocFileSystemError) as caught:
                volume.start()
        self.assertIn("status 3", str(caught.exception))
        self.assertFalse(volume.started)
        self.assertIsNone(volume._process)

    def test_workflow_runs_tasks_against_a_live_native_volume(self):
        workflow, volume = self.native_volume()
        workflow.adhoc_filesystems[volume.name] = volume
        task = DagonTask(TaskType.BATCH, "client", 'test -S "$DAGONFS_SOCKET" && test "$DAGON_ADHOC_ACCESS" = client')
        workflow.add_task(task)
        volume.bind(task)
        workflow.run()
        self.assertEqual(task.result["code"], 0)
        self.assertFalse(volume.started)

    def test_fuse_volume_unmounts_before_terminating(self):
        workflow = self.workflow(portable=False)
        volume = DAGonFS(workflow, mountpoint=os.path.join(self.scratch, "mnt"))
        volume._started = True
        volume._process = Mock()
        volume._process.poll.return_value = None
        process = volume._process
        with patch("dagon.adhoc.os.path.ismount", side_effect=[True, False]), \
                patch("dagon.adhoc.subprocess.run") as run:
            volume.stop()
        unmount = run.call_args_list[0].args[0]
        self.assertEqual(unmount[-1], volume.task_path)
        self.assertTrue(unmount[0] == "umount" or "fusermount" in unmount[0])
        process.wait.assert_called()
        self.assertIsNone(volume._process)


@POSIX_ONLY
class CapioTests(AdHocTestCase):
    def config(self, name="capio-wf"):
        path = os.path.join(self.scratch, "capio.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"name": name, "IO_Graph": [{"name": "writer", "output_stream": ["a.dat"]},
                                                  {"name": "reader", "input_stream": ["a.dat"]}]}, stream)
        return path

    def test_command_and_names_follow_capio_cl(self):
        workflow = self.workflow()
        config = self.config()
        capio = Capio(workflow, config=config, backend="mtcl", backend_options="TCP:7600@1000000",
                      mem_only=True, app_names={"produce": "writer"})
        self.assertEqual(capio.start_command, ["capio_server", "-c", config, "--backend", "mtcl",
                                               "--backend-options", "TCP:7600@1000000", "--mem-only"])
        self.assertEqual(Capio(workflow).start_command, ["capio_server", "--no-config"])
        self.assertEqual(Capio(workflow, server_launcher=["srun", "--ntasks-per-node=1"]).start_command,
                         ["srun", "--ntasks-per-node=1", "capio_server", "--no-config"])
        task = DagonTask(TaskType.BATCH, "produce", "true")
        workflow.add_task(task)
        capio.bind(task)
        environment = capio.task_environment(task)
        self.assertEqual(environment["CAPIO_WORKFLOW_NAME"], "capio-wf")
        self.assertEqual(capio.environment["CAPIO_WORKFLOW_NAME"], "capio-wf")
        self.assertEqual(environment["CAPIO_APP_NAME"], "writer")
        self.assertEqual(capio.environment["CAPIO_DIR"], capio.directory)
        with self.assertRaises(ValueError):
            Capio(workflow, config=config, workflow_name="other")
        installed = Capio(workflow, library_dir="/opt/capio/lib64")
        self.assertNotIn("LD_PRELOAD", installed.task_environment(task))
        self.assertEqual(installed.path_environment(task), {"LD_PRELOAD": "/opt/capio/lib64/libcapio_posix.so",
                                                            "LD_LIBRARY_PATH": "/opt/capio/lib64"})

    def test_unknown_app_is_reported(self):
        workflow = self.workflow()
        capio = Capio(workflow, config=self.config())
        task = DagonTask(TaskType.BATCH, "stranger", "true")
        workflow.add_task(task)
        with self.assertLogs("dagon.adhoc", "WARNING"):
            capio.bind(task)

    def test_server_lifecycle_uses_sigterm(self):
        server = write_script(self.scratch, "capio_server", """
            import os, signal, sys, time
            assert os.path.isdir(os.environ["CAPIO_DIR"])
            assert os.environ["CAPIO_WORKFLOW_NAME"] == "adhoc-test"
            signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
            print("main | Server instance successfully started!", flush=True)
            while True:
                time.sleep(0.05)
        """)
        capio = Capio(self.workflow(portable=False), server=server, startup_delay=0)
        capio.start()
        self.assertTrue(capio.is_ready())
        process = capio._process
        capio.stop()
        self.assertEqual(process.returncode, 0)

    def test_server_that_never_reports_ready_is_stopped(self):
        server = write_script(self.scratch, "capio_server", """
            import time
            while True:
                time.sleep(0.05)
        """)
        capio = Capio(self.workflow(portable=False), server=server, startup_delay=0, startup_timeout=1)
        with self.assertRaises(AdHocFileSystemError) as caught:
            capio.start()
        self.assertIn("not ready", str(caught.exception))
        self.assertFalse(capio.started)
        self.assertIsNone(capio._process)

    def test_server_exiting_at_startup_fails(self):
        server = write_script(self.scratch, "capio_server", "import sys; sys.exit(4)\n")
        capio = Capio(self.workflow(portable=False), server=server, startup_delay=2.0)
        self.addCleanup(capio.stop)
        with self.assertRaises(AdHocFileSystemError):
            capio.start()
        self.assertFalse(capio.started)


@POSIX_ONLY
class HerculesTests(AdHocTestCase):
    def config(self):
        path = os.path.join(self.scratch, "hercules.conf")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("# Hercules\nURI = imss://\nMOUNT_POINT = /mnt/herc/   # prefix\nBLOCK_SIZE = 512\n")
        return path

    def test_configuration_and_commands(self):
        config = self.config()
        self.assertEqual(read_hercules_config(config)["MOUNT_POINT"], "/mnt/herc/")
        hercules = Hercules(self.workflow(), config=config, meta_hostfile="meta", data_hostfile="data",
                            library_dir="/opt/hercules/lib")
        self.assertEqual(hercules.task_path, "/mnt/herc")
        self.assertEqual(hercules.start_command, ["hercules", "start", "-m", "meta", "-d", "data", "-f", config])
        self.assertEqual(hercules.stop_command, ["hercules", "stop", "-m", "meta", "-d", "data", "-f", config])
        environment = hercules.task_environment(None)
        self.assertEqual(hercules.path_environment(None)["LD_PRELOAD"], "/opt/hercules/lib/libhercules_posix.so")
        self.assertEqual(environment["HERCULES_CONF"], config)
        with self.assertRaises(ValueError):
            Hercules(self.workflow(), config=config, meta_hostfile="meta")
        with_clients = Hercules(self.workflow(), config=config, meta_hostfile="m", data_hostfile="d",
                                client_hostfile="c")
        self.assertEqual(with_clients.start_command[2:8], ["-m", "m", "-d", "d", "-c", "c"])

    def test_slurm_jobs_use_the_per_job_configuration(self):
        config = self.config()
        hercules = Hercules(self.workflow(), config=config, job_id="1234")
        self.assertEqual(hercules.task_environment(None)["HERCULES_CONF"], config + "_1234")
        with patch.dict(os.environ, {"SLURM_JOB_ID": "77"}):
            self.assertEqual(Hercules(self.workflow(), config=config).client_config(), config)
            open(config + "_77", "w").close()
            self.assertEqual(Hercules(self.workflow(), config=config).client_config(), config + "_77")

    @patch("dagon.adhoc.subprocess.run")
    def test_stop_inside_an_allocation_names_the_per_job_configuration(self, run):
        # ``hercules stop`` does not derive the per-job file from Slurm itself.
        run.return_value = Mock(returncode=0)
        config = self.config()
        with patch.dict(os.environ, {"SLURM_JOB_ID": "91"}):
            hercules = Hercules(self.workflow(portable=False), config=config)
            hercules.start()
            open(config + "_91", "w").close()   # written by ``hercules start``
            hercules.stop()
        self.assertEqual(run.call_args_list[0].args[0][-1], config)
        self.assertEqual(run.call_args_list[-1].args[0], ["hercules", "stop", "-f", config + "_91"])

    @patch("dagon.adhoc.subprocess.run")
    def test_stop_never_hands_user_host_files_to_a_per_job_stop(self, run):
        # ``hercules stop -d FILE`` deletes the stopped hosts from FILE; the
        # per-job configuration already names the job's own copies.
        run.return_value = Mock(returncode=0)
        config = self.config()
        with patch.dict(os.environ, {"SLURM_JOB_ID": "92"}):
            hercules = Hercules(self.workflow(portable=False), config=config,
                                meta_hostfile="meta", data_hostfile="data")
            hercules.start()
            open(config + "_92", "w").close()
            hercules.stop()
        self.assertEqual(run.call_args_list[0].args[0], ["hercules", "start", "-m", "meta", "-d", "data", "-f", config])
        self.assertEqual(run.call_args_list[-1].args[0], ["hercules", "stop", "-f", config + "_92"])
        run.reset_mock()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLURM_JOB_ID", None)
            outside = Hercules(self.workflow(portable=False), config=config,
                               meta_hostfile="meta", data_hostfile="data")
            outside.start()
            outside.stop()
        self.assertEqual(run.call_args_list[-1].args[0], ["hercules", "stop", "-m", "meta", "-d", "data", "-f", config])

    def test_library_path_is_prepended(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "t", "true")
        workflow.add_task(task)
        Hercules(workflow, config=self.config(), library_dir="/opt/h lib").bind(task)
        self.assertIn("export LD_LIBRARY_PATH='/opt/h lib'\"${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\"",
                      task.launcher_prologue())
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/usr/lib"}):
            self.assertEqual(task.portable_environment()["LD_LIBRARY_PATH"], "/opt/h lib" + os.pathsep + "/usr/lib")

    @patch("dagon.adhoc.subprocess.run")
    def test_managed_start_ready_and_stop(self, run):
        run.return_value = Mock(returncode=0)
        workflow = self.workflow(portable=False)
        hercules = Hercules(workflow, config="hercules.conf", ready_command=["ls", "/mnt/hercules"])
        hercules.start()
        hercules.stop()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [["hercules", "start", "-f", "hercules.conf"], ["ls", "/mnt/hercules"],
                                    ["hercules", "stop", "-f", "hercules.conf"]])
        ready_environment = run.call_args_list[1].kwargs["env"]
        self.assertEqual(ready_environment["LD_PRELOAD"], "libhercules_posix.so")

    @patch("dagon.adhoc.subprocess.run")
    def test_failed_start_does_not_mark_started(self, run):
        run.return_value = Mock(returncode=1)
        hercules = Hercules(self.workflow(portable=False), config="hercules.conf")
        with self.assertRaises(AdHocFileSystemError):
            hercules.start()
        self.assertFalse(hercules.started)


class BeeONDTests(AdHocTestCase):
    def test_rejects_non_slurm_tasks(self):
        workflow = self.workflow()
        filesystem = BeeOND(workflow)
        task = DagonTask(TaskType.BATCH, "task", "true")
        with self.assertRaises(TypeError):
            filesystem.bind(task)

    def test_common_path_follows_the_allocation_mount(self):
        workflow = self.workflow()
        filesystem = workflow.create_adhoc_filesystem("beeond", name="job")
        task = DagonTask(TaskType.SLURM, "s", "true")
        workflow.add_task(task)
        filesystem.bind(task)
        self.assertIs(task.beeond, filesystem.volume)
        late = task.adhoc_late_prologue()
        self.assertIn('export DAGON_ADHOC_PATH="$DAGON_BEEOND"', late)
        self.assertIn("DAGON_ADHOC_JOB_ACCESS=posix", late)
        self.assertNotIn("DAGON_ADHOC_PATH=", "".join(
            "%s=%s" % item for item in filesystem.task_environment(task).items()))
        self.assertEqual(filesystem.metadata()["access"], "posix")
        self.assertEqual(filesystem.metadata()["provider"], "beeond")


class LoopbackDynoStore(http.server.BaseHTTPRequestHandler):
    objects = {}
    metadata = {}
    openapi_title = None      # set to answer like a DynoStore FastAPI service

    def log_message(self, *args):
        pass

    def reply(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts == [""]:
            return self.reply(404)
        if parts == ["openapi.json"] and self.openapi_title:
            return self.reply(200, json.dumps({"info": {"title": self.openapi_title}}).encode())
        if parts[0] == "storage" and parts[1] == "tok":
            if parts[-1] == "exists":
                # Like the DynoStore metadata service: 200 with an explicit
                # flag, also for objects that were removed or never stored.
                found = parts[2] in self.objects
                return self.reply(200, json.dumps({"exists": found}).encode())
            if parts[2] not in self.objects:
                return self.reply(404)
            return self.reply(200, self.objects[parts[2]])
        self.reply(403)

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if parts[:2] == ["metadata", "tok"]:
            self.metadata[parts[2]] = json.loads(body)
            return self.reply(200)
        self.reply(403)

    def do_PUT(self):
        parts = self.path.strip("/").split("/")
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if parts[:2] == ["upload", "tok"] and parts[3] in self.metadata:
            self.objects[parts[3]] = body
            return self.reply(201)
        self.reply(403)

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if parts[:2] == ["storage", "tok"] and self.objects.pop(parts[2], None) is not None:
            return self.reply(200)
        self.reply(404)


K1 = "k1-" + "0" * 32


class DynoStoreTests(AdHocTestCase):
    def gateway(self, title=None):
        LoopbackDynoStore.objects, LoopbackDynoStore.metadata = {}, {}
        LoopbackDynoStore.openapi_title = title
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), LoopbackDynoStore)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "127.0.0.1:%d" % server.server_address[1]

    def test_environment_is_credential_free(self):
        workflow = self.workflow()
        store = DynoStore(workflow, server="http://gw:8095", catalog="run-1")
        environment = store.task_environment(None)
        self.assertEqual(environment["DAGON_ADHOC_ACCESS"], "object")
        self.assertEqual(environment["DAGON_ADHOC_PATH"], "dynostore://gw:8095/run-1")
        self.assertEqual(environment["DYNOSTORE_SERVER"], "gw:8095")
        self.assertEqual(environment["DYNOSTORE_URL"], "http://gw:8095")
        self.assertEqual(environment["DYNOSTORE_AUTH_VARIABLE"], "DYNOSTORE_TOKEN")
        self.assertEqual(environment["DYNOSTORE_CATALOG"], "run-1")
        for bad in ("http://u:p@gw:8095", "gw:8095/path", "ftp://gw"):
            with self.assertRaises(ValueError):
                DynoStore(workflow, server=bad)
        with self.assertRaises(ValueError):
            DynoStore(workflow, catalog="../x")

    def test_server_defaults_to_the_dynostore_mover_section(self):
        workflow = self.workflow()
        self.assertEqual(DynoStore(workflow).server, "127.0.0.1:8095")
        workflow.cfg["dynostore"] = {"host": "gateway.example", "port": "8070"}
        self.assertEqual(DynoStore(workflow).server, "gateway.example:8070")

    def test_object_codec_matches_dynostore_client_and_never_unpickles(self):
        data = os.urandom(70_000)
        # Protocols 3+ store bytes directly; protocol 2 needs a GLOBAL call and is refused.
        for protocol in range(3, pickle.HIGHEST_PROTOCOL + 1):
            # dynostore-client's ObjectCompressor: zlib.compress(pickle.dumps(obj), 9)
            stored = zlib.compress(pickle.dumps(data, protocol=protocol), 9)
            self.assertEqual(decode_dynostore_object(stored), data)
        self.assertEqual(pickle.loads(zlib.decompress(encode_dynostore_object(data))), data)
        self.assertEqual(decode_dynostore_object(encode_dynostore_object(b"")), b"")

        class Exploit:
            def __reduce__(self):
                return (os.getpid, ())
        for hostile in (pickle.dumps(Exploit()), pickle.dumps((b"a", b"b")), pickle.dumps("text")):
            with self.assertRaises(AdHocFileSystemError):
                decode_dynostore_object(zlib.compress(hostile))
        with self.assertRaises(AdHocFileSystemError):
            decode_dynostore_object(b"not zlib")

    def test_object_round_trip_against_loopback_gateway(self):
        server = self.gateway()
        store = DynoStore(self.workflow(portable=False), server=server, catalog="cat", startup_timeout=5)
        store.start()
        self.assertTrue(store.started)
        local = os.path.join(self.scratch, "in.bin")
        payload = os.urandom(100_000)
        with open(local, "wb") as stream:
            stream.write(payload)
        with patch.dict(os.environ, {"DYNOSTORE_TOKEN": "tok"}):
            name = "obj-00000000000000000000000000000001"
            key = store.put(local, key=name)
            self.assertEqual(LoopbackDynoStore.metadata[name]["key"], name)
            self.assertEqual(LoopbackDynoStore.metadata[name]["is_encrypted"], 0)
            self.assertEqual(pickle.loads(zlib.decompress(LoopbackDynoStore.objects[name])), payload)
            self.assertTrue(store.exists(key))
            out = os.path.join(self.scratch, "out.bin")
            self.assertEqual(store.get(key, out), len(payload))
            with open(out, "rb") as stream:
                self.assertEqual(stream.read(), payload)
            store.evict(key)
            self.assertFalse(store.exists(key))
        self.assertNotIn("tok", json.dumps(store.metadata()))
        self.assertIsNone(store.stop())

    def test_task_side_cli_round_trip(self):
        server = self.gateway()
        source = os.path.join(self.scratch, "in.txt")
        target = os.path.join(self.scratch, "out.txt")
        with open(source, "w") as stream:
            stream.write("payload")
        environment = {"DYNOSTORE_SERVER": server, "DYNOSTORE_CATALOG": "c", "DYNOSTORE_TOKEN": "tok"}
        with patch.dict(os.environ, environment):
            from dagon.adhoc import main
            self.assertEqual(main(["dynostore", "put", source, K1]), 0)
            self.assertEqual(main(["dynostore", "exists", K1]), 0)
            self.assertEqual(main(["dynostore", "get", K1, target]), 0)
            self.assertEqual(main(["dynostore", "evict", K1]), 0)
            self.assertEqual(main(["dynostore", "exists", K1]), 1)
        with open(target) as stream:
            self.assertEqual(stream.read(), "payload")

    def test_keys_outside_the_catalog_grammar_are_refused_before_any_request(self):
        server = self.gateway()
        store = DynoStore(self.workflow(portable=False), server=server)
        with patch.dict(os.environ, {"DYNOSTORE_TOKEN": "tok"}):
            for key in ("short", "has.dot-" + "0" * 32, "has/slash-" + "0" * 32):
                with self.assertRaises(AdHocFileSystemError):
                    store.client().put_bytes(b"x", key)
            self.assertEqual(LoopbackDynoStore.metadata, {})
            self.assertTrue(DYNOSTORE_KEY.match(store.client().put_bytes(b"x")))

    def test_missing_token_and_errors_never_leak_it(self):
        server = self.gateway()
        store = DynoStore(self.workflow(portable=False), server=server)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DYNOSTORE_TOKEN", None)
            with self.assertRaises(AdHocFileSystemError):
                store.exists("k")
        with patch.dict(os.environ, {"DYNOSTORE_TOKEN": "wrong-secret"}):
            with self.assertRaises(AdHocFileSystemError) as caught:
                store.evict("k")
        self.assertNotIn("wrong-secret", str(caught.exception))
        self.assertIn("HTTP 404", str(caught.exception))

    def test_unreachable_gateway_fails_startup(self):
        store = DynoStore(self.workflow(portable=False), server="127.0.0.1:9", startup_timeout=1)
        with self.assertRaises(AdHocFileSystemError):
            store.start()
        self.assertFalse(store.started)

    @POSIX_ONLY
    def test_managed_compose_deployment(self):
        server = self.gateway()
        log = os.path.join(self.scratch, "docker.log")
        docker = write_script(self.scratch, "docker", """
            import sys
            with open(%r, "a") as stream:
                stream.write(" ".join(sys.argv[1:]) + "\\n")
        """ % log)
        compose = os.path.join(self.scratch, "docker-compose.yml")
        open(compose, "w").close()
        store = DynoStore(self.workflow(portable=False), server=server, compose_file=compose,
                          compose_project="dagon", docker=docker,
                          setup_commands=[[docker, "compose", "exec", "metadata", "true"]])
        store.start()
        store.stop()
        with open(log, encoding="utf-8") as stream:
            lines = stream.read().splitlines()
        self.assertEqual(lines, ["compose -f %s -p dagon up -d" % compose, "compose exec metadata true",
                                 "compose -f %s -p dagon down" % compose])

    def test_metadata_service_port_is_reported_and_build_is_optional(self):
        server = self.gateway(title="DynoStore-Metadata")
        log = os.path.join(self.scratch, "docker.log")
        docker = write_script(self.scratch, "docker", """
            import sys
            with open(%r, "a") as stream:
                stream.write(" ".join(sys.argv[1:]) + "\\n")
        """ % log)
        compose = os.path.join(self.scratch, "docker-compose.dev.yml")
        open(compose, "w").close()
        store = DynoStore(self.workflow(portable=False), server=server, compose_file=compose,
                          docker=docker, compose_build=True)
        with patch.dict(os.environ, {"DYNOSTORE_TOKEN": "secret-token-value"}):
            with self.assertRaisesRegex(AdHocFileSystemError, "metadata service, not the API gateway") as caught:
                store.start()
        self.assertNotIn("secret-token-value", str(caught.exception))
        with open(log, encoding="utf-8") as stream:
            self.assertEqual(stream.read().splitlines(), ["compose -f %s up -d --build" % compose,
                                                          "compose -f %s down" % compose])
        self.assertFalse(store.started)
        # A gateway (no DynoStore OpenAPI description) is accepted.
        self.assertIsNone(DynoStore(self.workflow(), server=self.gateway()).misdirected())

    @POSIX_ONLY
    def test_setup_commands_learn_the_compose_file_and_project(self):
        server = self.gateway()
        log = os.path.join(self.scratch, "setup.log")
        docker = write_script(self.scratch, "docker", "")
        setup = write_script(self.scratch, "setup", """
            import os
            with open(%r, "w") as stream:
                stream.write(os.environ["DYNOSTORE_COMPOSE_FILE"] + "|" + os.environ["DYNOSTORE_PROJECT"])
        """ % log)
        compose = os.path.join(self.scratch, "docker-compose.dev.yml")
        open(compose, "w").close()
        store = DynoStore(self.workflow(portable=False), server=server, compose_file=compose,
                          compose_project="dagon", docker=docker, setup_commands=[[setup]])
        with patch.dict(os.environ, {"DYNOSTORE_TOKEN": "secret-token-value"}):
            store.start()
            store.stop()
        with open(log, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), os.path.abspath(compose) + "|dagon")

    @POSIX_ONLY
    def test_failed_setup_brings_the_stack_down(self):
        log = os.path.join(self.scratch, "docker.log")
        docker = write_script(self.scratch, "docker", """
            import sys
            with open(%r, "a") as stream:
                stream.write(" ".join(sys.argv[1:]) + "\\n")
            sys.exit(1 if "exec" in sys.argv else 0)
        """ % log)
        compose = os.path.join(self.scratch, "c.yml")
        store = DynoStore(self.workflow(portable=False), compose_file=compose, docker=docker,
                          setup_commands=[[docker, "compose", "exec", "x"]])
        with self.assertRaises(AdHocFileSystemError):
            store.start()
        with open(log, encoding="utf-8") as stream:
            self.assertTrue(stream.read().splitlines()[-1].endswith("down"))
        self.assertFalse(store.started)

    def test_portable_task_sees_object_store_variables(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "t",
                         'test "$DAGON_ADHOC_ACCESS" = object && test -d "$DYNOSTORE_EMULATED_DIR"')
        workflow.add_task(task)
        workflow.create_adhoc_filesystem("dynostore", catalog="c").bind(task)
        workflow.run()
        self.assertEqual(task.result["code"], 0)


class InteroperabilityTests(AdHocTestCase):
    def test_cwl_export_omits_execution_resources(self):
        workflow = self.workflow()
        task = DagonTask(TaskType.BATCH, "t", "echo hi")
        workflow.add_task(task)
        workflow.create_adhoc_filesystem("capio", library="/opt/libcapio_posix.so").bind(task)
        target = os.path.join(self.scratch, "wf.cwl")
        workflow.saveAsCWL(target)
        with open(target, encoding="utf-8") as stream:
            text = stream.read()
        self.assertNotIn("libcapio_posix", text)
        self.assertNotIn("DAGON_ADHOC", text)

    def test_metadata_is_json_serialisable_and_credential_free(self):
        workflow = self.workflow()
        resources = [create(workflow, "dagonfs", name="a", frontend="native", mountpoint="/tmp/a.sock"),
                     create(workflow, "capio", name="b"), create(workflow, "hercules", name="c", config="h.conf"),
                     create(workflow, "dynostore", name="d", token_env="MY_STORE_TOKEN")]
        text = json.dumps([resource.metadata() for resource in resources])
        self.assertNotIn("TOKEN", text)
        self.assertEqual({item["access"] for item in json.loads(text)}, {"client", "preload", "object"})


if __name__ == "__main__":
    unittest.main()
