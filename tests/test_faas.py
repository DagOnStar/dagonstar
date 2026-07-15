import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from dagon import Workflow
from dagon.faas import FaaSTask
from dagon.faas_models import FaaSInvocation
from dagon.faas_providers import FaaSError, HTTPProvider, MockProvider, get_provider
from dagon.fair import AccessPolicy, Agent, FairProfile
from dagon.task import DagonTask, TaskType


class FaaSTaskTests(unittest.TestCase):
    class _HTTPResponse:
        def __init__(self, payload, status=200, headers=None):
            self.payload = json.dumps(payload).encode("utf-8")
            self.status = status
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return self.payload

    def test_factory_validation_and_portable_json(self):
        original = {"nested": [{"value": 4}]}
        task = DagonTask(TaskType.FAAS, "invoke", provider="mock", function="double", inputs=original,
                         outputs={"result": "result.json"})
        self.assertIsInstance(task, FaaSTask)
        original["nested"][0]["value"] = 99
        self.assertEqual(task.inputs["nested"][0]["value"], 4)
        payload = task.as_json()
        self.assertEqual(payload["type"], "faas")
        self.assertEqual(payload["outputs"]["result"]["path"], "result.json")
        self.assertNotIn("working_dir", json.dumps(payload["provider_options"]))
        with self.assertRaises(ValueError):
            DagonTask(TaskType.FAAS, "bad", provider="mock", function="x", invocation="later")
        with self.assertRaises(ValueError):
            DagonTask(TaskType.FAAS, "bad", provider="http", function="x",
                      provider_options={"authorization": "marker-secret"})
        with self.assertRaises(ValueError):
            DagonTask(TaskType.FAAS, "bad", provider="mock", function="x", outputs={"x": "../x"})

    def test_nested_reference_dependency_staging_retry_and_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            producer_dir = root / "producer"
            producer_dir.mkdir()
            producer_dir.joinpath("data.json").write_text('{"value": 4}\n', encoding="utf-8")
            workflow = Workflow("faas-test", config={"batch": {"remove_dir": False}})
            producer = DagonTask(TaskType.BATCH, "prepare", "true", working_dir=str(producer_dir))
            task = DagonTask(TaskType.FAAS, "invoke", provider="mock", function="double",
                inputs={"nested": [{"document": "workflow:///prepare/data.json"}]},
                outputs={"result": "result.json"}, retry={"max_attempts": 3},
                provider_options={"mock": {"transient_failures": 1,
                    "response": {"status": "succeeded", "outputs": {"result": {"value": 8}}}}},
                working_dir=str(root / "invoke"))
            workflow.add_task(producer)
            workflow.add_task(task)
            workflow.make_dependencies()
            self.assertEqual(task.prevs, [producer])
            task.execute()
            self.assertEqual(json.loads((root / "invoke" / "outputs" / "result.json").read_text()), {"value": 8})
            request = json.loads((root / "invoke" / ".dagon" / "faas_request.json").read_text())
            artifact = request["data"]["inputs"]["nested"][0]["document"]
            self.assertEqual(artifact["kind"], "artifact")
            self.assertEqual(len(task.attempt_records), 2)
            self.assertNotIn(str(root), json.dumps(task.as_json()))

    def test_mock_error_and_missing_optional_sdk_boundary(self):
        provider = get_provider("mock")
        self.assertTrue(provider.capabilities().supports_sync)
        with self.assertRaises(ValueError):
            get_provider("does-not-exist")

    def test_http_provider_builds_envelope_headers_and_normalizes_response(self):
        invocation = FaaSInvocation("http", "echo", "sync", {"value": 4}, 17,
            "stable-id", 1, {"endpoint": "https://functions.example/invoke",
                              "header_env": {"X-Test-Token": "DAGON_FAAS_TEST_TOKEN"},
                              "cloudevents": True})
        response = self._HTTPResponse({"status": "succeeded", "outputs": {}},
                                      headers={"x-request-id": "request-42"})
        with patch.dict(os.environ, {"DAGON_FAAS_TEST_TOKEN": "runtime-secret"}), \
                patch("dagon.faas_providers.urlopen", return_value=response) as request:
            result = HTTPProvider().invoke(invocation)
        sent = request.call_args.args[0]
        self.assertEqual(request.call_args.kwargs["timeout"], 17)
        self.assertEqual(sent.get_header("X-test-token"), "runtime-secret")
        self.assertEqual(sent.get_header("Ce-id"), "stable-id")
        self.assertEqual(json.loads(sent.data), {"value": 4})
        self.assertEqual(result.request_id, "request-42")
        self.assertEqual(result.metadata["status_code"], 200)

    def test_http_provider_classifies_transient_status_and_missing_environment_header(self):
        invocation = FaaSInvocation("http", "echo", "sync", {}, 1, "id", 1,
            {"endpoint": "https://functions.example/invoke"})
        from urllib.error import HTTPError
        failure = HTTPError("https://functions.example/invoke", 429, "limited", {}, BytesIO(b"{}"))
        with patch("dagon.faas_providers.urlopen", side_effect=failure):
            with self.assertRaises(FaaSError) as raised:
                HTTPProvider().invoke(invocation)
        self.assertEqual(raised.exception.code, "provider_unavailable")
        self.assertTrue(raised.exception.transient)
        missing = FaaSInvocation("http", "echo", "sync", {}, 1, "id", 1,
            {"endpoint": "https://functions.example/invoke",
             "header_env": {"Authorization": "DAGON_FAAS_MISSING_TOKEN"}})
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(FaaSError) as raised:
            HTTPProvider().invoke(missing)
        self.assertEqual(raised.exception.code, "authentication")

    def test_checkpoint_reuse_does_not_reinvoke_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow = Workflow("checkpoint", config={"batch": {
                "remove_dir": False, "scratch_dir_base": temporary}})
            task = DagonTask(TaskType.FAAS, "invoke", provider="mock", function="echo",
                outputs={"result": "result.json"}, provider_options={"mock": {"response": {
                    "status": "succeeded", "outputs": {"result": {"ok": True}}}}})
            workflow.add_task(task)
            provider = MockProvider()
            with patch("dagon.faas.get_provider", return_value=provider) as factory:
                task.execute()
                first_working_dir = task.working_dir
                task.execute()
            self.assertEqual(factory.call_count, 1)
            self.assertTrue(task.fair_checkpoint_reused)
            self.assertEqual(task.working_dir, first_working_dir)

    def test_workflow_json_round_trip_recreates_faas_task(self):
        config = {"batch": {"remove_dir": False, "scratch_dir_base": "/tmp"}}
        workflow = Workflow("round-trip", config=config)
        workflow.add_task(DagonTask(TaskType.FAAS, "invoke", provider="mock", function="echo",
                                    inputs={"value": 4}))
        restored = Workflow("placeholder", config=config, jsonload=workflow.as_json())
        self.assertIsInstance(restored.tasks[0], FaaSTask)
        self.assertEqual(restored.tasks[0].function, "echo")
        self.assertEqual(restored.tasks[0].inputs, {"value": 4})

    def test_cwl_export_uses_namespaced_runner_hint(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow = Workflow("export", config={})
            workflow.add_task(DagonTask(TaskType.FAAS, "invoke", provider="mock", function="echo"))
            target = Path(temporary, "workflow.cwl")
            workflow.saveAsCWL(str(target))
            payload = json.loads(target.read_text())
            tool = payload["steps"]["invoke"]["run"]
            self.assertEqual(tool["baseCommand"], ["python", "-m", "dagon.faas_runner"])
            self.assertIn("dagon:FaaSInvocation", tool["hints"])
            self.assertEqual(payload["$namespaces"]["dagon"], "https://dagonstar.org/cwl#")

    def test_fair_records_service_attempts_output_and_redacts_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow = Workflow("faas-fair", config={"batch": {
                "remove_dir": False, "scratch_dir_base": temporary}})
            fair_dir = Path(temporary, "fair")
            workflow.enable_fair(FairProfile(title="FaaS run", description="test", creators=[Agent(name="Lab")],
                license="Apache-2.0", access_policy=AccessPolicy(), output_dir=str(fair_dir)))
            workflow.add_task(DagonTask(TaskType.FAAS, "invoke", provider="mock", function="echo",
                outputs={"result": "result.json"}, provider_options={"mock": {"response": {
                    "status": "succeeded", "outputs": {"result": {"ok": True}}}}}))
            workflow.run()
            run = json.loads(fair_dir.joinpath("run.json").read_text())
            self.assertEqual(run["tasks"]["invoke"]["execution"]["model"], "faas")
            self.assertEqual(run["artifacts"][0]["checksum"][:7], "sha256:")
            crate = json.loads(fair_dir.joinpath("ro-crate-metadata.json").read_text())
            self.assertTrue(any("Service" in item.get("@type", []) for item in crate["@graph"]))


if __name__ == "__main__":
    unittest.main()
