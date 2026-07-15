import builtins
import importlib
import sys
import unittest
from unittest import mock

from dagon.batch import Batch, RemoteBatch, RemoteSlurm, Slurm
from dagon.remote import CloudTask, RemoteTask
from dagon.task import DagonTask, TaskType


class OptionalIntegrationTests(unittest.TestCase):
    def test_batch_factory_returns_remote_batch_when_ip_is_configured(self):
        with mock.patch("dagon.remote.SSHManager") as ssh_manager:
            task = Batch("RemoteBatch", "echo remote", ip="192.0.2.10", ssh_username="user", keypath="/tmp/key")

        self.assertIsInstance(task, RemoteBatch)
        ssh_manager.assert_called_once_with("user", "192.0.2.10", "/tmp/key", port=22)

    def test_remote_task_passes_custom_ssh_port_to_connection(self):
        with mock.patch("dagon.remote.SSHManager") as ssh_manager:
            task = RemoteTask(
                "Remote", "echo remote", ip="192.0.2.10", ssh_username="user",
                keypath="/tmp/key", ssh_port=2200,
            )

        self.assertEqual(task.ssh_port, 2200)
        ssh_manager.assert_called_once_with("user", "192.0.2.10", "/tmp/key", port=2200)

    def test_remote_task_does_not_open_ssh_without_complete_connection_info(self):
        with mock.patch("dagon.remote.SSHManager") as ssh_manager:
            task = RemoteTask("Remote", "echo remote", ip="192.0.2.10", keypath="/tmp/key")

        self.assertIsNone(task.ssh_connection)
        ssh_manager.assert_not_called()

    def test_slurm_command_includes_configured_scheduler_options(self):
        task = Slurm(
            "Analysis",
            "python run.py",
            comment=["first", "second"],
            partition="debug",
            ntasks=4,
            memory=2048,
            time="01:30:00",
            nodes=2,
            ntasks_per_node=2,
            working_dir="/scratch/work",
        )

        command = task.generate_command("launcher.sh")

        self.assertIn("sbatch --comment=first --comment=second", command)
        self.assertIn("--partition=debug", command)
        self.assertIn("--ntasks=4", command)
        self.assertIn("--mem=2048", command)
        self.assertIn("--time=01:30:00", command)
        self.assertIn("--nodes=2", command)
        self.assertIn("--ntasks-per-node=2", command)
        self.assertIn("-J Analysis", command)
        self.assertIn("-D /scratch/work", command)
        self.assertIn("-W /scratch/work/.dagon/launcher.sh", command)

    def test_slurm_command_quotes_all_user_controlled_values(self):
        task = Slurm("job name; touch /tmp/pwned", "echo ok", comment="hello $(id)",
                     partition="debug queue", working_dir="/scratch/work dir")
        command = task.generate_command("launch script.sh")
        self.assertIn("'--comment=hello $(id)'", command)
        self.assertIn("'--partition=debug queue'", command)
        self.assertIn("'job name; touch /tmp/pwned'", command)
        self.assertIn("'/scratch/work dir/.dagon/launch script.sh'", command)

    def test_slurm_factory_returns_remote_slurm_when_ip_is_configured(self):
        with mock.patch("dagon.remote.SSHManager") as ssh_manager:
            task = Slurm(
                "RemoteSlurm",
                "hostname",
                partition="compute",
                ntasks=2,
                memory=1024,
                ip="192.0.2.20",
                ssh_username="user",
                keypath="/tmp/key",
            )

        self.assertIsInstance(task, RemoteSlurm)
        ssh_manager.assert_called_once_with("user", "192.0.2.20", "/tmp/key", port=22)

    def test_cloud_task_defers_provider_import_and_connection_until_execute(self):
        task = CloudTask(
            "Cloud",
            "hostname",
            provider="dummy",
            ssh_username="cloud-user",
            key_options={"key_path": "/tmp/key"},
            instance_id="i-123",
            instance_flavour={"image": "image", "size": "size"},
            instance_name="named-instance",
            stop_instance=True,
        )

        self.assertEqual(task.provider, "dummy")
        self.assertEqual(task.instance_id, "i-123")
        self.assertIsNone(task.node)
        self.assertIsNone(task.ssh_connection)
        self.assertTrue(task.stop_instance)

    def test_cloud_task_reports_missing_optional_extra(self):
        task = CloudTask(
            "Cloud", "hostname", provider="dummy", ssh_username="cloud-user",
            key_options={"key_path": "/tmp/key"},
        )
        task.workflow = mock.Mock(name="workflow")
        task.workflow.name = "workflow"
        real_import = builtins.__import__

        def import_without_libcloud(name, *args, **kwargs):
            if name == "libcloud" or name.startswith("libcloud."):
                error = ImportError("No module named 'libcloud'")
                error.name = "libcloud"
                raise error
            return real_import(name, *args, **kwargs)

        previous_cloud = sys.modules.pop("dagon.cloud", None)
        try:
            with mock.patch("builtins.__import__", side_effect=import_without_libcloud):
                with self.assertRaisesRegex(ImportError, r"dagonstar\[cloud\]"):
                    task.execute()
        finally:
            if previous_cloud is not None:
                sys.modules["dagon.cloud"] = previous_cloud
            else:
                sys.modules.pop("dagon.cloud", None)

    def test_docker_task_reports_missing_optional_extra(self):
        real_import = builtins.__import__

        def import_without_docker(name, *args, **kwargs):
            if name == "docker":
                raise ImportError("No module named docker")
            return real_import(name, *args, **kwargs)

        previous_module = sys.modules.pop("dagon.docker_task", None)
        previous_docker = sys.modules.pop("docker", None)
        try:
            with mock.patch("builtins.__import__", side_effect=import_without_docker):
                with self.assertRaisesRegex(ImportError, r"dagonstar\[docker\]"):
                    DagonTask(TaskType.DOCKER, "Docker", "echo hi", image="python:3.12")
        finally:
            if previous_module is not None:
                sys.modules["dagon.docker_task"] = previous_module
            else:
                sys.modules.pop("dagon.docker_task", None)
            if previous_docker is not None:
                sys.modules["docker"] = previous_docker
            importlib.invalidate_caches()


if __name__ == "__main__":
    unittest.main()
