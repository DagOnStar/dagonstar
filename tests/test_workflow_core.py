import unittest

import dagon
from dagon.task import DagonTask, TaskType

from tests.helpers import make_workflow


class WorkflowCoreTests(unittest.TestCase):
    def test_workflow_uses_safe_defaults_for_optional_sections(self):
        workflow = dagon.Workflow(
            "Defaults",
            config={
                "batch": {
                    "scratch_dir_base": "/tmp",
                    "run_base": "",
                    "threads": "1",
                },
                "slurm": {
                    "partition": "",
                },
            },
        )

        self.assertEqual(workflow.ftpAtt["host"], "localhost")
        self.assertEqual(workflow.ftpAtt["user"], "anonymous")
        self.assertEqual(workflow.local_path, "/tmp")
        self.assertFalse(workflow.is_api_available)

    def test_dataflow_references_create_dependencies(self):
        workflow = make_workflow("DataFlow")
        task_a = DagonTask(TaskType.BATCH, "A", "mkdir -p output; echo ok > output/result.txt")
        task_b = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/result.txt")

        workflow.add_task(task_a)
        workflow.add_task(task_b)
        workflow.make_dependencies()

        self.assertIn(task_b, task_a.nexts)
        self.assertIn(task_a, task_b.prevs)
        self.assertEqual(task_a.reference_count, 1)

    def test_explicit_cycle_is_rejected(self):
        workflow = make_workflow("Cycle")
        task_a = DagonTask(TaskType.BATCH, "A", "echo A")
        task_b = DagonTask(TaskType.BATCH, "B", "echo B")

        workflow.add_task(task_a)
        workflow.add_task(task_b)
        task_b.add_dependency_to(task_a)
        task_a.add_dependency_to(task_b)

        with self.assertRaisesRegex(Exception, "cycle"):
            workflow.Validate_WF()

    def test_workflow_json_serializes_tasks_and_host(self):
        workflow = make_workflow("Serializable")
        task = DagonTask(TaskType.BATCH, "A", "echo A")
        workflow.add_task(task)

        payload = workflow.as_json()

        self.assertEqual(payload["name"], "Serializable")
        self.assertEqual(payload["host"], "localhost")
        self.assertIn("A", payload["tasks"])
        self.assertEqual(payload["tasks"]["A"]["status"], dagon.Status.READY.name)


if __name__ == "__main__":
    unittest.main()
