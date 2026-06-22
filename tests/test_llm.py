import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dagon.task import DagonTask, TaskType
from tests.helpers import make_workflow, minimal_config


class LLMTaskTests(unittest.TestCase):
    def test_factory_creates_llm_task(self):
        task = DagonTask(TaskType.LLM, "Ask", {"messages": []}, provider="test")
        self.assertEqual(type(task).__name__, "LLMTask")
        self.assertEqual(task.provider, "test")

    def test_serialization_uses_llm_schema_type(self):
        task = DagonTask(TaskType.LLM, "Ask", {"messages": []}, provider="test", params={"x": "y"})
        serialized = task.as_json()
        self.assertEqual(serialized["type"], "llm")
        self.assertEqual(serialized["provider"], "test")
        self.assertEqual(serialized["params"], {"x": "y"})

    def test_input_file_creates_dependency_and_is_interpolated(self):
        config = minimal_config()
        config["llm.test"] = {"endpoint": "https://llm.example.test", "api_key": "secret", "model": "test-model"}
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow("LLMWorkflow")
            workflow.cfg = config
            producer_dir = Path(directory, "producer")
            producer_dir.mkdir()
            (producer_dir / "report.txt").write_text("important data", encoding="utf-8")
            producer = DagonTask(TaskType.BATCH, "Produce", "echo ignored", working_dir=str(producer_dir))
            task = DagonTask(TaskType.LLM, "Ask", {
                "messages": [{"role": "user", "content": "Summarize: {report}"}],
            }, provider="test", input_files={"report": "workflow:///Produce/report.txt"}, working_dir=str(Path(directory, "ask")))
            workflow.add_task(producer)
            workflow.add_task(task)
            workflow.make_dependencies()
            self.assertEqual(task.prevs, [producer])

            with mock.patch("dagon.llm.urlopen") as urlopen:
                response = mock.MagicMock()
                response.read.return_value = b'{"choices": [{"message": {"content": "summary"}}]}'
                urlopen.return_value.__enter__.return_value = response
                task.execute()

            request = urlopen.call_args[0][0]
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["messages"][0]["content"], "Summarize: important data")
            self.assertTrue(Path(task.working_dir, "response.json").is_file())
            self.assertTrue(Path(task.working_dir, ".dagon", "inputs", "LLMWorkflow", "Produce", "report.txt").is_file())

    def test_provider_requires_configuration(self):
        workflow = make_workflow()
        task = DagonTask(TaskType.LLM, "Ask", {"messages": []}, provider="missing")
        workflow.add_task(task)
        with self.assertRaisesRegex(ValueError, "not configured"):
            task._provider_config()

    def test_inline_workflow_reference_is_replaced_by_staged_text(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow("LLMWorkflow")
            workflow.cfg["llm.test"] = {"endpoint": "https://llm.example.test", "api_key": "secret", "model": "test-model"}
            producer_dir = Path(directory, "producer")
            producer_dir.mkdir()
            (producer_dir / "data.txt").write_text("inline data", encoding="utf-8")
            producer = DagonTask(TaskType.BATCH, "Produce", "echo ignored", working_dir=str(producer_dir))
            task = DagonTask(TaskType.LLM, "Ask", {"messages": [{"role": "user", "content": "Read workflow:///Produce/data.txt"}]}, provider="test", working_dir=str(Path(directory, "ask")))
            workflow.add_task(producer)
            workflow.add_task(task)
            workflow.make_dependencies()
            with mock.patch("dagon.llm.urlopen") as urlopen:
                response = mock.MagicMock()
                response.read.return_value = b'{}'
                urlopen.return_value.__enter__.return_value = response
                task.execute()
            payload = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
            self.assertEqual(payload["messages"][0]["content"], "Read inline data")

    def test_rejects_parent_directory_in_input_reference(self):
        task = DagonTask(TaskType.LLM, "Ask", {"messages": []}, provider="test")
        with self.assertRaisesRegex(ValueError, "stay inside"):
            task._parse_reference("workflow:///Produce/../secret")
