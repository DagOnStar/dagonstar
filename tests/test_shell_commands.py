import unittest
from types import SimpleNamespace
from unittest import mock

from dagon.batch import Batch
from dagon.communication.ssh import SSHManager
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

    def test_ssh_create_file_quotes_directory_and_avoids_heredoc_collision(self):
        manager = SSHManager.__new__(SSHManager)
        calls = []
        manager.execute_command = lambda command: calls.append(command) or {"code": 0}

        with mock.patch("dagon.communication.ssh.secrets.token_hex", side_effect=["collision", "safe"]):
            manager.create_file("/tmp/a dir; false/run.sh", "echo before\nDAGON_EOF_collision\necho after")

        self.assertEqual("mkdir -p '/tmp/a dir; false'", calls[0])
        self.assertIn("<< 'DAGON_EOF_safe'", calls[1])
        self.assertTrue(calls[1].endswith("\nDAGON_EOF_safe"))

    def test_ssh_execute_command_preserves_success_with_stderr(self):
        class Channel:
            @staticmethod
            def recv_exit_status():
                return 0

        stdout = SimpleNamespace(channel=Channel(), readlines=lambda: ["done\n"])
        stderr = SimpleNamespace(readlines=lambda: ["warning\n"])
        manager = SSHManager.__new__(SSHManager)
        manager.connection = SimpleNamespace(exec_command=lambda command: (None, stdout, stderr))

        result = manager.execute_command("command")

        self.assertEqual(0, result["code"])
        self.assertIn("warning", result["error"])

    @mock.patch("dagon.communication.ssh.is_port_open", return_value=True)
    @mock.patch("dagon.communication.ssh.SSHClient")
    def test_ssh_connection_rejects_unknown_host_keys(self, ssh_client, _is_port_open):
        manager = SSHManager.__new__(SSHManager)
        manager.host = "example.test"
        manager.port = 2222
        manager.username = "worker"
        manager.keypath = None

        manager.get_ssh_connection()

        client = ssh_client.return_value
        client.load_system_host_keys.assert_called_once_with()
        policy = client.set_missing_host_key_policy.call_args.args[0]
        self.assertEqual("RejectPolicy", type(policy).__name__)
        client.connect.assert_called_once_with("example.test", port=2222, username="worker")


if __name__ == "__main__":
    unittest.main()
