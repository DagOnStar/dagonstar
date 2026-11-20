"""``TaskType.VOLUME``: volumes created, shared, released, and destroyed through workflow://.

Everything runs locally: real runs use the out-of-package ``local-directory``
adapter of ``examples/adhoc/custom_adapter.py`` (a real local resource);
built-in providers run under portable emulation or are only planned.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples" / "adhoc"))

from dagon import Status, Workflow  # noqa: E402
from dagon.fair import Agent, FairProfile  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
from dagon import volume as dagon_volume  # noqa: E402
from dagon.volume import ObjectVolumeStore, PosixVolumeStore, VolumeTask, object_key  # noqa: E402
import custom_adapter  # noqa: E402


def config(scratch):
    return {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "8"},
            "slurm": {"partition": ""},
            "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}


class Recorded(custom_adapter.LocalDirectory):
    """Records when the volume starts and stops relative to the tasks."""
    provider = "recorded-volume-test"
    events = []

    def start(self):
        Recorded.events.append(("start", self.name))
        super().start()

    def stop(self):
        Recorded.events.append(("stop", self.name))
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


def record_task_ends(workflow, events):
    workflow.add_listener("on_task_end", lambda task: events.append(("end", task.name)))


class VolumeTestCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp()
        Recorded.events = []

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def workflow(self, name="volumes", **options):
        return Workflow(name, config=config(self.scratch), **options)


class ConstructionTests(VolumeTestCase):
    def test_create_and_destroy_specifications(self):
        create = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz",
                           stage_in={"inputs/data.csv": "workflow:///Prep/data.csv"},
                           options={"frontend": "fuse3", "ranks": 2})
        self.assertIsInstance(create, VolumeTask)
        self.assertEqual(create.command, "dagon-volume create xyz workflow:///Prep/data.csv")
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"results": "workflow:///Abc/xyz/out", "log.txt": "logs/run.log"})
        self.assertEqual(destroy.command, "dagon-volume destroy workflow:///Abc/xyz")
        self.assertEqual(destroy.stage_out, {"results": {"path": "out", "type": "auto"},
                                             "log.txt": {"path": "logs/run.log", "type": "auto"}})
        self.assertEqual(DagonTask(TaskType.VOLUME, "scratch", provider="capio").volume_name, "scratch")

    def test_invalid_specifications_are_refused(self):
        cases = [
            dict(provider="beeond"),
            dict(provider=None),
            dict(provider="dagonfs", stage_in={"../escape": "workflow:///A/x"}),
            dict(provider="dagonfs", stage_in={"x": "workflow:///A/frames?stream"}),
            dict(provider="dagonfs", stage_out={"x": "y"}),
            dict(provider="dagonfs", options={"password": "secret"}),
            dict(provider="dagonfs", options={"environment": {"API_KEY": "secret"}}),
            dict(provider="dagonfs", volume="bad name"),
            dict(provider="dagonfs", unexpected=1),
            dict(provider="dagonfs", action="resize"),
            dict(provider="dagonfs", release="never"),
            dict(action="destroy", volume="xyz"),
            dict(action="destroy", volume="workflow:///Abc/xyz/deeper"),
            dict(action="destroy", volume="workflow:///Abc/xyz", stage_out={"r": "workflow:///Other/xyz/r"}),
            dict(action="destroy", volume="workflow:///Abc/xyz", provider="dagonfs"),
        ]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                DagonTask(TaskType.VOLUME, "V", **options)

    def test_token_variable_names_are_not_credentials(self):
        task = DagonTask(TaskType.VOLUME, "Dyn", provider="dynostore",
                         options={"server": "127.0.0.1:8095", "token_env": "MY_DYNOSTORE_TOKEN"})
        self.assertEqual(task.portable_spec()["options"]["token_env"], "MY_DYNOSTORE_TOKEN")

    def test_volume_scope_is_reserved_for_volume_tasks(self):
        workflow = self.workflow()
        with self.assertRaises(ValueError):
            workflow.create_adhoc_filesystem("dagonfs", name="x", scope="volume")
        workflow.add_task(DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz"))
        filesystem = workflow.adhoc_filesystems["xyz"]
        self.assertEqual((filesystem.scope, filesystem.owner.name), ("volume", "Abc"))
        self.assertEqual(filesystem.metadata()["owner"], "Abc")
        with self.assertRaises(ValueError):
            workflow.add_task(DagonTask(TaskType.VOLUME, "Again", provider="capio", volume="xyz"))

    def test_object_keys_and_location_hooks(self):
        workflow = self.workflow()
        dyno = DagonTask(TaskType.VOLUME, "Dyn", provider="dynostore", volume="objects",
                         options={"server": "127.0.0.1:8095", "catalog": "run"})
        native = DagonTask(TaskType.VOLUME, "Nat", provider="dagonfs", volume="native",
                           options={"frontend": "native", "mountpoint": os.path.join(self.scratch, "n.sock")})
        capio = DagonTask(TaskType.VOLUME, "Cap", provider="capio", volume="capio",
                          options={"directory": os.path.join(self.scratch, "capio dir")})
        for task in (dyno, native, capio):
            workflow.add_task(task)
        key = object_key("objects", "a/b.csv")
        self.assertEqual(key, object_key("objects", "/a/b.csv/"))
        self.assertEqual(dyno.filesystem.volume_location("a/b.csv"), key)
        self.assertEqual(dyno.filesystem.volume_location(""), "dynostore://127.0.0.1:8095/run")
        self.assertEqual(native.filesystem.volume_location("a/b"), "/a/b")
        self.assertEqual(capio.filesystem.volume_reference_text("out/*.dat"),
                         "'%s'/out/*.dat" % os.path.join(self.scratch, "capio dir"))
        completed = subprocess.run([sys.executable, "-m", "dagon.volume", "key", "objects", "a/b.csv"],
                                   capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(completed.stdout.strip(), key)


class DiscoveryTests(VolumeTestCase):
    def build(self, provider="dagonfs", emulate=False, **options):
        workflow = self.workflow(portable_emulation=emulate)
        workflow.add_task(DagonTask(TaskType.BATCH, "Prep", "echo 1 > x.txt"))
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz",
                          stage_in={"in/x.txt": "workflow:///Prep/x.txt"}, **options)
        writer = DagonTask(TaskType.BATCH, "W", "cp workflow:///Abc/xyz/in/x.txt workflow:///Abc/xyz/out.txt")
        reader = DagonTask(TaskType.BATCH, "R", "cat workflow:///Abc/xyz/out.txt workflow:///W/.dagon/stdout.txt")
        for task in (owner, writer, reader):
            workflow.add_task(task)
        return workflow, owner, writer, reader

    def test_references_bind_users_and_count_like_the_scratch_collector(self):
        workflow, owner, writer, reader = self.build()
        workflow.make_dependencies()
        self.assertEqual([task.name for task in owner.prevs], ["Prep"])
        self.assertIn(owner, writer.prevs)
        self.assertIn(owner, reader.prevs)
        self.assertEqual(owner.reference_count, 3)
        self.assertEqual(set(owner.filesystem.tasks), {owner, writer, reader})
        root = owner.filesystem.task_path
        resolved = writer.resolve_volume_references(writer.command)
        self.assertEqual(resolved, "cp '%s'/in/x.txt '%s'/out.txt" % (root, root) if " " in root
                         else "cp %s/in/x.txt %s/out.txt" % (root, root))
        # The plain reference to W's scratch directory is still staged as before.
        self.assertIn("workflow:///W/.dagon/stdout.txt", reader.resolve_volume_references(reader.command))
        self.assertIn("DAGON_ADHOC_XYZ_PATH", writer.adhoc_prologue())

    def test_paths_outside_the_volume_name_are_ordinary_references(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz")
        task = DagonTask(TaskType.BATCH, "T", "cat workflow:///Abc/.dagon/volume_spec.json")
        workflow.add_task(owner)
        workflow.add_task(task)
        workflow.make_dependencies()
        self.assertEqual(task.volume_references, {})
        self.assertNotIn(task, owner.filesystem.tasks)
        self.assertIn(owner, task.prevs)

    def test_volume_tasks_are_not_stream_producers(self):
        workflow = self.workflow()
        workflow.add_task(DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz"))
        workflow.add_task(DagonTask(TaskType.BATCH, "C", "cat workflow:///Abc/xyz/frames?stream"))
        with self.assertRaisesRegex(ValueError, "stream=xyz"):
            workflow.make_dependencies()

    def test_destroy_runs_after_every_user(self):
        workflow, owner, writer, reader = self.build()
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz")
        attached = DagonTask(TaskType.BATCH, "Attached", "test -n \"$DAGON_ADHOC_XYZ_PATH\"")
        workflow.add_task(destroy)
        workflow.add_task(attached)
        owner.attach(attached)
        workflow.make_dependencies()
        self.assertEqual({task.name for task in destroy.prevs}, {"Abc", "W", "R", "Attached"})
        self.assertNotIn(destroy, destroy.explicit_prevs)
        self.assertEqual(owner.extra_users, {attached})
        self.assertEqual(owner.reference_count, 5)

    def test_a_user_after_the_destroy_task_is_refused(self):
        workflow, owner, writer, reader = self.build()
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"r.txt": "out.txt"})
        late = DagonTask(TaskType.BATCH, "Late", "cat workflow:///Del/r.txt workflow:///Abc/xyz/out.txt")
        workflow.add_task(destroy)
        workflow.add_task(late)
        with self.assertRaisesRegex(ValueError, "runs after Del"):
            workflow.make_dependencies()

    def test_two_destroy_tasks_and_unknown_volumes_are_refused(self):
        workflow, owner, writer, reader = self.build()
        workflow.add_task(DagonTask(TaskType.VOLUME, "D1", action="destroy", volume="workflow:///Abc/xyz"))
        workflow.add_task(DagonTask(TaskType.VOLUME, "D2", action="destroy", volume="workflow:///Abc/xyz"))
        with self.assertRaisesRegex(ValueError, "destroyed by both"):
            workflow.make_dependencies()
        other = self.workflow("other")
        other.add_task(DagonTask(TaskType.BATCH, "Abc", "true"))
        other.add_task(DagonTask(TaskType.VOLUME, "D", action="destroy", volume="workflow:///Abc/xyz"))
        with self.assertRaisesRegex(ValueError, "does not name the volume"):
            other.make_dependencies()

    def test_structured_readers_need_a_posix_path(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="capio", volume="xyz")
        native = DagonTask(TaskType.NATIVE, "N", "tests.native_functions:scale_file",
                           inputs={"input_file": "workflow:///Abc/xyz/x.txt", "scale": 1},
                           outputs={"output_file": "y.txt"})
        workflow.add_task(owner)
        workflow.add_task(native)
        with self.assertRaisesRegex(ValueError, "preload access"):
            workflow.make_dependencies()
        # Under portable emulation every volume is a local directory.
        emulated = self.workflow("emulated", portable_emulation=True)
        emulated.add_task(DagonTask(TaskType.VOLUME, "Abc", provider="capio", volume="xyz"))
        emulated.add_task(DagonTask(TaskType.NATIVE, "N", "tests.native_functions:scale_file",
                                    inputs={"input_file": "workflow:///Abc/xyz/x.txt", "scale": 1},
                                    outputs={"output_file": "y.txt"}))
        emulated.make_dependencies()

    def test_command_paths_into_client_and_object_volumes_are_refused(self):
        # Found live: a DAGonFS native volume reference became the host path /results.
        for provider, options in (("dagonfs", {"frontend": "native"}), ("dynostore", {"catalog": "c"})):
            with self.subTest(provider=provider):
                workflow = self.workflow("refused-" + provider)
                workflow.add_task(DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz",
                                            options=options))
                workflow.add_task(DagonTask(TaskType.BATCH, "W", "mkdir -p workflow:///Abc/xyz/results"))
                with self.assertRaisesRegex(ValueError, "no POSIX path"):
                    workflow.make_dependencies()
                # Streams and attached tasks remain available; emulation has a local path.
                allowed = self.workflow("allowed-" + provider)
                owner = DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz", options=options)
                emit = DagonTask(TaskType.BATCH, "Emit", "echo 1")
                read = DagonTask(TaskType.BATCH, "Read", "echo workflow:///Emit/n?stream=xyz")
                for task in (owner, emit, read):
                    allowed.add_task(task)
                allowed.make_dependencies()
                self.assertIn(read, owner.filesystem.tasks)
                emulated = self.workflow("emulated-" + provider, portable_emulation=True)
                emulated.add_task(DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz",
                                            options=options))
                emulated.add_task(DagonTask(TaskType.BATCH, "W", "mkdir -p workflow:///Abc/xyz/results"))
                emulated.make_dependencies()

    def test_volume_users_are_not_pre_staged(self):
        workflow = self.workflow()
        workflow.add_task(DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz"))
        slurm = DagonTask(TaskType.SLURM, "S", "cat workflow:///Abc/xyz/x.txt")
        workflow.add_task(slurm)
        workflow.make_dependencies()
        self.assertIn("volume", slurm.pre_stage_unsupported_reason())

    def test_json_round_trip_keeps_both_actions(self):
        workflow, owner, writer, reader = self.build(export="SHARED_VOLUME", release="end")
        workflow.add_task(DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                                    stage_out={"r": {"path": "out.txt", "type": "file"}}))
        document = json.loads(json.dumps(workflow.as_json()))
        self.assertEqual(document["tasks"]["Abc"]["type"], "volume")
        self.assertNotIn("password", json.dumps(document).lower())
        restored = Workflow("restored", config=config(self.scratch), jsonload=document)
        abc = restored.find_task_by_name(restored.name, "Abc")
        destroy = restored.find_task_by_name(restored.name, "Del")
        self.assertEqual(abc.portable_spec(), owner.portable_spec())
        self.assertEqual(destroy.stage_out, {"r": {"path": "out.txt", "type": "file"}})
        restored.make_dependencies()
        self.assertIn(restored.find_task_by_name(restored.name, "R"), destroy.prevs)

    def test_fair_edges_mark_volume_transfer(self):
        workflow, owner, writer, reader = self.build()
        recorder = workflow.enable_fair(FairProfile(title="Volume", description="Volume edges",
                                                    creators=[Agent(name="tests")], license="Apache-2.0",
                                                    output_dir=os.path.join(self.scratch, "fair")))
        workflow.make_dependencies()
        edges = [edge for edge in recorder.run["dependencies"] if edge["producer"] == "Abc"]
        self.assertTrue(edges)
        self.assertTrue(all(edge["transfer"] == "volume" and edge["volume"] == "xyz" for edge in edges))


class ExecutionTests(VolumeTestCase):
    def test_released_when_the_last_reference_is_gone(self):
        workflow = self.workflow()
        events = Recorded.events
        record_task_ends(workflow, events)
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz")
        first = DagonTask(TaskType.BATCH, "First", "echo 1 > workflow:///Abc/xyz/a.txt")
        second = DagonTask(TaskType.BATCH, "Second", "cat workflow:///Abc/xyz/a.txt > b.txt")
        after = DagonTask(TaskType.BATCH, "After", "cat workflow:///Second/b.txt")
        for task in (owner, first, second, after):
            workflow.add_task(task)
        second.add_dependency_to(first)
        workflow.run()
        self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks))
        self.assertEqual(Path(second.working_dir, "b.txt").read_text().strip(), "1")
        stop = events.index(("stop", "xyz"))
        # Released by the last user's reference cleanup, after the first user ended.
        self.assertLess(events.index(("end", "First")), stop)
        self.assertLess(stop, events.index(("end", "Second")))
        self.assertLess(stop, events.index(("end", "After")), "released before the workflow ended")
        self.assertEqual(owner.released, "no task refers to it")
        self.assertFalse(os.path.exists(owner.filesystem.path))
        checkpoint = workflow.checkpoints["volumes.Abc"]
        self.assertEqual((checkpoint["task_type"], checkpoint["code"], checkpoint["volume"]["released"]),
                         ("volume", 0, "no task refers to it"))

    def test_release_end_keeps_the_volume_until_the_workflow_ends(self):
        workflow = self.workflow()
        record_task_ends(workflow, Recorded.events)
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz", release="end")
        user = DagonTask(TaskType.BATCH, "User", "echo 1 > workflow:///Abc/xyz/a.txt")
        after = DagonTask(TaskType.BATCH, "After", "cat workflow:///User/.dagon/stdout.txt")
        for task in (owner, user, after):
            workflow.add_task(task)
        workflow.run()
        self.assertGreater(Recorded.events.index(("stop", "xyz")), Recorded.events.index(("end", "After")))
        self.assertEqual(owner.released, "workflow ended")

    def test_unreferenced_volume_is_released_after_creation(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz")
        workflow.add_task(owner)
        workflow.run()
        self.assertEqual(Recorded.events, [("start", "xyz"), ("stop", "xyz")])
        self.assertEqual(owner.released, "no task refers to it")

    def test_failed_user_keeps_the_volume_until_the_workflow_ends(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz")
        failing = DagonTask(TaskType.BATCH, "Fail", "cat workflow:///Abc/xyz/missing.txt")
        workflow.add_task(owner)
        workflow.add_task(failing)
        workflow.run()
        self.assertIs(failing.status, Status.FAILED)
        self.assertEqual(owner.released, "workflow ended")
        self.assertFalse(owner.filesystem.started)

    def test_destroy_stages_out_and_releases(self):
        for emulate in (False, True):
            with self.subTest(emulate=emulate):
                Recorded.events = []
                scratch = tempfile.mkdtemp(dir=self.scratch)
                workflow = Workflow("destroy", config=config(scratch), portable_emulation=emulate)
                prep = DagonTask(TaskType.BATCH, "Prep", "mkdir -p data; echo 41 > data/x.txt; echo n > note.txt")
                owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded if not emulate else "hercules",
                                  volume="xyz", options={} if not emulate else {"config": "hercules.conf"},
                                  stage_in={"in/data": "workflow:///Prep/data",
                                            "in/note.txt": {"path": "workflow:///Prep/note.txt", "type": "file"}})
                writer = DagonTask(TaskType.BATCH, "W", "mkdir -p workflow:///Abc/xyz/out ; "
                                   "echo $(( $(cat workflow:///Abc/xyz/in/data/x.txt) + 1 )) > "
                                   "workflow:///Abc/xyz/out/y.txt")
                destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                                    stage_out={"results": {"path": "workflow:///Abc/xyz/out", "type": "directory"},
                                               "note.txt": "in/note.txt"})
                final = DagonTask(TaskType.BATCH, "Final", "cat workflow:///Del/results/y.txt > final.txt")
                for task in (prep, owner, writer, destroy, final):
                    workflow.add_task(task)
                workflow.run()
                self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                                [(task.name, task.status) for task in workflow.tasks])
                self.assertEqual(Path(final.working_dir, "final.txt").read_text().strip(), "42")
                self.assertEqual(Path(destroy.working_dir, "note.txt").read_text().strip(), "n")
                self.assertEqual(owner.released, "destroyed by Del")
                staged = workflow.checkpoints["destroy.Del"]["staged"]
                self.assertEqual(sorted(item["target"] for item in staged), ["note.txt", "results"])
                if emulate:
                    emulated = owner.filesystem.emulated_path()
                    self.assertFalse(os.path.exists(emulated), "an emulated release removes the volume path")
                    self.assertTrue(os.path.isdir(emulated + "-released"))
                else:
                    self.assertEqual(Recorded.events.count(("stop", "xyz")), 1)

    def test_stage_in_failure_releases_the_volume(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz",
                          stage_in={"x": {"path": os.path.join(self.scratch, "absent"), "type": "file"}})
        workflow.add_task(owner)
        workflow.run()
        self.assertIs(owner.status, Status.FAILED)
        self.assertEqual(owner.failure_phase, "staging")
        self.assertEqual(Recorded.events, [("start", "xyz"), ("stop", "xyz")])

    def test_streams_through_a_volume(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="local-directory", volume="ram")
        producer = DagonTask(TaskType.BATCH, "P",
                             'for i in 1 2 3; do echo $i > f$i; '
                             '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" f$i; done')
        consumer = DagonTask(TaskType.BATCH, "C",
                             '"$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///P/frames?stream=ram --into got '
                             '> list.txt')
        for task in (owner, producer, consumer):
            workflow.add_task(task)
        workflow.make_dependencies()
        self.assertEqual(owner.extra_users, {producer, consumer})
        self.assertEqual(owner.reference_count, 2)
        workflow.run()
        self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                        [(task.name, task.status) for task in workflow.tasks])
        self.assertEqual(sorted(os.listdir(os.path.join(consumer.working_dir, "got"))), ["f1", "f2", "f3"])
        self.assertIn(producer, consumer.stream_prevs)
        self.assertEqual(owner.extra_users, set())
        self.assertEqual(owner.released, "no task refers to it")
        self.assertEqual(consumer.stream_inputs[0].filesystem, owner.filesystem)

    @unittest.skipIf(sys.platform == "win32", "directory links need privileges on some Windows hosts")
    def test_structured_tasks_read_through_the_scratch_link(self):
        workflow = self.workflow(portable_emulation=True)
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz")
        writer = DagonTask(TaskType.BATCH, "W", "echo 3 > workflow:///Abc/xyz/x.txt")
        native = DagonTask(TaskType.NATIVE, "N", "tests.native_functions:scale_file",
                           inputs={"input_file": "workflow:///Abc/xyz/x.txt", "scale": 2},
                           outputs={"output_file": "y.txt"})
        for task in (owner, writer, native):
            workflow.add_task(task)
        native.add_dependency_to(writer)
        workflow.run()
        self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                        [(task.name, task.status) for task in workflow.tasks])
        self.assertTrue(os.path.islink(os.path.join(owner.working_dir, "xyz")))
        self.assertTrue(Path(native.working_dir, "outputs", "y.txt").is_file())

    def test_staging_helper_receives_the_preload_environment(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Cap", provider="capio", volume="capio",
                          options={"library": "/opt/capio/libcapio_posix.so"})
        workflow.add_task(owner)
        environment = owner._environment(owner.filesystem)
        self.assertTrue(environment["LD_PRELOAD"].startswith("/opt/capio/libcapio_posix.so"))
        self.assertEqual(environment["CAPIO_APP_NAME"], "Cap")
        spec = owner._helper_spec(owner.filesystem, [])
        self.assertEqual((spec["access"], spec["location"]), ("preload", owner.filesystem.directory))
        dyno = DagonTask(TaskType.VOLUME, "Dyn", provider="dynostore", volume="objects",
                         options={"server": "127.0.0.1:8095", "catalog": "run", "token_env": "DYNO_TOKEN_X"})
        workflow.add_task(dyno)
        with mock.patch.dict(os.environ, {"DYNO_TOKEN_X": "very-secret-value"}):
            spec = dyno._helper_spec(dyno.filesystem, [])
            text = json.dumps(spec) + json.dumps(dyno.portable_spec())
        self.assertIn("DYNO_TOKEN_X", text)
        self.assertNotIn("very-secret-value", text)
        self.assertEqual(spec["access"], "object")


class CheckpointTests(VolumeTestCase):
    def build(self, checkpoint_file):
        workflow = Workflow("resume", config=config(self.scratch), checkpoint_file=checkpoint_file)
        owner = DagonTask(TaskType.VOLUME, "Abc", provider=Recorded, volume="xyz")
        user = DagonTask(TaskType.BATCH, "User", "echo 1 > workflow:///Abc/xyz/a.txt")
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"a.txt": "a.txt"})
        for task in (owner, user, destroy):
            workflow.add_task(task)
        return workflow, owner, user, destroy

    def test_completed_volume_workflow_resumes_without_starting_the_volume(self):
        checkpoint_file = os.path.join(self.scratch, "checkpoint.json")
        workflow, owner, user, destroy = self.build(checkpoint_file)
        workflow.run()
        self.assertEqual(Recorded.events.count(("start", "xyz")), 1)
        Recorded.events = []
        again, owner, user, destroy = self.build(checkpoint_file)
        again.run(checkpoint_file)
        self.assertTrue(all(task.status is Status.FINISHED for task in again.tasks))
        self.assertEqual(Recorded.events, [], "nothing needs the volume, so it is not started again")
        self.assertTrue(owner.fair_checkpoint_reused and destroy.fair_checkpoint_reused)

    def test_a_user_that_must_run_again_recreates_the_volume(self):
        checkpoint_file = os.path.join(self.scratch, "checkpoint.json")
        workflow, owner, user, destroy = self.build(checkpoint_file)
        workflow.run()
        record = json.loads(Path(checkpoint_file).read_text(encoding="utf-8"))
        record["resume.User"]["code"] = 1
        Path(checkpoint_file).write_text(json.dumps(record), encoding="utf-8")
        Recorded.events = []
        again, owner, user, destroy = self.build(checkpoint_file)
        again.run(checkpoint_file)
        self.assertTrue(all(task.status is Status.FINISHED for task in again.tasks))
        self.assertEqual(Recorded.events.count(("start", "xyz")), 1)
        self.assertFalse(owner.fair_checkpoint_reused)

    def test_destroy_checkpoint_verifies_staged_content(self):
        checkpoint_file = os.path.join(self.scratch, "checkpoint.json")
        workflow, owner, user, destroy = self.build(checkpoint_file)
        workflow.run()
        Path(destroy.working_dir, "a.txt").write_text("changed\n", encoding="utf-8")
        again, owner, user, destroy = self.build(checkpoint_file)
        again.checkpoints = json.loads(Path(checkpoint_file).read_text(encoding="utf-8"))
        self.assertFalse(destroy.reuse_checkpoint())

    def test_a_bare_successful_directory_is_not_reused(self):
        workflow = self.workflow()
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz")
        workflow.add_task(owner)
        workflow.checkpoints[owner.checkpoint_key()] = {"working_dir": self.scratch, "code": 0}
        self.assertFalse(owner.reuse_checkpoint())


class StoreTests(VolumeTestCase):
    def tree(self):
        source = Path(self.scratch, "source")
        (source / "sub").mkdir(parents=True)
        (source / "a.txt").write_text("a", encoding="utf-8")
        (source / "sub" / "b.txt").write_text("b", encoding="utf-8")
        return source

    def test_posix_store_round_trip(self):
        source = self.tree()
        store = PosixVolumeStore(os.path.join(self.scratch, "volume"))
        store.put_tree(str(source), "in/tree")
        store.put_file(str(source / "a.txt"), "single/a.txt")
        store.get("in/tree", os.path.join(self.scratch, "back"))
        store.get("single/a.txt", os.path.join(self.scratch, "back-a.txt"))
        self.assertEqual(Path(self.scratch, "back", "sub", "b.txt").read_text(), "b")
        self.assertEqual(Path(self.scratch, "back-a.txt").read_text(), "a")

    def test_object_store_round_trip_with_manifest(self):
        source = self.tree()
        objects = MemoryObjects()
        store = ObjectVolumeStore(objects, "objects")
        store.put_tree(str(source), "in")
        store.put_file(str(source / "a.txt"), "single.txt")
        self.assertIn(object_key("objects", "in/sub/b.txt"), objects.objects)
        store.get("in", os.path.join(self.scratch, "back"))
        store.get("single.txt", os.path.join(self.scratch, "single.txt"))
        self.assertEqual(Path(self.scratch, "back", "sub", "b.txt").read_text(), "b")
        self.assertEqual(Path(self.scratch, "single.txt").read_text(), "a")

    def test_helper_reports_digests(self):
        source = self.tree()
        spec = {"v": 1, "access": "posix", "location": os.path.join(self.scratch, "volume"),
                "operations": [{"op": "put", "source": str(source), "target": "t"},
                               {"op": "get", "source": "t/sub", "target": os.path.join(self.scratch, "out")}]}
        report = dagon_volume.run_operations(spec)
        self.assertEqual([(item["op"], item["type"]) for item in report], [("put", "directory"), ("get", "directory")])
        with self.assertRaises(ValueError):
            dagon_volume.run_operations(dict(spec, operations=[{"op": "put", "source": str(source),
                                                                "target": "../x"}]))


class CwlTests(VolumeTestCase):
    def build(self, emulate):
        workflow = self.workflow("volume-cwl", portable_emulation=emulate)
        prep = DagonTask(TaskType.BATCH, "Prep", "mkdir -p data; echo 41 > data/x.txt")
        owner = DagonTask(TaskType.VOLUME, "Abc", provider="dagonfs", volume="xyz",
                          stage_in={"in/x.txt": {"path": "workflow:///Prep/data/x.txt", "type": "file"}})
        reader = DagonTask(TaskType.BATCH, "R", "cat workflow:///Abc/xyz/in/x.txt > copy.txt")
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"x.txt": {"path": "in/x.txt", "type": "file"}})
        final = DagonTask(TaskType.BATCH, "Final", "cat workflow:///Del/x.txt")
        for task in (prep, owner, reader, destroy, final):
            workflow.add_task(task)
        return workflow

    def export(self, emulate):
        target = Path(self.scratch, "volume-%s.cwl" % emulate)
        self.build(emulate).saveAsCWL(target)
        first = target.read_text(encoding="utf-8")
        self.build(emulate).saveAsCWL(target)
        self.assertEqual(first, target.read_text(encoding="utf-8"), "deterministic")
        return target, json.loads(first)

    def test_volume_steps_materialize_the_volume(self):
        target, document = self.export(False)
        create, destroy = document["steps"]["Abc"], document["steps"]["Del"]
        self.assertEqual(create["run"]["hints"]["dagon:Volume"]["action"], "create")
        self.assertEqual(create["run"]["outputs"]["volume"]["outputBinding"]["glob"], "xyz")
        self.assertEqual(create["in"]["in_0"], "Prep/file_data_x_txt")
        self.assertEqual(document["steps"]["Prep"]["run"]["outputs"]["file_data_x_txt"]["type"], "File")
        self.assertEqual(destroy["in"]["volume"], "Abc/volume")
        self.assertIn("after_R", destroy["in"])
        self.assertEqual(destroy["run"]["outputs"]["staged_x_txt"]["type"], "File")
        self.assertIn("dagon", document["$namespaces"])
        if shutil.which("cwltool"):
            subprocess.run(["cwltool", "--validate", str(target)], check=True, capture_output=True, text=True)

    def test_portable_export_runs_with_cwltool(self):
        target, document = self.export(True)
        self.assertNotIn("workflow://", json.dumps({key: step for key, step in document["steps"].items()}))
        self.assertIn("task_dir", document["steps"]["Abc"]["out"])
        if not shutil.which("cwltool"):
            self.skipTest("cwltool is not installed")
        output = Path(self.scratch, "out")
        completed = subprocess.run(["cwltool", "--no-container", "--outdir", str(output), str(target)],
                                   capture_output=True, text=True, cwd=self.scratch)
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
