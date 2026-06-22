import json
import os
import tempfile
import unittest

from dagon.fair import AccessPolicy, Agent, Artifact, FairProfile, FairValidationError
from dagon.task import DagonTask, TaskType
from tests.helpers import make_workflow


class FairTests(unittest.TestCase):
    def profile(self, output_dir, strict=False):
        return FairProfile(title="Test FAIR workflow", description="local metadata test",
                           creators=[Agent(name="Test Lab")], license="Apache-2.0",
                           access_policy=AccessPolicy(), output_dir=output_dir, strict=strict)

    def test_declarations_are_chainable_without_fair_mode(self):
        task = DagonTask(TaskType.BATCH, "A", "echo hello")
        self.assertIs(task, task.declare_inputs(Artifact("in.txt")).declare_outputs(Artifact("out.txt")).annotate(description="test"))
        self.assertEqual(task.fair_annotations["description"], "test")

    def test_strict_profile_rejects_missing_core_metadata(self):
        workflow = make_workflow("Strict")
        with self.assertRaises(FairValidationError):
            workflow.enable_fair(FairProfile(title="", description="", creators=[], license="", strict=True))

    def test_local_dataflow_writes_standard_exports_and_provenance(self):
        with tempfile.TemporaryDirectory() as output_dir:
            workflow = make_workflow("FairLocal")
            recorder = workflow.enable_fair(self.profile(output_dir))
            first = DagonTask(TaskType.BATCH, "A", "mkdir -p output; echo hello > output/message.txt").declare_outputs(Artifact("output/message.txt", media_type="text/plain"))
            second = DagonTask(TaskType.BATCH, "B", "cat workflow:///A/output/message.txt > copied-message.txt").declare_outputs(Artifact("copied-message.txt", media_type="text/plain"))
            workflow.add_task(first); workflow.add_task(second); workflow.run()
            for name in ("run.json", "ro-crate-metadata.json", "prov.json", "fairness-report.json", "report.md", "checksums.sha256"):
                self.assertTrue(os.path.exists(os.path.join(output_dir, name)), name)
            with open(os.path.join(output_dir, "run.json"), encoding="utf-8") as source:
                run = json.load(source)
            self.assertEqual(len(run["artifacts"]), 2)
            self.assertTrue(all(item["checksum"].startswith("sha256:") for item in run["artifacts"]))
            with open(os.path.join(output_dir, "prov.json"), encoding="utf-8") as source:
                prov = json.load(source)
            self.assertTrue(prov["wasInformedBy"])
            with open(os.path.join(output_dir, "ro-crate-metadata.json"), encoding="utf-8") as source:
                crate = json.load(source)
            self.assertTrue(any(entity.get("@id") == "./" for entity in crate["@graph"]))
            self.assertEqual(recorder.run["environment"]["variables"], {})

    def test_missing_output_is_warning_or_strict_error(self):
        with tempfile.TemporaryDirectory() as output_dir:
            workflow = make_workflow("Missing")
            workflow.enable_fair(self.profile(output_dir))
            workflow.add_task(DagonTask(TaskType.BATCH, "A", "echo hello").declare_outputs(Artifact("absent.txt")))
            workflow.run()
            with open(os.path.join(output_dir, "fairness-report.json"), encoding="utf-8") as source:
                report = json.load(source)
            self.assertIn("Declared output missing: absent.txt", report["warnings"])

    def test_missing_output_is_an_error_in_strict_report(self):
        with tempfile.TemporaryDirectory() as output_dir:
            workflow = make_workflow("MissingStrict")
            workflow.enable_fair(self.profile(output_dir, strict=True))
            workflow.add_task(DagonTask(TaskType.BATCH, "A", "echo hello").declare_outputs(Artifact("absent.txt")))
            workflow.run()
            with open(os.path.join(output_dir, "fairness-report.json"), encoding="utf-8") as source:
                report = json.load(source)
            self.assertIn("Declared output missing: absent.txt", report["errors"])

    def test_checkpoint_reuse_is_recorded(self):
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as completed_dir:
            workflow = make_workflow("FairCheckpoint")
            workflow.enable_fair(self.profile(output_dir))
            task = DagonTask(TaskType.BATCH, "A", "exit 99")
            workflow.add_task(task)
            workflow.checkpoints = {"FairCheckpoint.A": {"working_dir": completed_dir, "code": 0}}
            workflow.run()
            with open(os.path.join(output_dir, "run.json"), encoding="utf-8") as source:
                run = json.load(source)
            self.assertTrue(run["tasks"]["A"]["checkpoint_reused"])
