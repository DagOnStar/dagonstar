import json
import tempfile
import unittest
from pathlib import Path

from dagon import Workflow
from dagon.iot import IoTTask, IoTUnknownOutcomeError
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config


class IoTTaskTests(unittest.TestCase):
    def workflow(self, name, directory):
        config = minimal_config()
        config["batch"]["scratch_dir_base"] = directory
        return Workflow(name, config=config)

    def test_factory_validation_and_stable_serialization(self):
        task = DagonTask(TaskType.IOT, "sensor", operation="observe", provider="mock",
                         request={"events": [{"value": 20.1}]}, completion={"mode": "first_event"})
        self.assertIsInstance(task, IoTTask)
        self.assertEqual(task.as_json()["type"], "iot")
        with self.assertRaises(ValueError):
            DagonTask(TaskType.IOT, "bad", operation="subscribe", completion={"mode": "first_event"})
        with self.assertRaises(ValueError):
            DagonTask(TaskType.IOT, "unbounded", operation="observe", completion={})

    def test_nested_references_create_one_edge_and_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self.workflow("nested", directory)
            producer = DagonTask(TaskType.BATCH, "producer", "mkdir -p outputs; echo '{\"x\":1}' > outputs/value.json")
            consumer = DagonTask(TaskType.IOT, "consumer", operation="configure", provider="mock",
                request={"desired": [{"a": "workflow:///producer/outputs/value.json"},
                                     "workflow:///producer/outputs/value.json"]},
                completion={"mode": "reported_state", "path": "applied", "equals": True,
                            "timeout_seconds": 2}, delivery={"idempotent": True},
                outputs={"configuration": "outputs/configuration.json"})
            workflow.add_task(producer); workflow.add_task(consumer)
            workflow.make_dependencies()
            self.assertEqual(consumer.prevs, [producer])
            self.assertEqual(producer.reference_count, 1)
            workflow.run()
            self.assertTrue(Path(consumer.working_dir, "outputs/configuration.json").is_file())
            self.assertIn("workflow:///producer", json.dumps(consumer.as_json()))
            self.assertNotIn(consumer.working_dir, json.dumps(consumer.as_json()))

    def test_completed_checkpoint_requires_valid_output_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self.workflow("checkpoint", directory)
            task = DagonTask(TaskType.IOT, "sensor", operation="observe", request={"events": [{"value": 1}]},
                             completion={"mode": "first_event"}, outputs={"observations": "outputs/o.json"})
            workflow.add_task(task); workflow.run()
            self.assertTrue(task.reuse_checkpoint())
            Path(task.working_dir, "outputs/o.json").unlink()
            self.assertFalse(task.reuse_checkpoint())

    def test_unknown_non_idempotent_actuation_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = self.workflow("actuate", directory)
            task = DagonTask(TaskType.IOT, "valve", operation="actuate", action="close",
                completion={"mode": "acknowledged", "timeout_seconds": 2}, delivery={"max_attempts": 1},
                provider_options={"unknown_outcome": True})
            workflow.add_task(task)
            with self.assertRaises(IoTUnknownOutcomeError):
                task.execute()
            self.assertEqual(workflow.checkpoints["actuate.valve"]["outcome_certainty"], "unknown")

    def test_json_round_trip_and_redaction(self):
        workflow = Workflow("roundtrip", config=minimal_config())
        task = DagonTask(TaskType.IOT, "sensor", operation="observe", request={"events": []},
            completion={"mode": "first_event"}, credential_ref="SENSOR_TOKEN",
            provider_options={"token": "secret-sentinel"})
        workflow.add_task(task)
        encoded = json.dumps(workflow.as_json(), sort_keys=True)
        self.assertNotIn("secret-sentinel", encoded)
        restored = Workflow("placeholder", config=minimal_config(), jsonload=workflow.as_json())
        self.assertEqual(restored.tasks[0].as_json()["iot"], task.as_json()["iot"])

    def test_cwl_uses_runner_outputs_namespace_and_redacted_hint(self):
        workflow = Workflow("iot-cwl", config=minimal_config())
        task = DagonTask(TaskType.IOT, "sensor", operation="observe",
            request={"events": [{"value": 1}]}, completion={"mode": "first_event"},
            outputs={"observations": "outputs/o.json"}, provider_options={"token": "sentinel"})
        workflow.add_task(task)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "iot.cwl")
            workflow.saveAsCWL(target)
            payload = json.loads(target.read_text())
        tool = payload["steps"]["sensor"]["run"]
        self.assertEqual(tool["baseCommand"], ["dagon-iot-runner", "run"])
        self.assertIn("dagon:IoTTask", tool["hints"])
        self.assertEqual(tool["outputs"]["observations"]["outputBinding"]["glob"], "outputs/o.json")
        self.assertNotIn("sentinel", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
