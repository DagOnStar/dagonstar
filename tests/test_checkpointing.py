import tempfile
import unittest
from pathlib import Path

from dagon.task import DagonTask, TaskType

from tests.helpers import make_workflow


class CheckpointingTests(unittest.TestCase):
    def test_completed_checkpoint_reuses_existing_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed_dir = Path(tmp) / "completed-task"
            completed_dir.mkdir()

            workflow = make_workflow("Checkpointed")
            task = DagonTask(TaskType.BATCH, "A", "exit 99")
            workflow.add_task(task)
            workflow.checkpoints = {
                "Checkpointed.A": {
                    "working_dir": str(completed_dir),
                    "workflow": "Checkpointed",
                    "name": "A",
                    "code": 0,
                }
            }

            task.execute()

            self.assertEqual(task.working_dir, str(completed_dir))


if __name__ == "__main__":
    unittest.main()
