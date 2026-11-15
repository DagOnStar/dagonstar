"""Independent evaluators, the result-fit metric, and acceptance gates."""
import tempfile
import unittest
from pathlib import Path

from dagon.agentic import AgenticEvaluationError, AgenticValidationError, EvaluatorSpec
from dagon.agentic.builtins import numeric_error, record_coverage
from dagon.agentic.evaluation import aggregate, validate_evaluator_result
from dagon.agentic.registry import snapshot
from dagon.agentic.schema import check_schema, validate
from tests.agentic_fixtures import (REQUIREMENT, agent_task, agent_workflow, prepared, read_json)


def entry(identifier, score, weight=1.0, status=None, mandatory=False, minimum=None, hard=False):
    return {"id": identifier, "score": score, "weight": weight, "mandatory": mandatory,
            "minimum_score": 1.0 if mandatory and minimum is None else minimum, "hard": hard,
            "status": status or ("pass" if score == 1.0 else "fail")}


class ResultFitTests(unittest.TestCase):
    def test_golden_weighted_mean(self):
        results = [entry("a", 1.0, 2.0), entry("b", 0.5, 1.0)]
        outcome = aggregate(results, 0.8)
        self.assertAlmostEqual(outcome["result_fit"], 5.0 / 6.0, places=15)
        self.assertTrue(outcome["accepted"])
        self.assertFalse(aggregate(results, 0.9)["accepted"])

    def test_threshold_boundary_is_inclusive(self):
        self.assertTrue(aggregate([entry("a", 1.0), entry("b", 0.5)], 0.75)["accepted"])

    def test_mandatory_and_hard_gates_override_the_mean(self):
        mandatory = [entry("a", 1.0, 2.0), entry("b", 0.5, 1.0, mandatory=True)]
        outcome = aggregate(mandatory, 0.8)
        self.assertAlmostEqual(outcome["result_fit"], 5.0 / 6.0)
        self.assertFalse(outcome["accepted"])
        self.assertEqual(outcome["mandatory_failures"], ["b"])
        self.assertTrue(aggregate([entry("a", 1.0, 2.0), entry("b", 0.5, 1.0, mandatory=True, minimum=0.5)],
                                  0.8)["accepted"])
        hard = [entry("a", 1.0, 2.0), entry("b", 0.5, 1.0, hard=True)]
        self.assertFalse(aggregate(hard, 0.8)["accepted"])

    def test_zero_weight_gate_runs_and_failed_requirements_stay_in_denominator(self):
        gate = entry("gate", 0.0, 0.0, mandatory=True, minimum=1.0)
        outcome = aggregate([entry("a", 1.0), gate], 0.5)
        self.assertEqual(outcome["result_fit"], 1.0)
        self.assertFalse(outcome["accepted"])
        self.assertEqual(aggregate([entry("a", 1.0), entry("b", 0.0)], 0.5)["result_fit"], 0.5)

    def test_any_evaluator_error_prevents_acceptance(self):
        outcome = aggregate([entry("a", 1.0), entry("b", None, status="error")], 0.0)
        self.assertIsNone(outcome["result_fit"])
        self.assertFalse(outcome["accepted"])
        self.assertEqual(outcome["evaluator_errors"], ["b"])

    def test_invalid_scores_are_errors_not_clamped(self):
        for score in (float("nan"), float("inf"), -0.1, 1.2, True, "1"):
            with self.subTest(score=score):
                with self.assertRaises(AgenticEvaluationError):
                    validate_evaluator_result({"status": "pass", "score": score}, 1.0)
        with self.assertRaises(AgenticEvaluationError):
            validate_evaluator_result({"status": "pass", "score": None}, 1.0)
        self.assertIsNone(validate_evaluator_result({"status": "pass", "score": None}, 0.0)["score"])


class BuiltinEvaluatorTests(unittest.TestCase):
    def test_numeric_error_scale_and_tolerance(self):
        result = numeric_error({"mean": 9.0}, 10.0, {"path": "mean", "scale": 4.0}, {})
        self.assertEqual(result["score"], 0.75)
        self.assertEqual(result["status"], "fail")
        tolerant = numeric_error({"mean": 9.0}, 10.0, {"path": "mean", "scale": 4.0, "tolerance": 1.0}, {})
        self.assertEqual(tolerant["status"], "pass")
        self.assertEqual(numeric_error({"mean": 0.0}, 10.0, {"path": "mean", "scale": 4.0}, {})["score"], 0.0)
        self.assertEqual(numeric_error({}, 10.0, {"path": "mean", "scale": 4.0}, {})["score"], 0.0)
        with self.assertRaises(AgenticValidationError):
            agent_task(requirements=[{"id": "n", "evaluator": "numeric_error", "expected": 1, "options": {"scale": 0}}])

    def test_record_coverage_penalises_duplicates_and_missing_ids(self):
        records = {"observations": [{"id": 1}, {"id": 2}, {"id": 2}, {"id": 3}, {"id": 4}]}
        self.assertEqual(record_coverage(records, {"count": 4}, {}, {})["score"], 0.8)
        self.assertEqual(record_coverage({"observations": [{"id": 1}]}, {"ids": [1, 2]}, {}, {})["score"], 0.5)
        self.assertEqual(record_coverage({"rows": []}, {"count": 1}, {}, {})["score"], 0.0)

    def test_schema_subset_rejects_unsupported_keywords(self):
        with self.assertRaisesRegex(AgenticValidationError, "unsupported JSON Schema keyword"):
            check_schema({"type": "object", "properties": {"a": {"pattern": "^x"}}})
        schema = {"type": "object", "required": ["a"], "additionalProperties": False,
                  "properties": {"a": {"type": "integer", "minimum": 1}}}
        check_schema(schema)
        self.assertEqual(validate({"a": 2}, schema), [])
        self.assertEqual(len(validate({"a": 0, "b": 1}, schema)), 2)
        self.assertTrue(validate({"a": True}, schema))


class EngineEvaluationTests(unittest.TestCase):
    def run_with(self, registry, requirements, threshold=1.0):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        workflow = agent_workflow("evaluation", directory.name)
        task = prepared(workflow, directory.name, agent_task(tools=[], registry=registry, requirements=requirements,
                                                             evaluation={"threshold": threshold}))
        return task

    def test_evaluator_errors_stop_the_run_with_null_fit(self):
        for function in ("tests.agentic_fixtures:nan_evaluator", "tests.agentic_fixtures:high_evaluator",
                         "tests.agentic_fixtures:raising_evaluator"):
            with self.subTest(function):
                registry = snapshot()
                registry.register_evaluator(EvaluatorSpec("faulty", "1.0.0", "faulty", function))
                task = self.run_with(registry, [REQUIREMENT, {"id": "faulty", "evaluator": "faulty"}])
                with self.assertRaises(AgenticEvaluationError):
                    task.execute()
                report = read_json(Path(task.working_dir, "outputs/evaluation.json"))
                self.assertIsNone(report["result_fit"])
                self.assertEqual(report["termination_reason"], "evaluator_error")
                self.assertFalse(Path(task.working_dir, "outputs/result.json").exists())

    def test_golden_example_through_the_engine(self):
        registry = snapshot()
        registry.register_evaluator(EvaluatorSpec("fixed", "1.0.0", "returns expected as score",
                                                  "tests.agentic_fixtures:fixed_evaluator", isolation="process"))
        requirements = [{"id": "primary", "evaluator": "fixed", "expected": 1.0, "weight": 2.0},
                        {"id": "secondary", "evaluator": "fixed", "expected": 0.5, "weight": 1.0}]
        task = self.run_with(registry, requirements, threshold=0.8)
        task.execute()
        self.assertAlmostEqual(task.agentic_report["result_fit"], 5.0 / 6.0)
        self.assertTrue(task.agentic_report["accepted"])
        self.assertEqual(task.agentic_report["evaluator_versions"], {"fixed": "1.0.0"})


if __name__ == "__main__":
    unittest.main()
