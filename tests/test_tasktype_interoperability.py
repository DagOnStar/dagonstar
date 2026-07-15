"""Factory-wide contracts for mixed TaskType workflows.

These tests deliberately avoid live schedulers and services. They verify the
portable DAGonStar contract shared by every backend; backend-specific suites
cover command generation and mocked provider behavior separately.
"""

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from dagon.fair import Agent, Artifact, FairProfile
from dagon.task import DagonTask, TaskType
from tests.helpers import make_workflow


class TaskTypeInteroperabilityTests(unittest.TestCase):
    def _tasks(self):
        reference = "workflow:///producer/output/value.txt"
        with patch("dagon.docker_task.docker.from_env", return_value=None), \
             patch("dagon.kubernetes_task.config.load_kube_config"), \
             patch("dagon.kubernetes_task.client.CoreV1Api"):
            return {
                TaskType.CHECKPOINT: DagonTask(TaskType.CHECKPOINT, "checkpoint", reference),
                TaskType.BATCH: DagonTask(TaskType.BATCH, "batch", "cat " + reference),
                TaskType.SLURM: DagonTask(TaskType.SLURM, "slurm", "cat " + reference),
                TaskType.CLOUD: self._cloud("cloud", "cat " + reference),
                TaskType.DOCKER: DagonTask(TaskType.DOCKER, "docker", "cat " + reference,
                                           image="busybox", pull=False),
                TaskType.KUBERNETES: DagonTask(TaskType.KUBERNETES, "kubernetes", "cat " + reference,
                                               image="busybox"),
                TaskType.APPTAINER: DagonTask(TaskType.APPTAINER, "apptainer", "cat " + reference,
                                              image="busybox.sif"),
                TaskType.NOMAD: DagonTask(TaskType.NOMAD, "nomad", "cat " + reference,
                                          image="busybox"),
                TaskType.LLM: DagonTask(TaskType.LLM, "llm", {"messages": [{"content": reference}]},
                                        provider="mock"),
                TaskType.NATIVE: DagonTask(TaskType.NATIVE, "native", "tests.native_functions:scale_file",
                                           inputs={"input_file": reference, "scale": 1},
                                           outputs={"output_file": "value.txt"}),
                TaskType.WEB: DagonTask(TaskType.WEB, "web", {"method": "POST", "url": "http://example.invalid",
                                         "body": {"text": reference}}),
                TaskType.FAAS: DagonTask(TaskType.FAAS, "faas", provider="mock", function="echo",
                                         inputs={"document": reference}),
            }

    @staticmethod
    def _cloud(name, command):
        from dagon.remote import CloudTask
        with patch.object(CloudTask, "connect", return_value=None, create=True):
            return DagonTask(TaskType.CLOUD, name, command, provider="mock", ssh_username="user",
                             key_options={"key_path": "/tmp/key"}, instance_id="instance")

    def test_every_factory_type_discovers_workflow_reference_in_one_mixed_dag(self):
        workflow = make_workflow("mixed")
        producer = DagonTask(TaskType.BATCH, "producer", "mkdir -p output; echo value > output/value.txt")
        workflow.add_task(producer)
        tasks = self._tasks()
        for task in tasks.values():
            workflow.add_task(task)
        workflow.make_dependencies()
        self.assertEqual(set(tasks), set(TaskType))
        for task_type, task in tasks.items():
            with self.subTest(task_type=task_type):
                self.assertIn(producer, task.prevs)

    def test_every_factory_type_exposes_fair_declarations(self):
        for task_type, task in self._tasks().items():
            with self.subTest(task_type=task_type):
                self.assertIs(task, task.declare_inputs(Artifact("input.dat"))
                                     .declare_outputs(Artifact("output.dat"))
                                     .annotate(task_type=task_type.value))

    def test_fair_recorder_accepts_every_task_type_in_one_run(self):
        with tempfile.TemporaryDirectory() as output_dir:
            workflow = make_workflow("mixed-fair")
            workflow.enable_fair(FairProfile(
                title="Mixed task FAIR contract",
                description="Every registered task type in one provenance run.",
                creators=[Agent(name="DAGonStar tests")],
                license="Apache-2.0",
                output_dir=output_dir,
            ))
            workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                        "mkdir -p output; echo value > output/value.txt"))
            tasks = self._tasks()
            for task in tasks.values():
                workflow.add_task(task)
            workflow.make_dependencies()
            workflow._fire_event("on_workflow_start", workflow)
            for task in tasks.values():
                workflow._fire_event("on_task_start", task)
                workflow._fire_event("on_task_end", task)
            workflow._fire_event("on_workflow_end", workflow)
            run = json.loads(Path(output_dir, "run.json").read_text(encoding="utf-8"))
        self.assertEqual({record["type"] for record in run["tasks"].values()},
                         {type(task).__name__ for task in tasks.values()})

    def test_every_factory_type_reuses_a_successful_local_checkpoint(self):
        for task_type, task in self._tasks().items():
            with self.subTest(task_type=task_type), tempfile.TemporaryDirectory() as completed:
                workflow = make_workflow("resume-" + task_type.value)
                workflow.add_task(task)
                workflow.checkpoints[workflow.name + "." + task.name] = {
                    "working_dir": completed, "code": 0,
                }
                self.assertTrue(task.reuse_checkpoint())
                self.assertTrue(task.fair_checkpoint_reused)

    def test_mixed_tasktype_graph_exports_as_deterministic_cwl(self):
        workflow = make_workflow("mixed-cwl")
        workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                    "mkdir -p output; echo value > output/value.txt"))
        for task in self._tasks().values():
            workflow.add_task(task)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "mixed.cwl")
            workflow.saveAsCWL(target)
            document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(document["cwlVersion"], "v1.2")
        self.assertEqual(len(document["steps"]), len(TaskType) + 1)


if __name__ == "__main__":
    unittest.main()
