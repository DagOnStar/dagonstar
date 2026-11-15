"""Explicit add_dependency_to edges survive make_dependencies(), run(), and JSON."""
import json
import tempfile
import unittest
from pathlib import Path

from dagon import Workflow
from dagon.platform_support import shell_path
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config


def workflow(name, scratch):
    config = minimal_config()
    config["batch"]["scratch_dir_base"] = scratch
    return Workflow(name, config=config)


def names(tasks):
    return [task.name for task in tasks]


class ExplicitDependencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.scratch = directory.name

    def test_edge_added_before_run_is_kept_and_orders_execution(self):
        wf = workflow("ExplicitRun", self.scratch)
        marker = shell_path(str(Path(self.scratch, "marker.txt")))
        writer = DagonTask(TaskType.BATCH, "writer", "sleep 1; echo written > %s" % marker)
        reader = DagonTask(TaskType.BATCH, "reader", "cat %s > copy.txt" % marker)
        wf.add_task(writer)
        wf.add_task(reader)
        reader.add_dependency_to(writer)  # before make_dependencies(); run() calls it
        wf.run()
        self.assertEqual(names(reader.prevs), ["writer"])
        self.assertEqual(names(writer.nexts), ["reader"])
        self.assertEqual(Path(reader.working_dir, "copy.txt").read_text().strip(), "written")

    def test_rebuilding_keeps_explicit_and_discovered_edges_without_duplicates(self):
        wf = workflow("ExplicitRebuild", self.scratch)
        first = DagonTask(TaskType.BATCH, "first", "echo 1 > one.txt")
        second = DagonTask(TaskType.BATCH, "second", "cat workflow:///first/one.txt > two.txt")
        third = DagonTask(TaskType.BATCH, "third", "true")
        for task in (first, second, third):
            wf.add_task(task)
        second.add_dependency_to(first)  # the same edge is also discovered
        third.add_dependency_to(second)
        for _ in range(3):
            wf.make_dependencies()
            self.assertEqual(names(second.prevs), ["first"])
            self.assertEqual(names(first.nexts), ["second"])
            self.assertEqual(names(third.prevs), ["second"])
            # Reference counts come from workflow:// references only.
            self.assertEqual(first.reference_count, 1)
            self.assertEqual(second.reference_count, 0)
        self.assertEqual(names(second.explicit_prevs), ["first"])
        self.assertEqual(third.explicit_prevs, [second])

    def test_discovered_edges_are_not_recorded_as_explicit(self):
        wf = workflow("Discovered", self.scratch)
        first = DagonTask(TaskType.BATCH, "first", "echo 1 > one.txt")
        second = DagonTask(TaskType.BATCH, "second", "cat workflow:///first/one.txt > two.txt")
        wf.add_task(first)
        wf.add_task(second)
        wf.make_dependencies()
        self.assertEqual(names(second.prevs), ["first"])
        self.assertEqual(second.explicit_prevs, [])

    def test_removed_explicit_edge_stays_removed(self):
        wf = workflow("Removed", self.scratch)
        first = DagonTask(TaskType.BATCH, "first", "true")
        second = DagonTask(TaskType.BATCH, "second", "true")
        wf.add_task(first)
        wf.add_task(second)
        second.add_dependency_to(first)
        second.remove_dependency_to(first)
        wf.make_dependencies()
        self.assertEqual(second.prevs, [])
        self.assertEqual(first.nexts, [])

    def test_explicit_cycle_is_still_rejected(self):
        wf = workflow("Cycle", self.scratch)
        first = DagonTask(TaskType.BATCH, "first", "true")
        second = DagonTask(TaskType.BATCH, "second", "true")
        wf.add_task(first)
        wf.add_task(second)
        second.add_dependency_to(first)
        first.add_dependency_to(second)
        with self.assertRaises(Exception):
            wf.make_dependencies()


class ExplicitDependencyJsonTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.scratch = directory.name

    def restore(self, document):
        config = minimal_config()
        config["batch"]["scratch_dir_base"] = self.scratch
        return Workflow("placeholder", config=config, jsonload=json.loads(json.dumps(document)))

    @staticmethod
    def task(workflow, name):
        return next(task for task in workflow.tasks if task.name == name)

    def test_json_round_trip_keeps_explicit_edges(self):
        source = workflow("Source", self.scratch)
        a = DagonTask(TaskType.BATCH, "a", "true")
        b = DagonTask(TaskType.BATCH, "b", "true")
        source.add_task(a)
        source.add_task(b)
        b.add_dependency_to(a)
        document = source.as_json()
        self.assertEqual(document["tasks"]["b"]["explicit_prevs"], ["a"])
        restored = self.restore(document)
        restored_b = self.task(restored, "b")
        self.assertEqual(names(restored_b.prevs), ["a"])
        self.assertEqual(names(restored_b.explicit_prevs), ["a"])
        restored.make_dependencies()
        self.assertEqual(names(restored_b.prevs), ["a"])
        self.assertEqual(names(self.task(restored, "a").nexts), ["b"])
        # A second round trip is stable.
        self.assertEqual(restored.as_json()["tasks"]["b"]["explicit_prevs"], ["a"])

    def test_restored_explicit_edge_orders_execution(self):
        source = workflow("SourceRun", self.scratch)
        marker = shell_path(str(Path(self.scratch, "marker.txt")))
        writer = DagonTask(TaskType.BATCH, "writer", "sleep 1; echo written > %s" % marker)
        reader = DagonTask(TaskType.BATCH, "reader", "cat %s > copy.txt" % marker)
        source.add_task(writer)
        source.add_task(reader)
        reader.add_dependency_to(writer)
        restored = self.restore(source.as_json())
        restored.run()
        restored_reader = self.task(restored, "reader")
        self.assertEqual(Path(restored_reader.working_dir, "copy.txt").read_text().strip(), "written")

    def test_discovered_edges_are_serialized_but_not_as_explicit(self):
        source = workflow("SourceDiscovered", self.scratch)
        first = DagonTask(TaskType.BATCH, "first", "echo 1 > one.txt")
        second = DagonTask(TaskType.BATCH, "second", "cat workflow:///first/one.txt > two.txt")
        source.add_task(first)
        source.add_task(second)
        source.make_dependencies()
        document = source.as_json()
        self.assertEqual(document["tasks"]["second"]["prevs"], ["first"])
        self.assertEqual(document["tasks"]["second"]["explicit_prevs"], [])
        restored = self.restore(document)
        self.assertEqual(self.task(restored, "second").prevs, [])
        restored.make_dependencies()
        restored_second = self.task(restored, "second")
        self.assertEqual(names(restored_second.prevs), ["first"])
        self.assertEqual(restored_second.explicit_prevs, [])

    def test_legacy_json_restores_same_workflow_prevs_only(self):
        document = {"name": "Legacy", "id": 1, "tasks": {
            "A": {"name": "A", "command": "true", "type": "batch", "prevs": []},
            # "X" belongs to another workflow (a cross-workflow reference).
            "B": {"name": "B", "command": "true", "type": "batch", "prevs": ["A", "X"]},
        }}
        restored = self.restore(document)
        self.assertEqual(names(self.task(restored, "B").prevs), ["A"])
        restored.make_dependencies()
        self.assertEqual(names(self.task(restored, "B").prevs), ["A"])

    def test_unknown_explicit_dependency_is_rejected(self):
        document = {"name": "Unknown", "id": 1, "tasks": {
            "B": {"name": "B", "command": "true", "type": "batch", "explicit_prevs": ["missing"]},
        }}
        with self.assertRaisesRegex(ValueError, "unknown tasks: missing"):
            self.restore(document)

    def test_self_dependency_is_rejected(self):
        document = {"name": "Self", "id": 1, "tasks": {
            "A": {"name": "A", "command": "true", "type": "batch", "explicit_prevs": ["A"]},
        }}
        with self.assertRaisesRegex(ValueError, "itself"):
            self.restore(document)

    def test_explicit_cycle_in_json_is_rejected(self):
        document = {"name": "Cycle", "id": 1, "tasks": {
            "A": {"name": "A", "command": "true", "type": "batch", "explicit_prevs": ["B"]},
            "B": {"name": "B", "command": "true", "type": "batch", "explicit_prevs": ["A"]},
        }}
        with self.assertRaisesRegex(Exception, "cycle"):
            self.restore(document)

    def test_mixed_task_types_keep_explicit_edges_through_json(self):
        source = workflow("Mixed", self.scratch)
        producer = DagonTask(TaskType.BATCH, "producer", "true")
        source.add_task(producer)
        consumers = [
            DagonTask(TaskType.NATIVE, "native", "tests.native_functions:scale_file",
                      inputs={"input_file": "value.txt", "scale": 1}, outputs={"output_file": "value.txt"}),
            DagonTask(TaskType.WEB, "web", {"method": "GET", "url": "http://example.invalid"}),
            DagonTask(TaskType.FAAS, "faas", provider="mock", function="echo", inputs={"document": "x"}),
            DagonTask(TaskType.IOT, "iot", operation="observe", provider="mock",
                      request={"events": [{"source": "sensor"}]}, completion={"mode": "first_event"},
                      outputs={"observations": "outputs/observations.json"}),
            DagonTask(TaskType.LLM, "llm", {"messages": [{"content": "hello"}]}, provider="mock"),
        ]
        for consumer in consumers:
            source.add_task(consumer)
            consumer.add_dependency_to(producer)
        restored = self.restore(source.as_json())
        restored.make_dependencies()
        for consumer in consumers:
            with self.subTest(task=consumer.name):
                restored_consumer = self.task(restored, consumer.name)
                self.assertEqual(type(restored_consumer), type(consumer))
                self.assertEqual(names(restored_consumer.prevs), ["producer"])


if __name__ == "__main__":
    unittest.main()
