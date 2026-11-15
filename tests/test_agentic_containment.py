"""Timed-out or cancelled agent components cannot act after the supervisor stops waiting.

Adapters, custom evaluators, and custom guardrails run in supervised worker
processes; on timeout or cancellation the whole process group is killed, so
neither the component nor a process it started can write a delayed marker,
change published outputs, or create a commit manifest.  Inline execution is
refused unless a component is registered as side-effect free.
"""
import hashlib
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from dagon import Workflow
from dagon.agentic.engine import COMMIT_MANIFEST
from dagon.agentic.errors import (AgenticCancelled, AgenticEvaluationError, AgenticNotAccepted,
                                  AgenticValidationError)
from dagon.agentic.guardrails import run_guards
from dagon.agentic.registry import AdapterSpec, EvaluatorSpec, GuardrailSpec, snapshot
from tests.agentic_fixtures import REQUIREMENT, agent_config, agent_task, prepared

POSIX = os.name == "posix"
# Deadlines leave room for worker start-up on slow (for example NFS-mounted) installations;
# each late component waits longer than its deadline before writing its marker.
DEADLINE = 4.0
DELAY = 5.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ContainmentTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.scratch = directory.name
        self.marker = Path(self.scratch, "late-marker")
        self.started = Path(self.scratch, "component-started")

    def assert_nothing_happened_later(self, delay, task=None):
        """The component started, and nothing it or its descendants scheduled happened after the return."""
        self.assertTrue(self.started.is_file(), "the component never started, so the check would prove nothing")
        evaluation = None
        if task is not None:
            path = Path(task.working_dir, "outputs/evaluation.json")
            evaluation = digest(path) if path.is_file() else None
        self.assertFalse(self.marker.exists(), "the component was not stopped at its deadline")
        # Wait until well after the moment the component would have written its marker.
        wait = float(self.started.read_text(encoding="utf-8")) + delay + 1.0 - time.time()
        time.sleep(max(0.0, wait))
        self.assertFalse(self.marker.exists(), "a stopped component acted after the supervisor returned")
        if task is not None:
            self.assertFalse(Path(task.working_dir, COMMIT_MANIFEST).exists())
            self.assertFalse(Path(task.working_dir, "outputs/result.json").exists())
            path = Path(task.working_dir, "outputs/evaluation.json")
            self.assertEqual(digest(path) if path.is_file() else None, evaluation,
                             "the evaluation report changed after the task returned")


class LateEvaluatorTests(ContainmentTestCase):
    def evaluator_task(self, spawn=False, timeout=DEADLINE, delay=DELAY):
        registry = snapshot()
        registry.register_evaluator(EvaluatorSpec("late", "1.0.0", "sleeps past its deadline",
                                                  "tests.agentic_fixtures:late_evaluator",
                                                  timeout_seconds=timeout))
        options = {"marker": str(self.marker), "spawn": spawn, "started": str(self.started), "delay": delay}
        requirements = [REQUIREMENT, {"id": "late", "evaluator": "late", "options": options, "weight": 0.0}]
        workflow = Workflow("contained", config=agent_config(self.scratch))
        return prepared(workflow, self.scratch, agent_task(tools=[], registry=registry, requirements=requirements))

    def test_timed_out_evaluator_cannot_write_after_return(self):
        task = self.evaluator_task()
        with self.assertRaises(AgenticEvaluationError):
            task.execute()
        self.assertEqual(task.agentic_report["termination_reason"], "evaluator_error")
        self.assert_nothing_happened_later(DELAY, task)

    @unittest.skipUnless(POSIX, "process-group descendants are checked on POSIX; Windows uses taskkill /T")
    def test_timed_out_evaluator_descendants_are_killed(self):
        task = self.evaluator_task(spawn=True)
        with self.assertRaises(AgenticEvaluationError):
            task.execute()
        self.assert_nothing_happened_later(DELAY, task)

    def test_cancelled_evaluator_cannot_write_after_return(self):
        task = self.evaluator_task(timeout=60.0, delay=3.0)
        outcome = {}

        def run():
            try:
                task.execute()
            except BaseException as exc:  # recorded for the assertion below
                outcome["error"] = exc

        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 60
        while not self.started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        task.cancel_event.set()
        worker.join(30)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcome.get("error"), AgenticCancelled)
        self.assert_nothing_happened_later(3.0, task)


class LateGuardTests(ContainmentTestCase):
    def test_timed_out_guard_fails_closed_and_cannot_write_after_return(self):
        registry = snapshot()
        registry.register_guardrail(GuardrailSpec("late", "1", "sleeps past its deadline", "result",
                                                  "tests.agentic_fixtures:late_guard"))
        environment = {"DAGON_TEST_LATE_MARKER": str(self.marker), "DAGON_TEST_LATE_DELAY": str(DELAY),
                       "DAGON_TEST_LATE_STARTED": str(self.started)}
        with mock.patch.dict(os.environ, environment):
            violations = run_guards("result", ["late"], {"observations": []}, {}, registry, DEADLINE)
        self.assertEqual([item.code for item in violations], ["guard_error"])
        self.assert_nothing_happened_later(DELAY)


class LateAdapterTests(ContainmentTestCase):
    def adapter_workflow(self, registry):
        config = agent_config(self.scratch)
        config["agent_provider.late"] = {"implementation": "late"}
        config["agent.late"] = {"provider": "late", "max_steps": "4", "timeout_seconds": str(int(DEADLINE))}
        workflow = Workflow("contained-adapter", config=config)
        return prepared(workflow, self.scratch, agent_task(agent="late", tools=[], registry=registry))

    def registry(self):
        registry = snapshot()
        registry.register_adapter(AdapterSpec("late", "1.0.0", "tests.agentic_fixtures:late_adapter_factory"))
        return registry

    def run_late_adapter(self, spawn):
        task = self.adapter_workflow(self.registry())
        environment = {"DAGON_TEST_LATE_MARKER": str(self.marker), "DAGON_TEST_LATE_STARTED": str(self.started),
                       "DAGON_TEST_LATE_SPAWN": "1" if spawn else "0"}
        with mock.patch.dict(os.environ, environment):
            with self.assertRaises(AgenticNotAccepted):
                task.execute()
        self.assertEqual(task.agentic_report["termination_reason"], "timeout_seconds_exhausted")
        self.assertEqual(task.agentic_report["execution"]["adapter"], "late")
        # The adapter sleeps the time it was given plus 0.5 s; it was given at most DEADLINE.
        self.assert_nothing_happened_later(DEADLINE + 0.5, task)

    def test_timed_out_adapter_cannot_write_after_return(self):
        self.run_late_adapter(spawn=False)

    @unittest.skipUnless(POSIX, "process-group descendants are checked on POSIX; Windows uses taskkill /T")
    def test_timed_out_adapter_descendants_are_killed(self):
        self.run_late_adapter(spawn=True)

    def test_adapter_start_up_counts_against_the_deadline_and_is_reported(self):
        config = agent_config(self.scratch)
        config["agent.instant"] = {"provider": "fixture", "max_steps": "4", "timeout_seconds": "0.001"}
        workflow = Workflow("contained-start", config=config)
        task = prepared(workflow, self.scratch, agent_task(agent="instant", tools=[]))
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        report = task.agentic_report
        self.assertEqual(report["termination_reason"], "timeout_seconds_exhausted")
        self.assertEqual(report["execution"]["determinism"], "adapter_not_started")
        self.assertFalse(Path(task.working_dir, COMMIT_MANIFEST).exists())


class InlineRegistrationTests(unittest.TestCase):
    def test_inline_requires_a_side_effect_free_declaration(self):
        registry = snapshot()
        cases = [
            (registry.register_evaluator, EvaluatorSpec("e", "1", "inline", lambda *a: {}, isolation="inline")),
            (registry.register_guardrail, GuardrailSpec("g", "1", "inline", "result", lambda *a: None,
                                                        isolation="inline")),
            (registry.register_adapter, AdapterSpec("a", "1", lambda **o: None, isolation="inline")),
            (registry.register_evaluator, EvaluatorSpec("r", "1", "reads", lambda *a: {}, isolation="inline",
                                                        side_effect="read")),
        ]
        for register, spec in cases:
            with self.subTest(spec.id), self.assertRaises(AgenticValidationError):
                register(spec)

    def test_process_isolation_requires_an_importable_reference(self):
        registry = snapshot()
        with self.assertRaises(AgenticValidationError):
            registry.register_evaluator(EvaluatorSpec("e", "1", "callable", lambda *a: {}))
        with self.assertRaises(AgenticValidationError):
            registry.register_guardrail(GuardrailSpec("g", "1", "callable", "result", lambda *a: None))
        with self.assertRaises(AgenticValidationError):
            registry.register_adapter(AdapterSpec("a", "1", lambda **o: None))

    def test_declared_side_effect_free_components_may_run_inline(self):
        registry = snapshot()
        registry.register_evaluator(EvaluatorSpec("e", "1", "pure", lambda *a: {"status": "pass", "score": 1.0},
                                                  isolation="inline", side_effect="none"))
        registry.register_guardrail(GuardrailSpec("g", "1", "pure", "result", lambda *a: None,
                                                  isolation="inline", side_effect="none"))
        self.assertEqual(registry.evaluators["e"].isolation, "inline")

    def test_built_in_components_follow_the_rule(self):
        registry = snapshot()
        for table in (registry.evaluators, registry.guardrails, registry.adapters):
            for spec in table.values():
                with self.subTest(spec.id):
                    if spec.isolation == "inline":
                        self.assertEqual(spec.side_effect, "none")
                    else:
                        self.assertIn(":", spec.factory if isinstance(spec, AdapterSpec) else spec.function)
        self.assertEqual(registry.adapters["builtin"].isolation, "process")
        self.assertEqual(registry.adapters["mock"].isolation, "process")
        self.assertEqual(registry.evaluators["reference_match"].isolation, "process")


if __name__ == "__main__":
    unittest.main()
