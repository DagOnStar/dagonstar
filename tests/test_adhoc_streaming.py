"""Streams, adapter registry, scopes, and multiple volumes of dagon.adhoc.

Everything runs locally: streams use the out-of-package ``local-directory``
adapter of ``examples/adhoc/custom_adapter.py`` (a real local resource), an
in-memory object store, or a stand-in for DAGonFS's native client.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples" / "adhoc"))

from dagon import Status, Workflow  # noqa: E402
from dagon import adhoc  # noqa: E402
from dagon import streaming  # noqa: E402
from dagon.adhoc import AdHocFileSystem, register_provider, unregister_provider  # noqa: E402
from dagon.streaming import (ObjectStreamStore, PosixStreamStore, StreamError,  # noqa: E402
                             StreamProducerFailed, StreamReader, StreamWriter)
from dagon import task as dagon_task  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
import custom_adapter  # noqa: E402
import streaming as streaming_example  # noqa: E402


def config(scratch):
    return {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "8"},
            "slurm": {"partition": ""},
            "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}


class Plain(AdHocFileSystem):
    """A POSIX adapter that does not declare streaming support."""
    provider = "plain-test"

    @property
    def task_path(self):
        return os.path.join(self.workflow.get_scratch_dir_base(), "plain-" + self.name)


class Recorder(custom_adapter.LocalDirectory):
    """Records when the resource starts and stops relative to its tasks."""
    provider = "recorder-test"
    events = []

    def start(self):
        Recorder.events.append(("start", self.name))
        super().start()

    def stop(self):
        Recorder.events.append(("stop", self.name))
        return super().stop()


class MemoryObjects:
    def __init__(self):
        self.objects = {}
        self.lock = threading.Lock()

    def put_bytes(self, data, key):
        with self.lock:
            self.objects[key] = bytes(data)
        return key

    def get_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects


class ReferenceTest(unittest.TestCase):
    def test_query_is_optional_and_backward_compatible(self):
        plain = streaming.parse_reference("workflow:///A/out/f1.txt")
        self.assertEqual((plain.workflow, plain.task, plain.path, plain.stream), ("", "A", "out/f1.txt", False))
        named = streaming.parse_reference("workflow://wf/B1/frames?stream=ram")
        self.assertEqual((named.workflow, named.task, named.path), ("wf", "B1", "frames"))
        self.assertTrue(named.stream)
        self.assertEqual(named.stream_filesystem, "ram")
        self.assertIsNone(streaming.parse_reference("workflow:///B1/frames?stream").stream_filesystem)

    def test_other_question_marks_keep_their_legacy_meaning(self):
        # Before queries existed, "?" was an ordinary path character (for
        # example a shell glob); only ``?stream[=name]`` is interpreted.
        for text, path in (("workflow:///A/out?.txt", "out?.txt"), ("workflow:///A/f?mode=fast", "f?mode=fast"),
                           ("workflow:///A/f?stream&x", "f?stream&x")):
            reference = streaming.parse_reference(text)
            self.assertEqual((reference.path, reference.query, reference.stream), (path, (), False))
        with tempfile.TemporaryDirectory() as scratch:
            workflow = Workflow("glob", config=config(scratch))
            workflow.add_task(DagonTask(TaskType.BATCH, "A", "touch out1.txt"))
            workflow.add_task(DagonTask(TaskType.BATCH, "B", "cat workflow:///A/out?.txt"))
            workflow.make_dependencies()
            self.assertEqual(workflow.plan_streams(prepare=False), [])

    def test_unsafe_stream_paths_are_refused(self):
        for path in ("../x", ".hidden", "", "a/../b"):
            with self.assertRaises(ValueError):
                streaming.validate_stream_path(path)

    def test_stream_reference_builder(self):
        self.assertEqual(streaming.stream_reference("B1", "frames"), "workflow:///B1/frames?stream")
        self.assertEqual(streaming.stream_reference("B1", "frames", "ram"), "workflow:///B1/frames?stream=ram")

    def test_structured_task_types_refuse_streams(self):
        from dagon.faas import FaaSTask
        from dagon.iot.task import IoTTask
        from dagon.llm import LLMTask
        from dagon.native import NativeTask
        from dagon.web.task import WebTask
        from dagon.agentic.models import parse_reference
        reference = "workflow:///B1/frames?stream"
        for parse in (FaaSTask._parse_reference, IoTTask._parse_reference, LLMTask._parse_reference,
                      NativeTask._parse_reference, WebTask._parse_reference, parse_reference):
            with self.assertRaisesRegex(ValueError, "cannot consume streams"):
                parse(reference)
        for task_type in (FaaSTask, IoTTask, LLMTask, NativeTask, WebTask):
            self.assertFalse(task_type.stream_capable)


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def pair(self, store):
        writer = StreamWriter(store, os.path.join(self.root, "state", "s.json"))
        return writer, StreamReader(store, poll=0.001, max_poll=0.01, idle_timeout=5)

    def test_items_arrive_in_order_and_verified(self):
        store = PosixStreamStore(os.path.join(self.root, "base", "run", "frames"), os.path.join(self.root, "base"))
        os.makedirs(os.path.join(self.root, "base"))
        writer, reader = self.pair(store)
        for index in range(5):
            writer.publish_bytes("item-%d" % index, b"x" * index)
        writer.close(0)
        writer.close(0)  # idempotent
        items = list(reader)
        self.assertEqual([item.name for item in items], ["item-%d" % i for i in range(5)])
        self.assertEqual([reader.read(item) for item in items], [b"x" * i for i in range(5)])
        self.assertEqual(reader.end["items"], 5)
        with self.assertRaises(StreamError):
            writer.publish_bytes("late", b"")

    def test_commit_reads_back_an_item_written_in_place(self):
        location = os.path.join(self.root, "frames")
        writer, reader = self.pair(PosixStreamStore(location))
        writer.store.prepare()
        Path(location, "a.dat").write_bytes(b"payload")
        writer.commit("a.dat")
        writer.close()
        item = next(iter(reader))
        self.assertEqual((item.size, reader.path(item)), (7, location + "/a.dat"))

    def test_partial_marker_is_retried_and_reader_follows_a_live_producer(self):
        location = os.path.join(self.root, "frames")
        store = PosixStreamStore(location)
        store.prepare()
        marker = os.path.join(location, ".dagon-stream", "000000001")
        Path(marker).write_bytes(b'{"v": 1, "seq": 1, "item": "a"')  # no newline: incomplete
        self.assertIsNone(streaming._parse_marker(store.read_marker(1), 1))
        writer, reader = self.pair(store)

        def produce():
            # The producer's first marker replaces the partial one in place
            # (removing it would fail on Windows while the reader polls it).
            for index in range(3):
                writer.publish_bytes("f%d" % index, b"%d" % index)
            writer.close()

        producer = threading.Timer(0.05, produce)
        producer.start()
        self.assertEqual([reader.read(item) for item in reader], [b"0", b"1", b"2"])
        producer.join()

    def test_failed_producer_and_corrupt_item_are_reported(self):
        writer, reader = self.pair(PosixStreamStore(os.path.join(self.root, "s")))
        writer.publish_bytes("a", b"abc")
        Path(self.root, "s", "a").write_bytes(b"abd")
        writer.close(7)
        iterator = iter(reader)
        item = next(iterator)
        with self.assertRaises(StreamError):
            reader.read(item)
        with self.assertRaises(StreamProducerFailed):
            next(iterator)

    def test_a_reader_stops_after_the_producer_ended_signal_and_grace(self):
        writer, reader = self.pair(PosixStreamStore(os.path.join(self.root, "s")))
        writer.publish_bytes("a", b"abc")
        signal = os.path.join(self.root, "P_OUT.ended")
        reader.signal, reader.grace, reader.idle_timeout = signal, 0.05, None
        iterator = iter(reader)
        self.assertEqual(next(iterator).name, "a")
        Path(signal).write_text('{"status": 1}')
        with self.assertRaisesRegex(StreamError, "ended without ending the stream"):
            next(iterator)

    def test_idle_timeout_and_item_names(self):
        writer, reader = self.pair(PosixStreamStore(os.path.join(self.root, "s")))
        reader.idle_timeout = 0.05
        with self.assertRaisesRegex(StreamError, "no stream marker"):
            next(iter(reader))
        for name in ("../x", ".dagon-stream", "a/b", ""):
            with self.assertRaises(StreamError):
                writer.publish_bytes(name, b"")

    def test_concurrent_publishers_get_distinct_sequence_numbers(self):
        writer, reader = self.pair(PosixStreamStore(os.path.join(self.root, "s")))
        threads = [threading.Thread(target=writer.publish_bytes, args=("t%d" % i, b"%d" % i)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        writer.close()
        self.assertEqual(sorted(item.name for item in reader), sorted("t%d" % i for i in range(8)))

    def test_object_store_uses_deterministic_keys(self):
        objects = MemoryObjects()
        writer, reader = self.pair(ObjectStreamStore(objects, "run/wf/B1/frames"))
        writer.publish_bytes("a", b"1")
        writer.close()
        self.assertEqual(len(objects.objects), 3)
        self.assertTrue(all(adhoc.DYNOSTORE_KEY.match(key) for key in objects.objects))
        self.assertEqual([reader.read(item) for item in reader], [b"1"])

    def test_dynostore_and_dagonfs_native_stores_come_from_their_adapters(self):
        spec = {"access": "object", "location": "dynostore://h:1/cat/run/wf/B1/frames",
                "parameters": {"url": "http://h:1", "catalog": "cat", "auth_variable": "DYNOSTORE_TOKEN"}}
        store = adhoc.DynoStore.open_stream_store(spec)
        self.assertIsInstance(store, ObjectStreamStore)
        self.assertEqual(store.name, "h:1/cat/run/wf/B1/frames")
        calls = []

        class Client:
            def __init__(self, socket_path):
                calls.append(socket_path)
                self.files = {}

            def makedirs(self, path):
                calls.append(("makedirs", path))

            def write_bytes(self, path, data):
                self.files[path] = data

            def read_bytes(self, path):
                if path not in self.files:
                    raise FileNotFoundError(path)
                return self.files[path]

        module = types.ModuleType("dagonfs.native")
        module.Client = Client
        with mock.patch.dict(sys.modules, {"dagonfs": types.ModuleType("dagonfs"), "dagonfs.native": module}):
            native = adhoc.DAGonFS.open_stream_store({"access": "client", "location": "/.dagon-streams/r/w/B1/f",
                                                      "parameters": {"socket": "/tmp/s.sock"}})
            writer, reader = self.pair(native)
            writer.publish_bytes("x", b"data")
            writer.close()
            self.assertEqual([reader.read(item) for item in reader], [b"data"])
        self.assertEqual(calls[0], "/tmp/s.sock")
        self.assertIn(("makedirs", "/.dagon-streams/r/w/B1/f/.dagon-stream"), calls)


class RegistryTest(unittest.TestCase):
    def tearDown(self):
        unregister_provider("plain-test")

    def test_register_create_and_protect_builtins(self):
        register_provider("plain-test", Plain)
        self.assertIn("plain-test", adhoc.available_providers())
        workflow = Workflow("registry", config=config(tempfile.gettempdir()))
        self.assertIsInstance(workflow.create_adhoc_filesystem("PLAIN-TEST", name="a"), Plain)
        self.assertIsInstance(workflow.create_adhoc_filesystem(Plain, name="b"), Plain)
        with self.assertRaises(ValueError):
            register_provider("plain-test", Recorder)
        with self.assertRaises(TypeError):
            register_provider("bad", object)
        with self.assertRaises(ValueError):
            unregister_provider("capio")
        # Built-in names are protected even with replace=True, and stay unchanged.
        builtin = adhoc.PROVIDERS["dagonfs"]
        for replace in (False, True):
            with self.assertRaises(ValueError):
                register_provider("dagonfs", Plain, replace=replace)
            with self.assertRaises(ValueError):
                register_provider("DAGonFS", Plain, replace=replace)
        self.assertIs(adhoc.PROVIDERS["dagonfs"], builtin)
        self.assertIs(register_provider("dagonfs", builtin), builtin)
        self.assertEqual(sorted(adhoc.BUILTIN_PROVIDERS),
                         ["beeond", "capio", "dagonfs", "dynostore", "hercules"])

    def test_entry_points_register_adapters_lazily(self):
        class Entry:
            name = "entry-test"

            @staticmethod
            def load():
                return Plain

        class Found:
            @staticmethod
            def select(group):
                return [Entry] if group == adhoc.ENTRY_POINT_GROUP else []

        with mock.patch.object(adhoc, "_ENTRY_POINTS_LOADED", False), \
                mock.patch("importlib.metadata.entry_points", return_value=Found()):
            workflow = Workflow("entry", config=config(tempfile.gettempdir()))
            self.assertIsInstance(workflow.create_adhoc_filesystem("entry-test"), Plain)
        unregister_provider("entry-test")


class ScopeAndVolumeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.scratch = self.directory.name
        register_provider("recorder-test", Recorder, replace=True)
        Recorder.events = []

    def tearDown(self):
        unregister_provider("recorder-test")
        self.directory.cleanup()

    def test_conflicting_preload_libraries_are_refused_in_one_task(self):
        def resources(emulate=False):
            workflow = Workflow("conflict", config=config(self.scratch), portable_emulation=emulate)
            first, second = DagonTask(TaskType.BATCH, "a", "true"), DagonTask(TaskType.BATCH, "b", "true")
            workflow.add_task(first)
            workflow.add_task(second)
            capio = workflow.create_adhoc_filesystem("capio", name="c", server="capio_server")
            hercules = workflow.create_adhoc_filesystem("hercules", name="h", config="site.conf")
            return first, second, capio, hercules
        first, second, capio, hercules = resources()
        capio.bind(first)
        with self.assertRaisesRegex(adhoc.AdHocFileSystemError, "cannot be loaded in one process"):
            hercules.bind(first)
        self.assertEqual([fs.name for fs in first.adhoc_filesystems], ["c"])
        hercules.bind(second)                       # separate tasks are fine
        dagonfs = second.workflow.create_adhoc_filesystem("dagonfs", name="d", frontend="preload",
                                                          preload_library="libdagonfs_preload.so")
        dagonfs.bind(first)                         # DAGonFS preload composes with CAPIO
        first, _, capio, hercules = resources(emulate=True)
        capio.bind(first)
        hercules.bind(first)                        # emulation preloads nothing

        class Picky(custom_adapter.LocalDirectory):
            provider = "picky"
            preload_conflicts = ("local-directory",)
        workflow = Workflow("third-party", config=config(self.scratch))
        task = DagonTask(TaskType.BATCH, "t", "true")
        workflow.add_task(task)
        workflow.create_adhoc_filesystem(custom_adapter.LocalDirectory, name="x").bind(task)
        with self.assertRaises(adhoc.AdHocFileSystemError):
            workflow.create_adhoc_filesystem(Picky, name="y").bind(task)

    def test_task_scope_starts_around_its_task_and_workflow_default_binds_all(self):
        workflow = Workflow("scopes", config=config(self.scratch))
        first = DagonTask(TaskType.BATCH, "first", 'echo one > "$DAGON_ADHOC_SHARED_PATH/one.txt"')
        second = DagonTask(TaskType.BATCH, "second", 'echo workflow:///first/ >/dev/null; '
                           'cat "$DAGON_ADHOC_SHARED_PATH/one.txt" > "$DAGON_ADHOC_MINE_PATH/copy.txt"; '
                           'echo "$DAGON_ADHOC_NAMES" > names.txt')
        workflow.add_task(first)
        workflow.add_task(second)
        shared = workflow.create_adhoc_filesystem("recorder-test", name="shared", default=True)
        mine = second.create_adhoc_filesystem("recorder-test", name="mine")
        self.assertEqual(mine.scope, "task")
        with self.assertRaisesRegex(ValueError, "task-scope"):
            mine.bind(first)
        workflow.run()
        self.assertEqual([task.status for task in workflow.tasks], [Status.FINISHED, Status.FINISHED])
        self.assertEqual(Recorder.events, [("start", "shared"), ("start", "mine"), ("stop", "mine"),
                                           ("stop", "shared")])
        self.assertEqual(Path(second.working_dir, "names.txt").read_text().strip(), "mine,shared")
        self.assertEqual(shared.tasks, [first, second])
        self.assertEqual({item["scope"] for item in second.get_execution_metadata()["adhoc_filesystems"]},
                         {"task", "workflow"})

    def test_task_scope_start_failure_fails_only_that_task(self):
        workflow = Workflow("scope-failure", config=config(self.scratch))
        task = DagonTask(TaskType.BATCH, "t", "true")
        workflow.add_task(task)
        resource = task.create_adhoc_filesystem("recorder-test", name="broken")
        with mock.patch.object(Recorder, "start", side_effect=adhoc.AdHocFileSystemError("down")):
            workflow.run()
        self.assertEqual((task.status, task.failure_phase), (Status.FAILED, "adhoc"))
        self.assertFalse(resource.started)

    def test_scope_validation(self):
        workflow = Workflow("scope-validation", config=config(self.scratch))
        with self.assertRaises(ValueError):
            workflow.create_adhoc_filesystem("recorder-test", scope="node")
        with self.assertRaises(ValueError):
            workflow.create_adhoc_filesystem("recorder-test", scope="task", default=True)
        with self.assertRaises(ValueError):
            DagonTask(TaskType.BATCH, "orphan", "true").create_adhoc_filesystem("recorder-test")

    def test_preload_libraries_of_several_resources_compose(self):
        workflow = Workflow("volumes", config=config(self.scratch))
        task = DagonTask(TaskType.BATCH, "both", "true")
        workflow.add_task(task)
        first = workflow.create_adhoc_filesystem("capio", name="one", library="/opt/a/libcapio_posix.so")
        # CAPIO with the DAGonFS preload frontend: the pair that worked live
        # (CAPIO with Hercules is refused, see the conflict test).
        second = workflow.create_adhoc_filesystem("dagonfs", name="two", frontend="preload",
                                                  preload_library="/opt/b/libdagonfs_preload.so")
        first.bind(task)
        second.bind(task)
        prologue = task.launcher_prologue()
        self.assertIn('export LD_PRELOAD=/opt/a/libcapio_posix.so"${LD_PRELOAD:+:$LD_PRELOAD}"', prologue)
        variable = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
        self.assertIn('export %s=/opt/b/libdagonfs_preload.so"${%s:+:$%s}"' % ((variable,) * 3), prologue)
        self.assertIn("export DAGON_ADHOC_NAMES=one,two", prologue)
        self.assertIn("DAGON_ADHOC_ONE_PROVIDER=capio", prologue)
        self.assertNotEqual(first.capio_workflow_name, workflow.create_adhoc_filesystem(
            "capio", name="three").capio_workflow_name)
        self.assertEqual(workflow.create_adhoc_filesystem("capio").capio_workflow_name, "volumes")

    def test_peer_to_peer_streams_use_the_mount_of_their_own_node(self):
        workflow = Workflow("p2p", config=config(self.scratch))
        task = DagonTask(TaskType.BATCH, "t", "true")
        workflow.add_task(task)
        root = os.path.join(self.scratch, "dfs")
        volume = workflow.create_adhoc_filesystem("dagonfs", name="shared", model="peer-to-peer",
                                                  ranks=2, mountpoint=root)
        volume.bind(task)
        parameters = volume.stream_parameters()
        self.assertEqual(parameters, {"base": os.path.join(root, "0"), "peer_root": root, "ranks": "2"})
        spec = {"location": os.path.join(root, "0", ".dagon-streams", "B1", "frames"),
                "access": "posix", "parameters": parameters}
        mounted = set()
        with mock.patch.object(streaming.os.path, "ismount", side_effect=lambda p: p in mounted):
            self.assertEqual(streaming.node_local_location(spec), (spec["location"], parameters["base"]))
            mounted.add(os.path.join(root, "1"))    # this node runs rank 1 only
            self.assertEqual(streaming.node_local_location(spec),
                             (os.path.join(root, "1", ".dagon-streams", "B1", "frames"), os.path.join(root, "1")))
            mounted.add(os.path.join(root, "0"))    # rank 0 here: the recorded path
            self.assertEqual(streaming.node_local_location(spec)[1], parameters["base"])
        # The launcher picks the rank listed in the node's mount table.
        lines = volume.launcher_environment_lines()
        self.assertIn("/proc/mounts", lines[0])
        self.assertIn(task.adhoc_late_prologue().strip(), "\n".join(lines))
        table = os.path.join(self.scratch, "mounts")
        with open(table, "w") as stream:
            stream.write("dagonfs %s/1x fuse 0 0\ndagonfs %s/1 fuse.dagonfs rw 0 0\n" % (root, root))
        script = "\n".join(['export DAGON_ADHOC_NAME=shared DAGON_ADHOC_PATH=unset'] +
                           [line.replace("/proc/mounts", table) for line in lines] +
                           ['echo "$DAGON_ADHOC_PATH|$DAGON_ADHOC_SHARED_PATH|$DAGONFS_MOUNTPOINT"'])
        from dagon.platform_support import bash_executable
        if sys.platform != "win32":
            output = subprocess.run([bash_executable(), "-c", script], capture_output=True, text=True, check=True)
            local = os.path.join(root, "1")
            self.assertEqual(output.stdout.strip(), "|".join([local] * 3))
        # Other models and frontends keep their static paths.
        self.assertEqual(workflow.create_adhoc_filesystem("dagonfs", name="cs").launcher_environment_lines(), [])
        self.assertNotIn("peer_root", workflow.create_adhoc_filesystem("dagonfs", name="cs2").stream_parameters())

    def test_resource_names_never_count_as_credentials(self):
        workflow = Workflow("names", config=config(self.scratch))
        task = DagonTask(TaskType.BATCH, "t", "true")
        workflow.add_task(task)
        workflow.create_adhoc_filesystem("recorder-test", name="private-token").bind(task)
        self.assertIn("DAGON_ADHOC_PRIVATE_TOKEN_PATH", task.launcher_prologue())


class StreamWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.scratch = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def test_only_the_streaming_edge_overlaps(self):
        workflow = streaming_example.build(self.scratch)
        workflow.run()
        streaming_example.check(workflow)
        tasks = {task.name: task for task in workflow.tasks}
        self.assertEqual(tasks["D"].stream_prevs, [])
        self.assertEqual(sorted(task.name for task in tasks["D"].prevs), ["B2", "C"])
        metadata = tasks["B2"].get_execution_metadata()["streams"]
        self.assertEqual(metadata, [{"producer": "B1", "path": "frames", "adhoc": "frames",
                                     "provider": "local-directory", "consumers": ["B2"], "role": "consumer"}])
        launcher = Path(tasks["B1"].working_dir, ".dagon", "launcher.sh")
        if launcher.exists():
            self.assertIn("stream close", launcher.read_text())

    def test_portable_emulation_with_each_builtin_provider(self):
        for provider in ("dagonfs", "capio", "hercules", "dynostore"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as scratch:
                workflow = streaming_example.build(scratch, provider)
                workflow.run()
                streaming_example.check(workflow)
                channel = workflow.streams[0]
                self.assertTrue(channel.emulated)
                self.assertIn(".adhoc-emulated", channel.location)

    def failing_workflow(self, producer_command):
        workflow = Workflow("stream-failure", config=config(self.scratch))
        producer = DagonTask(TaskType.BATCH, "P", producer_command)
        consumer = DagonTask(TaskType.BATCH, "Q", '"$DAGON_PYTHON" -m dagon.adhoc stream items '
                             'workflow:///P/out?stream > items.txt')
        after = DagonTask(TaskType.BATCH, "R", "cat workflow:///Q/items.txt")
        for task in (producer, consumer, after):
            workflow.add_task(task)
        volume = workflow.create_adhoc_filesystem(custom_adapter.LocalDirectory, name="v", keep=True)
        volume.bind(producer)
        volume.bind(consumer)
        workflow.run()
        return producer, consumer, after

    def test_a_failed_producer_fails_its_consumer_and_dependants(self):
        producer, consumer, after = self.failing_workflow(
            'echo a > a.txt; "$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" a.txt; exit 4')
        self.assertEqual((producer.status, consumer.status, after.status),
                         (Status.FAILED, Status.FAILED, Status.FAILED))
        self.assertIn("status 1", consumer.result["message"])
        self.assertEqual(Path(consumer.working_dir, "items.txt").read_text().count("\n"), 1)

    def test_an_early_exit_still_ends_the_stream_in_the_launcher(self):
        # ``exit`` before the last command leaves the launcher before its epilogue;
        # the host does not close the stream here, so the EXIT trap must.
        with mock.patch.object(dagon_task.Task, "close_streams_from_host", autospec=True) as host:
            producer, consumer, after = self.failing_workflow(
                'echo a > a.txt; "$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" a.txt; exit 3; true')
        self.assertEqual((producer.status, consumer.status), (Status.FAILED, Status.FAILED))
        self.assertIn("status 3", consumer.result["message"])
        host.assert_called()

    def test_the_ended_signal_is_written_before_the_host_closes_the_stream(self):
        seen = []

        def close(task, status):
            seen.append(all(os.path.exists(channel.signal) for channel in task.stream_outputs.values()))
        with mock.patch.object(dagon_task.Task, "close_streams_from_host", autospec=True, side_effect=close):
            self.failing_workflow("exit 2")
        self.assertEqual(seen, [True])

    def test_a_producer_failing_before_its_command_releases_the_consumer(self):
        workflow = Workflow("early-failure", config=config(self.scratch))
        early = DagonTask(TaskType.BATCH, "P", "true")
        late = DagonTask(TaskType.BATCH, "Q", "cat workflow:///P/out?stream")
        workflow.add_task(early)
        workflow.add_task(late)
        volume = workflow.create_adhoc_filesystem(custom_adapter.LocalDirectory, name="v")
        volume.bind(early)
        volume.bind(late)
        with mock.patch.object(type(early), "execute", side_effect=RuntimeError("staging failed")):
            workflow.run()
        self.assertEqual((early.status, late.status), (Status.FAILED, Status.FAILED))
        self.assertFalse(late.stream_launched, "the consumer never ran its command")

    def test_planning_errors(self):
        def plan(command, bind=("P", "Q"), adapter=custom_adapter.LocalDirectory, extra=False):
            workflow = Workflow("plan", config=config(self.scratch))
            tasks = {"P": DagonTask(TaskType.BATCH, "P", "true"), "Q": DagonTask(TaskType.BATCH, "Q", command)}
            for task in tasks.values():
                workflow.add_task(task)
            volume = workflow.create_adhoc_filesystem(adapter, name="v")
            for name in bind:
                volume.bind(tasks[name])
            if extra:
                other = workflow.create_adhoc_filesystem(custom_adapter.LocalDirectory, name="w")
                for name in bind:
                    other.bind(tasks[name])
            if "workflow://other" not in command:
                workflow.make_dependencies()
            return workflow.plan_streams(prepare=False), tasks

        channels, tasks = plan("cat workflow:///P/out?stream")
        self.assertEqual(tasks["Q"].stream_prevs, [tasks["P"]])
        self.assertEqual(channels[0].location.split("/.dagon-streams/")[1].split("/")[1:], ["plan", "P", "out"])
        channels, tasks = plan("cat workflow:///P/out?stream workflow:///P/file.txt")
        self.assertEqual(tasks["Q"].stream_prevs, [], "a plain reference to the producer keeps the edge sequential")
        with self.assertRaisesRegex(ValueError, "share no ad-hoc file system"):
            plan("cat workflow:///P/out?stream", bind=("P",))
        with self.assertRaisesRegex(ValueError, "supports streaming"):
            plan("cat workflow:///P/out?stream", adapter=Plain)
        with self.assertRaisesRegex(ValueError, "several streaming resources"):
            plan("cat workflow:///P/out?stream", extra=True)
        channels, _ = plan("cat workflow:///P/out?stream=w", extra=True)
        self.assertEqual(channels[0].filesystem.name, "w")
        with self.assertRaisesRegex(ValueError, "not bound to both"):
            plan("cat workflow:///P/out?stream=zz")
        with self.assertRaisesRegex(ValueError, "between workflows"):
            plan("cat workflow://other/P/out?stream")

    def test_cwl_export_materializes_the_stream_and_keeps_the_intent(self):
        workflow = streaming_example.build(self.scratch)
        target = os.path.join(self.scratch, "streaming.cwl")
        workflow.saveAsCWL(target)
        document = json.loads(Path(target).read_text())
        self.assertEqual(document["$namespaces"], {"dagon": "https://dagonstar.org/cwl#"})
        producer, consumer = document["steps"]["B1"], document["steps"]["B2"]
        self.assertIn("stream_b1_frames", producer["out"])
        self.assertEqual(producer["run"]["outputs"]["stream_b1_frames"],
                         {"type": "Directory", "outputBinding": {"glob": ".dagon-streams/frames"}})
        self.assertEqual(consumer["in"]["stream_b1_frames"], "B1/stream_b1_frames")
        self.assertIn("$(inputs.stream_b1_frames.path)", consumer["run"]["arguments"][0])
        self.assertNotIn("?stream", json.dumps(document))
        self.assertEqual(consumer["run"]["hints"]["dagon:Stream"]["inputs"][0]["producer"], "B1")
        environment = producer["run"]["requirements"]["EnvVarRequirement"]["envDef"]
        self.assertEqual(environment["DAGON_STREAM_OUT"], "$(runtime.outdir)/.dagon-streams/frames")
        self.assertIn("stream close", producer["run"]["arguments"][0])

    def test_portable_cwl_export_reads_the_stream_from_the_producer_directory(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "cwl"))
        import export_streaming_workflow
        target = os.path.join(self.scratch, "portable.cwl")
        export_streaming_workflow.build_workflow(self.scratch).saveAsCWL(target)
        document = json.loads(Path(target).read_text())
        consumer = document["steps"]["consume"]
        self.assertEqual(consumer["in"], {"after_produce": "produce/task_dir"})
        self.assertIn("$(inputs.after_produce.path)/.dagon-streams/items", consumer["run"]["arguments"][0])
        environment = consumer["run"]["requirements"]["EnvVarRequirement"]["envDef"]
        self.assertEqual(environment["DAGON_STREAM_IDLE_TIMEOUT"], "60")
        hint = consumer["run"]["hints"]["dagon:Stream"]["inputs"][0]
        self.assertEqual(hint, {"producer": "produce", "stream": "items", "adhoc": "ram", "provider": "dagonfs"})

    @unittest.skipUnless(shutil.which("cwltool"), "cwltool is not installed")
    def test_portable_cwl_export_runs_with_cwltool(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "cwl"))
        import export_streaming_workflow
        target = os.path.join(self.scratch, "portable.cwl")
        export_streaming_workflow.build_workflow(self.scratch).saveAsCWL(target)
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        completed = subprocess.run(["cwltool", "--quiet", "--preserve-environment", "PYTHONPATH", target],
                                   cwd=self.scratch, env=environment, capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertTrue(json.loads(completed.stdout)["consume_completed"])

    def test_fair_edge_records_the_stream(self):
        from dagon.fair.recorder import FairRecorder
        workflow = streaming_example.build(self.scratch)
        workflow.make_dependencies()
        recorder = FairRecorder.__new__(FairRecorder)
        recorder.run = {"dependencies": []}
        recorder.on_dependencies_made(workflow)
        edges = {(edge["producer"], edge["consumer"]): edge for edge in recorder.run["dependencies"]}
        self.assertEqual(edges[("B1", "B2")]["path"], "frames")
        self.assertEqual(edges[("B1", "B2")]["transfer"], "stream")
        self.assertNotIn("transfer", edges[("A", "B1")])

    def test_json_round_trip_keeps_the_stream_reference(self):
        workflow = streaming_example.build(self.scratch)
        document = workflow.as_json()
        self.assertIn("workflow:///B1/frames?stream", document["tasks"]["B2"]["command"])

    def test_prestaging_and_checkpoint_rules(self):
        workflow = streaming_example.build(self.scratch)
        workflow.make_dependencies()
        workflow.plan_streams(prepare=False)
        tasks = {task.name: task for task in workflow.tasks}
        tasks["B1"].pre_stage_capable = True
        self.assertIn("streams", tasks["B1"].pre_stage_unsupported_reason())
        workflow.checkpoints = {tasks["B1"].checkpoint_key(): {"code": 0, "working_dir": self.scratch}}
        self.assertFalse(tasks["B1"].reuse_checkpoint(), "the producer reruns while its consumer must run")
        workflow.checkpoints[tasks["B2"].checkpoint_key()] = {"code": 0, "working_dir": self.scratch}
        self.assertTrue(tasks["B1"].reuse_checkpoint())

    def test_capio_stream_rules(self):
        workflow = Workflow("capio-streams", config=config(self.scratch))
        producer = DagonTask(TaskType.BATCH, "B1", "true")
        consumer = DagonTask(TaskType.BATCH, "B2", "cat workflow:///B1/frames?stream")
        workflow.add_task(producer)
        workflow.add_task(consumer)
        capio = workflow.create_adhoc_filesystem("capio", name="cl", server="capio_server")
        capio.bind(producer)
        capio.bind(consumer)
        workflow.make_dependencies()
        channels = workflow.plan_streams()
        self.assertEqual(capio.start_command[:3], ["capio_server", "-c", capio.generated_config])
        rules = json.loads(Path(capio.generated_config).read_text())
        self.assertEqual(rules["name"], "capio-streams-cl")
        steps = {step["name"]: step for step in rules["IO_Graph"]}
        self.assertEqual(steps["B1"]["streaming"], [{"name": [channels[0].location + "/*"],
                                                    "committed": "on_close", "mode": "no_update"}])
        self.assertEqual(steps["B2"]["input_stream"], [channels[0].location])
        workflow.plan_streams()  # a second run plans again from the configuration-free command
        self.assertEqual(capio.start_command.count("-c"), 1)

    def test_launcher_lines_for_streams_and_beeond_locations(self):
        workflow = streaming_example.build(self.scratch)
        workflow.make_dependencies()
        workflow.plan_streams(prepare=False)
        tasks = {task.name: task for task in workflow.tasks}
        prologue = tasks["B1"].stream_prologue()
        self.assertIn('export DAGON_STREAM_STATE_DIR="$PWD/.dagon/streams"', prologue)
        self.assertIn("DAGON_STREAM_OUT_FRAMES=", prologue)
        self.assertIn("stream close", prologue)
        self.assertIn("trap ", prologue)
        self.assertIn('dagon_close_streams "$code"', tasks["B1"].stream_epilogue())
        self.assertEqual(tasks["A"].stream_prologue() + tasks["A"].stream_epilogue(), "")
        channel = tasks["B1"].stream_outputs["frames"]
        channel.location = "$DAGON_BEEOND/.dagon-streams/r/w/B1/frames"
        self.assertIn('"${DAGON_BEEOND}"', tasks["B1"].stream_prologue())
        spec = dict(channel.spec())
        found = streaming.find_spec("/mnt/beeond/.dagon-streams/r/w/B1/frames",
                                    {"DAGON_BEEOND": "/mnt/beeond",
                                     "DAGON_STREAM_B1_FRAMES_SPEC": json.dumps(spec)})
        self.assertEqual(found["location"], "/mnt/beeond/.dagon-streams/r/w/B1/frames")


if __name__ == "__main__":
    unittest.main()
