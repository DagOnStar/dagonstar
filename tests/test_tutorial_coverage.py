"""Tutorial coverage manifest: the real manifest passes, and each kind of omission is detected."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_tutorial_coverage",
                                                  ROOT / "tools" / "validate_tutorial_coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TutorialCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = _load_validator()
        cls.manifest = json.loads((ROOT / "docs/tutorial/coverage.json").read_text(encoding="utf-8"))
        cls.notebook = json.loads((ROOT / "docs/tutorial/DAGonStar_tutorial.ipynb").read_text(encoding="utf-8"))

    def errors(self, manifest=None, notebook=None):
        return self.validator.validate(copy.deepcopy(manifest or self.manifest),
                                       copy.deepcopy(notebook or self.notebook))

    def without_feature(self, feature_id):
        manifest = copy.deepcopy(self.manifest)
        manifest["features"] = [item for item in manifest["features"] if item["feature_id"] != feature_id]
        return manifest

    def test_repository_manifest_is_complete(self):
        self.assertEqual(self.errors(), [])

    def test_every_registered_task_type_is_derived_dynamically(self):
        from dagon.task import TaskType
        self.assertEqual(self.validator.task_type_values(), sorted(item.value for item in TaskType))
        self.assertIn("agentic", self.validator.task_type_values())

    def test_a_newly_registered_task_type_without_coverage_fails(self):
        from unittest import mock
        synthetic = self.validator.task_type_values() + ["synthetic-audit-type"]
        with mock.patch.object(self.validator, "task_type_values", return_value=sorted(synthetic)):
            errors = self.errors()
        self.assertIn("registered TaskType 'synthetic-audit-type' has no supported task-type coverage entry", errors)

    def test_deleting_a_task_type_mapping_fails(self):
        errors = self.errors(self.without_feature("tasktype.nomad"))
        self.assertIn("registered TaskType 'nomad' has no supported task-type coverage entry", errors)

    def test_deleting_a_feature_mapping_fails(self):
        errors = self.errors(self.without_feature("agentic.guardrails"))
        self.assertIn("required feature has no supported coverage: agentic.guardrails", errors)

    def test_deleting_an_evidence_target_fails(self):
        manifest = copy.deepcopy(self.manifest)
        entry = next(item for item in manifest["features"] if item["feature_id"] == "slurm.beeond")
        entry["test_targets"] = []
        errors = self.errors(manifest)
        self.assertIn("slurm.beeond needs at least one lesson, one example, and one test target", errors)
        self.assertIn("required feature has no supported coverage: slurm.beeond", errors)

    def test_nonexistent_evidence_paths_fail(self):
        manifest = copy.deepcopy(self.manifest)
        entry = next(item for item in manifest["features"] if item["feature_id"] == "cwl.export")
        entry["example_paths"] = ["examples/does_not_exist.py"]
        entry["test_targets"] = ["tests.test_cwl_example.NoSuchClass"]
        errors = self.errors(manifest)
        self.assertIn("cwl.export example does not exist: examples/does_not_exist.py", errors)
        self.assertIn("cwl.export: test class does not exist: tests.test_cwl_example.NoSuchClass", errors)

    def test_deleting_a_notebook_section_fails(self):
        notebook = copy.deepcopy(self.notebook)
        notebook["cells"] = [cell for cell in notebook["cells"]
                             if not "".join(cell.get("source", [])).startswith("## Lesson 20 ")]
        errors = self.errors(notebook=notebook)
        self.assertTrue(any("missing: 20" in error for error in errors), errors)

    def test_planned_features_do_not_count(self):
        manifest = copy.deepcopy(self.manifest)
        entry = next(item for item in manifest["features"] if item["feature_id"] == "tasktype.iot")
        entry["evidence_level"] = "planned"
        self.assertIn("registered TaskType 'iot' has no supported task-type coverage entry", self.errors(manifest))

    def test_duplicate_ids_and_unknown_levels_fail(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["features"].append(copy.deepcopy(manifest["features"][0]))
        manifest["features"][1]["evidence_level"] = "assumed"
        errors = self.errors(manifest)
        self.assertIn("duplicate feature_id: %s" % manifest["features"][0]["feature_id"], errors)
        self.assertTrue(any("unknown evidence_level 'assumed'" in error for error in errors), errors)

    def test_exclusions_require_evidence(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["exclusions"][0]["evidence"] = []
        errors = self.errors(manifest)
        self.assertIn("exclusion %s gives no implementation evidence" % manifest["exclusions"][0]["feature_id"],
                      errors)


if __name__ == "__main__":
    unittest.main()
