"""Portable emulation and live staging end a ``workflow://`` reference alike.

Both follow the whitespace boundary rule of ``docs/the_workflow_schema.md``:
a reference ends at the next space or at the end of the command, never at a
shell character such as ``)``.  The parsing tests execute nothing; the
emulation tests run local ``bash`` commands in a temporary directory only.
"""

import os
import tempfile
import unittest

from dagon import Workflow
from dagon.platform_support import shell_path
from dagon.task import DagonTask, TaskType

from tests.helpers import make_workflow, minimal_config


class ReferenceBoundaryTests(unittest.TestCase):
    def make_tasks(self, command):
        workflow = make_workflow("Boundary")
        producer = DagonTask(TaskType.BATCH, "A", "echo a > x.txt")
        consumer = DagonTask(TaskType.BATCH, "B", command)
        workflow.add_task(producer)
        workflow.add_task(consumer)
        workflow.make_dependencies()
        scratch = tempfile.mkdtemp()
        producer.working_dir = scratch + "/A"
        consumer.working_dir = scratch + "/B"
        return producer, consumer

    def live_and_portable(self, command):
        producer, consumer = self.make_tasks(command)
        _, inputs, _ = consumer.build_stage_plan(command)
        portable, missing = consumer.resolve_portable_references()
        return producer, inputs, portable, missing

    def test_shell_character_does_not_end_a_reference(self):
        producer, inputs, portable, missing = self.live_and_portable(
            "for i in $(cat workflow:///A/x.txt); do echo $i; done")

        self.assertEqual([item.local_path for item in inputs], ["/x.txt);"])
        self.assertEqual([item.reference for item in inputs], ["workflow:///A/x.txt);"])
        # Emulation ends the reference at the same character and reports it,
        # instead of silently reading the producer's x.txt.
        self.assertEqual(missing, ["workflow:///A/x.txt);"])
        self.assertNotIn("workflow://", portable)

    def test_a_space_ends_a_reference_in_both_paths(self):
        producer, inputs, portable, missing = self.live_and_portable(
            "for i in $(cat workflow:///A/x.txt ); do echo $i; done")

        self.assertEqual([item.local_path for item in inputs], ["/x.txt"])
        self.assertEqual(missing, ["workflow:///A/x.txt"])  # the producer has not run
        self.assertEqual(portable, "for i in $(cat %s/x.txt ); do echo $i; done" % shell_path(producer.working_dir))

    def test_reference_at_end_of_command(self):
        producer, inputs, portable, _ = self.live_and_portable("cat workflow:///A/x.txt")

        self.assertEqual([item.local_path for item in inputs], ["/x.txt"])
        self.assertEqual(portable, "cat %s/x.txt" % shell_path(producer.working_dir))


class PortableReferenceBoundaryTests(unittest.TestCase):
    def run_workflow(self, command):
        with tempfile.TemporaryDirectory() as scratch:
            config = minimal_config()
            config["batch"]["scratch_dir_base"] = scratch
            workflow = Workflow("Boundary", config=config, portable_emulation=True)
            producer = DagonTask(TaskType.BATCH, "A", "printf '1\\n2\\n' > ids.txt")
            consumer = DagonTask(TaskType.BATCH, "B", command)
            workflow.add_task(producer)
            workflow.add_task(consumer)
            workflow.make_dependencies()
            workflow.run()
            output = None
            if consumer.working_dir and os.path.isfile(os.path.join(consumer.working_dir, "out.txt")):
                with open(os.path.join(consumer.working_dir, "out.txt")) as stream:
                    output = stream.read()
            return producer.status.name, consumer.status.name, output

    def test_emulation_rejects_a_reference_ended_by_a_shell_character(self):
        producer, consumer, output = self.run_workflow(
            "for i in $(cat workflow:///A/ids.txt); do echo $i >> out.txt; done")

        self.assertEqual(producer, "FINISHED")
        self.assertEqual(consumer, "FAILED")
        self.assertIsNone(output)

    def test_emulation_accepts_the_reference_followed_by_a_space(self):
        producer, consumer, output = self.run_workflow(
            "for i in $(cat workflow:///A/ids.txt ); do echo $i >> out.txt; done")

        self.assertEqual((producer, consumer), ("FINISHED", "FINISHED"))
        self.assertEqual(output, "1\n2\n")


if __name__ == "__main__":
    unittest.main()
