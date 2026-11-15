"""Explicit add_dependency_to edges survive Workflow.make_dependencies() and run()."""
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


if __name__ == "__main__":
    unittest.main()
