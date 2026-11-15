"""Bounded agent loop, tools, budgets, publication, and workflow integration."""
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from dagon import Status, Workflow
from dagon.agentic import (AgenticCancelled, AgenticGuardrailViolation, AgenticNotAccepted, AgenticTask,
                           AgenticValidationError, ToolSpec)
from dagon.agentic.engine import COMMIT_MANIFEST
from dagon.agentic.registry import snapshot
from dagon.prestage import PreStageConfigurationError
from dagon.task import DagonTask, TaskType
from tests.agentic_fixtures import (DATA, REQUIREMENT, SOURCE, SPECIFICATION, add_producer, agent_task,
                                    agent_workflow, pid_alive, prepared, read_json)


class ContractValidationTests(unittest.TestCase):
    def test_factory_registration_preserves_existing_values(self):
        self.assertEqual(TaskType.AGENTIC.value, "agentic")
        self.assertEqual(TaskType.IOT.value, "iot")
        self.assertEqual(TaskType.LLM.value, "llm")
        self.assertIsInstance(agent_task(), AgenticTask)

    def test_invalid_declarations_are_rejected(self):
        nan = float("nan")
        cases = {
            "nan expected": dict(requirements=[dict(REQUIREMENT, expected={"count": nan})]),
            "infinite weight": dict(requirements=[dict(REQUIREMENT, weight=float("inf"))]),
            "duplicate ids": dict(requirements=[REQUIREMENT, REQUIREMENT]),
            "no positive weight": dict(requirements=[dict(REQUIREMENT, weight=0.0)]),
            "unknown requirement field": dict(requirements=[dict(REQUIREMENT, prompt="x")]),
            "unknown evaluator": dict(requirements=[dict(REQUIREMENT, evaluator="llm_judge")]),
            "bad coverage expectation": dict(requirements=[dict(REQUIREMENT, expected={"rows": 4})]),
            "numeric without scale": dict(requirements=[{"id": "n", "evaluator": "numeric_error", "expected": 1}]),
            "minimum above one": dict(requirements=[dict(REQUIREMENT, minimum_score=1.5)]),
            "unsupported schema keyword": dict(specification=dict(SPECIFICATION, output_schema={"pattern": "x"})),
            "schema version": dict(specification=dict(SPECIFICATION, schema_version=2)),
            "unknown specification field": dict(specification=dict(SPECIFICATION, endpoint="http://x")),
            "empty objective": dict(specification={"objective": " "}),
            "threshold above one": dict(evaluation={"threshold": 1.01}),
            "unknown aggregation": dict(evaluation={"aggregation": "max"}),
            "absolute output": dict(outputs={"result": "/tmp/result.json"}),
            "traversal output": dict(outputs={"result": "../result.json"}),
            "drive output": dict(outputs={"result": "C:/result.json"}),
            "unc output": dict(outputs={"result": "//server/share/result.json"}),
            "backslash output": dict(outputs={"result": "outputs\\\\result.json"}),
            "reserved output": dict(outputs={"result": ".dagon/agentic/commit.json"}),
            "colliding outputs": dict(outputs={"result": "outputs/evaluation.json"}),
            "unknown output name": dict(outputs={"extra": "outputs/x.json"}),
            "two references in one input": dict(inputs={"source": SOURCE + " " + SOURCE}),
            "traversal reference": dict(inputs={"source": "workflow:///prepare/../secret.json"}),
            "unknown tool": dict(tools=["shell"]),
            "unknown guardrail": dict(guardrails=["nope"]),
            "unknown budget": dict(budgets={"max_cost": 1}),
            "negative budget": dict(budgets={"max_steps": -1}),
            "fractional budget": dict(budgets={"max_steps": 1.5}),
            "missing profile name": dict(agent=""),
            "callable expected": dict(requirements=[dict(REQUIREMENT, expected=print)]),
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                with self.assertRaises(AgenticValidationError):
                    agent_task(**overrides)

    def test_output_schema_support_is_explicit(self):
        task = agent_task(specification=dict(SPECIFICATION, output_schema={
            "type": "object", "required": ["observations"], "additionalProperties": False,
            "properties": {"observations": {"type": "array", "minItems": 1, "items": {"type": "object"}}}}))
        self.assertEqual(task.contract["specification"]["output_schema"]["additionalProperties"], False)


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.scratch = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def run_agent(self, task=None, name="loop", **producer):
        workflow = agent_workflow(name, self.scratch)
        task = prepared(workflow, self.scratch, task, **producer)
        return workflow, task

    def assert_not_published(self, task):
        self.assertFalse(Path(task.working_dir, "outputs/result.json").exists())
        self.assertFalse(Path(task.working_dir, COMMIT_MANIFEST).exists())
        report = read_json(Path(task.working_dir, "outputs/evaluation.json"))
        self.assertFalse(report["accepted"])
        return report

    def test_tool_assisted_repair_is_accepted_and_published(self):
        _, task = self.run_agent()
        task.execute()
        result = read_json(Path(task.working_dir, "outputs/result.json"))
        self.assertEqual([item["id"] for item in result["observations"]], [1, 2, 3, 4])
        report = read_json(Path(task.working_dir, "outputs/evaluation.json"))
        self.assertTrue(report["accepted"])
        self.assertEqual(report["result_fit"], 1.0)
        self.assertEqual(report["usage"]["tool_calls"], 2)
        self.assertEqual(report["selected_attempt"], 1)
        self.assertEqual(report["termination_reason"], "accepted")
        self.assertEqual(report["tool_versions"], {"inspect_records": "1.0.0", "repair_records": "1.0.0"})
        self.assertEqual(report["execution"]["determinism"], "deterministic_fixture")
        commit = read_json(Path(task.working_dir, COMMIT_MANIFEST))
        self.assertEqual({item["name"] for item in commit["outputs"]}, {"result", "evaluation", "trace"})
        trace = read_json(Path(task.working_dir, "outputs/trace.json"))
        self.assertEqual([entry["event"] for entry in trace["entries"]], ["tool", "tool", "candidate"])
        self.assertTrue(Path(task.working_dir, ".dagon/agentic/attempts/01/candidate.json").is_file())

    def test_tool_free_loop_revises_within_budget(self):
        _, task = self.run_agent(agent_task(tools=[]))
        task.execute()
        report = read_json(Path(task.working_dir, "outputs/evaluation.json"))
        self.assertEqual([item["result_fit"] for item in report["attempts"]], [0.8, 1.0])
        self.assertEqual(report["usage"]["tool_calls"], 0)
        self.assertEqual(report["tool_versions"], {})

    def test_profile_without_tools_grants_none(self):
        _, task = self.run_agent(agent_task(agent="reason-only"))
        task.execute()
        self.assertEqual(task.effective_profile.tools, ())
        self.assertEqual(task.agentic_report["usage"]["tool_calls"], 0)

    def test_blocked_actions_terminate_before_execution(self):
        for scenario, code in (("undeclared_tool", "undeclared_tool"), ("path_escape", "path_escape"),
                               ("workflow_uri", "workflow_uri_injection")):
            with self.subTest(scenario):
                _, task = self.run_agent(agent_task(agent=scenario), name="blocked-" + scenario.replace("_", "-"))
                with self.assertRaises(AgenticGuardrailViolation) as caught:
                    task.execute()
                self.assertEqual(caught.exception.violation["code"], code)
                report = self.assert_not_published(task)
                self.assertEqual(report["termination_reason"], "guardrail_blocked")
                self.assertEqual(report["usage"]["tool_calls"], 0)
                self.assertEqual(task.workflow.checkpoints[task.checkpoint_key()]["code"], 1)

    def test_malformed_responses_count_toward_max_steps(self):
        _, task = self.run_agent(agent_task(agent="malformed"))
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        report = self.assert_not_published(task)
        self.assertEqual(report["termination_reason"], "max_steps_exhausted")
        self.assertEqual(report["usage"]["steps"], 4)
        self.assertIsNone(report["result_fit"])

    def test_self_reported_score_cannot_cause_acceptance(self):
        _, task = self.run_agent(agent_task(agent="self_reported_score"))
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        report = self.assert_not_published(task)
        self.assertTrue(all(item["result_fit"] == 0.8 for item in report["attempts"]))
        trace = read_json(Path(task.working_dir, "outputs/trace.json"))
        self.assertIn("self_assessment_ignored", [entry["event"] for entry in trace["entries"]])

    def test_repairable_guardrail_violation_returns_feedback(self):
        _, task = self.run_agent(agent_task(agent="drop_records", tools=[]))
        task.execute()
        report = task.agentic_report
        self.assertEqual(report["attempts"][0]["guard_violations"], ["record_ids_changed"])
        self.assertTrue(report["accepted"])
        self.assertEqual(report["selected_attempt"], 2)

    def test_slow_adapter_is_stopped_by_the_task_deadline(self):
        _, task = self.run_agent(agent_task(agent="slow"))
        started = time.monotonic()
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(self.assert_not_published(task)["termination_reason"], "timeout_seconds_exhausted")

    def test_attempt_and_tool_budgets_are_enforced(self):
        _, task = self.run_agent(agent_task(tools=[], budgets={"max_attempts": 1}))
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        self.assertEqual(task.agentic_report["termination_reason"], "max_attempts_exhausted")
        _, task = self.run_agent(agent_task(budgets={"max_tool_calls": 1}), name="toolbudget")
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        self.assertEqual(task.agentic_report["termination_reason"], "max_tool_calls_exhausted")

    def registry_with(self, *specs):
        registry = snapshot()
        for spec in specs:
            registry.register_tool(spec, replace=True)
        return registry

    def custom_workflow(self, registry, tools, name, budgets=None):
        workflow = agent_workflow(name, self.scratch)
        workflow.cfg["agent.custom"] = {"provider": "fixture", "tools": ", ".join(tools), "max_steps": "4",
                                        "timeout_seconds": "20"}
        task = agent_task(agent="custom", registry=registry, budgets=budgets)
        prepared(workflow, self.scratch, task)
        return task

    def test_tool_errors_become_feedback_without_publication(self):
        registry = self.registry_with(
            ToolSpec("inspect_records", "9.0.0", "fails", "tests.agentic_fixtures:failing_tool",
                     side_effect="read"),
        )
        task = self.custom_workflow(registry, ["inspect_records"], "toolerror")
        with self.assertRaises(AgenticNotAccepted):
            task.execute()  # the cooperative mock keeps retrying the failing tool
        trace = read_json(Path(task.working_dir, "outputs/trace.json"))
        errors = [entry for entry in trace["entries"] if entry.get("status") == "error"]
        self.assertTrue(errors and "tool failure sentinel" in errors[0]["error"])

    def test_process_tool_timeout_kills_the_process_group(self):
        from dagon.agentic.sandbox import call_in_process
        from dagon.agentic.errors import AgenticTimeoutError
        pid_file = Path(self.scratch, "grandchild.pid")
        started = time.monotonic()
        with self.assertRaises(AgenticTimeoutError):
            call_in_process("tests.agentic_fixtures:spawning_tool", [{"pid_file": str(pid_file)}, {}], 3.0, 1000)
        self.assertLess(time.monotonic() - started, 10)
        if os.name == "posix" and pid_file.exists():
            pid = int(pid_file.read_text())
            for _ in range(50):
                if not pid_alive(pid):
                    break
                time.sleep(0.1)
            self.assertFalse(pid_alive(pid), "grandchild process survived the timeout")

    def test_output_bound_rejects_large_tool_results(self):
        from dagon.agentic.sandbox import call_in_process
        from dagon.agentic.errors import AgenticToolError
        with self.assertRaises(AgenticToolError):
            call_in_process("tests.agentic_fixtures:huge_tool", [{}, {}], 20.0, 1000)

    def test_cancellation_prevents_publication_and_stops_tools(self):
        registry = self.registry_with(ToolSpec("inspect_records", "9.1.0", "sleeps",
                                               "tests.agentic_fixtures:sleepy_tool", side_effect="read",
                                               timeout_seconds=30))
        task = self.custom_workflow(registry, ["inspect_records"], "cancel")
        timer = threading.Timer(1.0, task.cancel)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(AgenticCancelled):
            task.execute()
        timer.cancel()
        self.assertLess(time.monotonic() - started, 10)
        self.assert_not_published(task)

    def test_symlink_escape_is_refused_before_transfer(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        outside = Path(self.scratch, "outside.json")
        outside.write_text(json.dumps(DATA), encoding="utf-8")
        workflow = agent_workflow("symlink", self.scratch)
        producer = add_producer(workflow, self.scratch)
        target = Path(producer.working_dir, "outputs/observations.json")
        target.unlink()
        try:
            os.symlink(str(outside), str(target))
        except OSError:
            self.skipTest("symlink creation not permitted")
        task = agent_task()
        workflow.add_task(task)
        workflow.make_dependencies()
        with self.assertRaisesRegex(AgenticValidationError, "symbolic link"):
            task.execute()
        self.assertFalse(Path(task.working_dir, ".dagon/inputs").exists())

    def test_binary_artifacts_are_staged_and_hashed_but_not_parsed(self):
        workflow = agent_workflow("binary", self.scratch)
        add_producer(workflow, self.scratch)
        add_producer(workflow, self.scratch, name="model", relative="outputs/field.nc", raw=b"CDF\x01\x00\xff\xfe")
        task = agent_task(inputs={"source": SOURCE, "field": {"uri": "workflow:///model/outputs/field.nc",
                                                              "binary": True, "media_type": "application/x-netcdf"}})
        workflow.add_task(task)
        workflow.make_dependencies()
        task.execute()
        staged = Path(task.working_dir, ".dagon/inputs/binary/model/outputs/field.nc")
        self.assertEqual(staged.read_bytes(), b"CDF\x01\x00\xff\xfe")
        self.assertIn("workflow:///model/outputs/field.nc", task.agentic_report["digests"]["inputs"])

    def test_invalid_json_input_fails_closed(self):
        workflow = agent_workflow("badinput", self.scratch)
        task = prepared(workflow, self.scratch, raw=b"{not json")
        with self.assertRaises(AgenticGuardrailViolation):
            task.execute()
        self.assert_not_published(task)


class WorkflowIntegrationTests(unittest.TestCase):
    def test_references_are_discovered_once_across_fields(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("refs", scratch)
            producer = add_producer(workflow, scratch)
            task = agent_task(
                specification=dict(SPECIFICATION, context="Compare with " + SOURCE),
                requirements=[REQUIREMENT, {"id": "same", "evaluator": "reference_match", "weight": 0.0,
                                            "reference": SOURCE, "options": {"path": "observations.0"},
                                            "expected": None}])
            workflow.add_task(task)
            workflow.make_dependencies()
            workflow.make_dependencies()
            self.assertEqual(task.prevs, [producer])
            self.assertEqual(producer.reference_count, 1)

    def test_missing_producer_and_cycles_are_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("missing", scratch)
            workflow.add_task(agent_task())
            with self.assertRaisesRegex(AgenticValidationError, "not found"):
                workflow.make_dependencies()
            workflow = agent_workflow("cycle", scratch)
            first = agent_task("first", inputs={"source": "workflow:///second/outputs/result.json"})
            second = agent_task("second", inputs={"source": "workflow:///first/outputs/result.json"})
            workflow.add_task(first)
            workflow.add_task(second)
            with self.assertRaisesRegex(Exception, "cycle"):
                workflow.make_dependencies()

    def test_json_round_trip_keeps_logical_contract_only(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("roundtrip", scratch)
            add_producer(workflow, scratch)
            task = agent_task(working_dir=str(Path(scratch, "fixed")))
            workflow.add_task(task)
            document = workflow.as_json()
            encoded = json.dumps(document)
            self.assertIn(SOURCE, encoded)
            self.assertNotIn(scratch, json.dumps(document["tasks"]["quality_control"]))
            restored = Workflow("placeholder", config=workflow.cfg, jsonload=json.loads(encoded))
            again = [item for item in restored.tasks if item.name == "quality_control"][0]
            self.assertIsInstance(again, AgenticTask)
            self.assertEqual(again.contract, task.contract)

    def test_dry_run_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("dry", scratch)
            task = prepared(workflow, scratch)
            workflow.set_dry(True)
            before = sorted(str(path) for path in Path(scratch).rglob("*"))
            task.execute()
            self.assertIsNone(task.working_dir)
            self.assertEqual(sorted(str(path) for path in Path(scratch).rglob("*")), before)
            self.assertNotIn(task.checkpoint_key(), workflow.checkpoints)

    def test_pre_stage_is_not_supported(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("prestage", scratch)
            with self.assertRaises(PreStageConfigurationError):
                workflow.add_task(agent_task(pre_stage=True))
            workflow = agent_workflow("prestage-default", scratch, pre_stage=True)
            task = prepared(workflow, scratch)
            self.assertFalse(task.resolve_pre_stage())

    def test_portable_emulation_never_contacts_the_live_endpoint(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("portable", scratch, portable=True, endpoint="http://127.0.0.1:9")
            task = prepared(workflow, scratch, agent_task(agent="quality-live"))
            os.environ.pop("DAGON_TEST_AGENT_KEY", None)
            task.execute()
            execution = task.agentic_report["execution"]
            self.assertTrue(execution["portable_emulation"])
            self.assertEqual(execution["configured_implementation"], "builtin")
            self.assertEqual(task.agentic_report["agent"]["implementation"], "builtin")

    def test_failure_blocks_downstream_tasks_in_a_real_run(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("downstream", scratch)
            add_producer(workflow, scratch)
            agent = agent_task(agent="malformed")
            consumer = DagonTask(TaskType.BATCH, "consume", "cat workflow:///quality_control/outputs/result.json")
            workflow.add_task(agent)
            workflow.add_task(consumer)
            workflow.run()
            self.assertIs(agent.status, Status.FAILED)
            self.assertIs(consumer.status, Status.FAILED)
            self.assertIsNone(consumer.working_dir)

    def test_fair_records_accepted_agentic_outputs_without_secrets(self):
        from dagon.fair import Agent, FairProfile
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("fair-agentic", scratch, endpoint="http://127.0.0.1:9")
            output_dir = str(Path(scratch, "fair"))
            workflow.enable_fair(FairProfile(title="Agentic FAIR", description="Agentic provenance.",
                                             creators=[Agent(name="tests")], license="Apache-2.0",
                                             output_dir=output_dir))
            add_producer(workflow, scratch)
            workflow.add_task(agent_task())
            workflow.run()
            run = read_json(Path(output_dir, "run.json"))
        record = run["tasks"]["quality_control"]
        self.assertEqual(record["execution"]["model"], "agentic")
        self.assertTrue(record["execution"]["accepted"])
        artifacts = {item["role"]: item for item in run["artifacts"] if item.get("task") == "quality_control"}
        self.assertTrue(artifacts["agentic-result"]["accepted_output"])
        self.assertFalse(artifacts["agentic-evaluation"]["accepted_output"])
        self.assertIn({"producer": "prepare", "consumer": "quality_control", "path": "outputs/observations.json",
                       "type": "workflow-edge"}, run["dependencies"])
        self.assertNotIn("127.0.0.1:9", json.dumps(run))

    def test_mixed_graph_agentic_produces_for_and_consumes_from_other_types(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("mixed-agentic", scratch)
            workflow.add_task(DagonTask(TaskType.BATCH, "prepare", "mkdir -p outputs; printf '%s' '"
                                        + json.dumps(DATA) + "' > outputs/observations.json"))
            first = agent_task()
            second = agent_task("review", tools=[], inputs={"source": "workflow:///quality_control/outputs/result.json"})
            native = DagonTask(TaskType.NATIVE, "native", "tests.native_functions:count_records",
                               inputs={"input_file": "workflow:///review/outputs/result.json"},
                               outputs={"output_file": "count.json"})
            iot = DagonTask(TaskType.IOT, "iot", operation="observe", provider="mock",
                            request={"events": [{"source": "workflow:///review/outputs/evaluation.json"}]},
                            completion={"mode": "first_event"}, outputs={"observations": "outputs/o.json"})
            for task in (first, second, native, iot):
                workflow.add_task(task)
            workflow.run()
            self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                            [(task.name, task.status) for task in workflow.tasks])
            self.assertEqual(second.prevs, [first])
            self.assertTrue(second.agentic_report["accepted"])
            self.assertEqual(read_json(Path(native.working_dir, "outputs/count.json")), {"count": 4})


if __name__ == "__main__":
    unittest.main()
