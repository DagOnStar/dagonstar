import json
import tempfile
import unittest
from pathlib import Path

from dagon.task import DagonTask, TaskType
from tests.helpers import make_workflow, minimal_config


class NativeTaskTests(unittest.TestCase):
    def test_local_native_task_stages_workflow_file_and_writes_result(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimal_config()
            config["batch"]["scratch_dir_base"] = directory
            workflow = make_workflow("Native")
            workflow.cfg = config
            source = DagonTask(TaskType.BATCH, "source", "mkdir -p data; printf '2\\n3\\n' > data/input.txt")
            native = DagonTask(TaskType.NATIVE, "scale", "tests.native_functions:scale_file",
                               inputs={"input_file": "workflow:///source/data/input.txt", "scale": 2.5},
                               outputs={"output_file": "scaled.txt"})
            workflow.add_task(source)
            workflow.add_task(native)
            workflow.run()

            self.assertEqual(native.status.name, "FINISHED")
            self.assertEqual(Path(native.working_dir, "outputs/scaled.txt").read_text(), "5.0\n7.5\n")
            self.assertEqual(json.loads(Path(native.working_dir, ".dagon/native_result.json").read_text()),
                             {"count": 2, "scale": 2.5})
            self.assertTrue(Path(native.working_dir, "inputs/input_file/input.txt").is_file())

    def test_invalid_output_and_missing_parameter_fail_early(self):
        with self.assertRaisesRegex(ValueError, "relative"):
            DagonTask(TaskType.NATIVE, "bad", "tests.native_functions:needs_value",
                      outputs={"output_file": "../escape"})
        with self.assertRaisesRegex(ValueError, "incompatible"):
            DagonTask(TaskType.NATIVE, "bad", "tests.native_functions:needs_value")

    def test_non_importable_function_and_slurm_command_are_validated(self):
        with self.assertRaisesRegex(ValueError, "not importable"):
            DagonTask(TaskType.NATIVE, "bad", "no_such_module:fn")
        task = DagonTask(TaskType.NATIVE, "scheduled", "tests.native_functions:needs_value",
                         inputs={"value": 1}, executor="slurm", resources={"partition": "debug", "ntasks": 2})
        task.working_dir = "/tmp/native-scheduled"
        command = task.generate_slurm_command("native_launcher.sh")
        self.assertIn("sbatch", command)
        self.assertIn("--partition=debug", command)
        self.assertIn("--ntasks=2", command)

    def test_native_serialization_uses_native_schema(self):
        task = DagonTask(TaskType.NATIVE, "native", "tests.native_functions:needs_value",
                         inputs={"value": 1})
        payload = task.as_json()
        self.assertEqual(payload["type"], "native")
        self.assertEqual(payload["function"], "tests.native_functions:needs_value")


if __name__ == "__main__":
    unittest.main()
