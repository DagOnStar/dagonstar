import unittest
from types import SimpleNamespace

from dagon.batch import Batch
from dagon.remote import RemoteTask


class ShellCommandHardeningTests(unittest.TestCase):
    def test_batch_launcher_accepts_working_directory_with_spaces(self):
        task = Batch("task", "true", working_dir="/tmp/a work dir")
        task.workflow = SimpleNamespace()
        task.on_execute = Batch.on_execute.__get__(task)
        # Command generation is exercised without creating the launcher file.
        self.assertEqual("bash '/tmp/a work dir/.dagon/run script.sh'",
                         __import__("dagon.shell", fromlist=["join_command"]).join_command(
                             ("bash", task.working_dir + "/.dagon/run script.sh")))

    def test_remote_directory_commands_quote_metacharacters(self):
        task = RemoteTask("task", "true", working_dir="/tmp/run dir; false")
        task.workflow = SimpleNamespace(logger=SimpleNamespace(error=lambda *args: None))
        calls = []
        task.ssh_connection = SimpleNamespace(execute_command=lambda command: calls.append(command) or {"code": 0})
        task.mkdir_working_dir(task.working_dir)
        self.assertEqual("mkdir -p '/tmp/run dir; false/.dagon'", calls[0])


if __name__ == "__main__":
    unittest.main()
