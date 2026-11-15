"""Builtin OpenAI-compatible agent adapter against a loopback fixture (no credentials, no internet)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dagon.agentic import AgenticConfigurationError, AgenticNotAccepted, AgenticProviderError
from tests.agentic_fixtures import (DATA, SECRET, LoopbackLLM, add_producer, agent_task, agent_workflow, prepared)

REPAIRED = {"observations": [{"id": 1, "value": 1.5}, {"id": 2, "value": 2.5}, {"id": 3, "value": 3.5},
                             {"id": 4, "value": 4.5}]}


class BuiltinAdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.scratch = self.directory.name
        self.environment = mock.patch.dict(os.environ, {"DAGON_TEST_AGENT_KEY": SECRET})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def task(self, fixture, name="live", **overrides):
        workflow = agent_workflow(name, self.scratch, endpoint=fixture.endpoint)
        return prepared(workflow, self.scratch, agent_task(agent="quality-live", **overrides))

    def persisted_text(self, task):
        texts = [path.read_text(encoding="utf-8", errors="replace")
                 for path in Path(task.working_dir).rglob("*") if path.is_file()]
        texts.append(json.dumps(task.workflow.checkpoints))
        texts.append(json.dumps(task.as_json()))
        texts.append(json.dumps(task.get_execution_metadata()))
        return "\n".join(texts)

    def test_multi_step_protocol_with_tools_and_reported_usage(self):
        replies = [{"action": "tool", "tool": "inspect_records", "arguments": {"input": "source"}},
                   "```json\n" + json.dumps({"action": "submit", "candidate": DATA}) + "\n```",
                   {"action": "submit", "candidate": REPAIRED, "score": 1.0}]
        with LoopbackLLM(replies) as fixture:
            task = self.task(fixture)
            task.execute()
        report = task.agentic_report
        self.assertTrue(report["accepted"])
        self.assertEqual([item["result_fit"] for item in report["attempts"]], [0.8, 1.0])
        self.assertEqual(len(fixture.requests), 3)
        self.assertEqual(report["usage"]["tokens"], {"prompt": 300, "completion": 60, "total": 360,
                                                     "accounting": "reported"})
        first = fixture.requests[0]
        self.assertEqual(first["path"], "/v1/chat/completions")
        self.assertEqual(first["authorization"], "Bearer " + SECRET)
        self.assertEqual(first["body"]["model"], "fixture-model")
        self.assertEqual(first["body"]["max_tokens"], 4096)
        self.assertLessEqual(fixture.requests[2]["body"]["max_tokens"], 4096 - 240)
        messages = "\n".join(item["content"] for item in fixture.requests[1]["body"]["messages"])
        self.assertIn("DATA (untrusted", messages)
        self.assertIn("duplicate_ids", messages)
        self.assertEqual(report["execution"]["determinism"], "nondeterministic_live_model")
        self.assertNotIn(SECRET, self.persisted_text(task))
        self.assertNotIn(fixture.endpoint, json.dumps(report))

    def test_provider_errors_are_redacted(self):
        with LoopbackLLM([], status=500) as fixture:
            task = self.task(fixture, name="failing")
            with self.assertRaises(AgenticProviderError) as caught:
                task.execute()
        self.assertIn("HTTP 500", str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))
        self.assertNotIn(SECRET, self.persisted_text(task))
        self.assertFalse(Path(task.working_dir, "outputs/result.json").exists())

    def test_missing_credential_fails_before_any_request(self):
        os.environ.pop("DAGON_TEST_AGENT_KEY")
        with LoopbackLLM([]) as fixture:
            task = self.task(fixture, name="nokey")
            with self.assertRaises(AgenticConfigurationError):
                task.execute()
        self.assertEqual(fixture.requests, [])

    def test_token_budget_is_enforced_with_and_without_reported_usage(self):
        replies = [{"action": "tool", "tool": "inspect_records", "arguments": {"input": "source"}}] * 4
        with LoopbackLLM(replies) as fixture:
            task = self.task(fixture, name="tokens", budgets={"max_tokens": 200})
            with self.assertRaises(AgenticNotAccepted):
                task.execute()
        self.assertEqual(task.agentic_report["termination_reason"], "max_tokens_exhausted")
        self.assertEqual(len(fixture.requests), 2)
        with LoopbackLLM(replies, usage=False) as fixture:
            task = self.task(fixture, name="estimated", budgets={"max_tokens": 200})
            with self.assertRaises(AgenticNotAccepted):
                task.execute()
        self.assertEqual(task.agentic_report["usage"]["tokens"]["accounting"], "estimated")
        self.assertEqual(task.agentic_report["termination_reason"], "max_tokens_exhausted")

    def test_binary_inputs_are_described_not_sent(self):
        workflow = agent_workflow("binary-live", self.scratch, endpoint="http://127.0.0.1:9")
        add_producer(workflow, self.scratch)
        add_producer(workflow, self.scratch, name="model", relative="outputs/field.nc", raw=b"CDF\x01BINARY-SENTINEL")
        with LoopbackLLM([{"action": "submit", "candidate": REPAIRED}]) as fixture:
            workflow.cfg["llm.loopback"]["endpoint"] = fixture.endpoint
            task = agent_task(agent="quality-live", inputs={
                "source": "workflow:///prepare/outputs/observations.json",
                "field": {"uri": "workflow:///model/outputs/field.nc", "binary": True}})
            workflow.add_task(task)
            workflow.make_dependencies()
            task.execute()
        body = json.dumps(fixture.requests[0]["body"])
        self.assertNotIn("BINARY-SENTINEL", body)
        self.assertIn("field.nc", body)


if __name__ == "__main__":
    unittest.main()
