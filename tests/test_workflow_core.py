import unittest
import time
import tempfile
import threading

import dagon
from dagon.task import DagonTask, TaskType

from tests.helpers import make_workflow, minimal_config


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

    def test_make_dependencies_rebuilds_graph_from_current_commands(self):
        workflow = make_workflow("Rebuild")
        task_a = DagonTask(TaskType.BATCH, "A", "echo A")
        task_b = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/result.txt")

        workflow.add_task(task_a)
        workflow.add_task(task_b)
        workflow.make_dependencies()

        task_b.command = "echo independent"
        workflow.make_dependencies()

        self.assertEqual(task_a.nexts, [])
        self.assertEqual(task_b.prevs, [])
        self.assertEqual(task_a.reference_count, 0)

    def test_transversal_references_resolve_across_loaded_workflows(self):
        producer = make_workflow("Producer")
        consumer = make_workflow("Consumer")
        task_a = DagonTask(TaskType.BATCH, "A", "echo A")
        task_b = DagonTask(TaskType.BATCH, "B", "cat workflow://Producer/A/out.txt")
        dag_tps = type("DagTps", (), {"workflows": [producer, consumer]})()

        producer.add_task(task_a)
        consumer.add_task(task_b)
        consumer.set_dag_tps(dag_tps)
        consumer.make_dependencies()

        self.assertEqual(task_a.nexts, [])
        self.assertIn(task_a, task_b.prevs)
        self.assertEqual(task_a.reference_count, 1)

    def test_unknown_reference_requires_api_service(self):
        workflow = make_workflow("Offline")
        task = DagonTask(TaskType.BATCH, "NeedsExternal", "cat workflow://Other/Missing/out.txt")

        workflow.add_task(task)

        with self.assertRaisesRegex(ConnectionError, "Dagon service is not available"):
            workflow.make_dependencies()

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

    def test_load_json_recreates_task_instances(self):
        payload = {
            "name": "Loaded",
            "id": 42,
            "tasks": {
                "A": {
                    "name": "A",
                    "command": "echo A",
                    "type": "batch",
                },
            },
        }

        workflow = dagon.Workflow("Initial", config=minimal_config(), jsonload=payload)

        self.assertEqual(workflow.name, "Loaded")
        self.assertEqual(workflow.workflow_id, 42)
        self.assertEqual(len(workflow.tasks), 1)
        self.assertEqual(workflow.tasks[0].command, "echo A")
        self.assertIs(workflow.tasks[0].workflow, workflow)

    def test_launch_wait_and_lifecycle_events(self):
        config = minimal_config()
        with tempfile.TemporaryDirectory() as scratch_dir:
            config["batch"]["scratch_dir_base"] = scratch_dir
            workflow = dagon.Workflow("Async", config=config)
            task = DagonTask(TaskType.BATCH, "A", "echo asynchronous")
            workflow.add_task(task)

            events = []
            workflow.on_workflow_start += lambda subject: events.append(("workflow_start", subject))
            workflow.on_workflow_end += lambda subject: events.append(("workflow_end", subject))
            workflow.on_task_start += lambda subject: events.append(("task_start", subject))
            workflow.on_task_wait += lambda subject: events.append(("task_wait", subject))
            workflow.on_task_staging_in_start += lambda subject: events.append(("staging_in_start", subject))
            workflow.on_task_staging_in_end += lambda subject: events.append(("staging_in_end", subject))
            workflow.on_task_execute_start += lambda subject: events.append(("execute_start", subject))
            workflow.on_task_staging_out_start += lambda subject: events.append(("staging_out_start", subject))
            workflow.on_task_staging_out_end += lambda subject: events.append(("staging_out_end", subject))
            workflow.on_task_end += lambda subject: events.append(("task_end", subject))

            started = time.monotonic()
            thread = workflow.launch()
            self.assertIsInstance(thread, threading.Thread)
            self.assertLess(time.monotonic() - started, 1)
            self.assertTrue(workflow.wait(timeout=10))

            self.assertTrue(workflow._dependencies_made)
            self.assertEqual(task.status, dagon.Status.FINISHED)
            self.assertEqual(
                [name for name, _ in events],
                [
                    "workflow_start", "task_start", "task_wait", "staging_in_start",
                    "staging_in_end", "execute_start", "staging_out_start",
                    "staging_out_end", "task_end", "workflow_end",
                ],
            )
            self.assertTrue(all(subject is task for name, subject in events[1:-1]))
            self.assertIs(events[0][1], workflow)
            self.assertIs(events[-1][1], workflow)


if __name__ == "__main__":
    unittest.main()
