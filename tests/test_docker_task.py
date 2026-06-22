import unittest
from unittest.mock import patch, MagicMock
from dagon.docker_task import DockerTask, DockerRemoteTask


class TestDockerTask(unittest.TestCase):
    """Unit tests for DockerTask."""

    def setUp(self):
        # Mock docker.from_env to avoid creating real Docker client
        patcher_client = patch("dagon.docker_task.docker.from_env")
        self.mock_docker_from_env = patcher_client.start()
        self.addCleanup(patcher_client.stop)

        # Fake docker client
        self.mock_client = MagicMock()
        self.mock_docker_from_env.return_value = self.mock_client

        # Fake workflow with minimal interface
        self.mock_workflow = MagicMock()
        self.mock_workflow.get_scratch_dir_base.return_value = "/tmp"
        self.mock_workflow.logger = MagicMock()

        # Create the DockerTask instance
        self.task = DockerTask(
            name="test_task",
            command="echo hola",
            image="ubuntu:20.04",
            working_dir="/app",
            remove=True,
        )
        self.task.workflow = self.mock_workflow

    def test_pull_image_success(self):
        """Should pull image successfully."""
        self.task.pull_image("ubuntu:20.04")
        self.mock_client.images.pull.assert_called_with("ubuntu:20.04")
        self.mock_workflow.logger.info.assert_called_once()

    def test_pull_image_failure(self):
        """Should log an error if pulling image fails."""
        self.mock_client.images.pull.side_effect = Exception("Docker error")
        self.task.pull_image("fakeimage:latest")
        self.mock_workflow.logger.error.assert_called_once()

    def test_create_container_success(self):
        """Should create and return a docker container."""
        mock_container = MagicMock(id="abc123")
        self.mock_client.containers.run.return_value = mock_container

        container = self.task.create_container()

        self.assertEqual(container.id, "abc123")
        self.mock_client.containers.run.assert_called_once()
        self.mock_workflow.logger.info.assert_called()

    def test_create_container_failure(self):
        """Should raise exception when container creation fails."""
        self.mock_client.containers.run.side_effect = Exception("Run failed")

        with self.assertRaises(Exception):
            self.task.create_container()

    def test_get_running_container_success(self):
        """Should return a running container by ID."""
        mock_container = MagicMock(id="cont123")
        self.mock_client.containers.get.return_value = mock_container
        self.task.container_id = "cont123"

        result = self.task.get_running_container()

        self.assertEqual(result.id, "cont123")
        self.mock_client.containers.get.assert_called_with("cont123")

    def test_get_running_container_failure(self):
        """Should raise exception if container not found."""
        self.mock_client.containers.get.side_effect = Exception("Not found")
        self.task.container_id = "unknown"

        with self.assertRaises(Exception):
            self.task.get_running_container()

    def test_remove_container_with_remove_true(self):
        """Should stop and remove container."""
        mock_container = MagicMock()
        self.task.container = mock_container
        self.task.remove = True

        self.task.remove_container()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    def test_remove_container_with_remove_false(self):
        """Should stop container but not remove it."""
        mock_container = MagicMock()
        self.task.container = mock_container
        self.task.remove = False

        self.task.remove_container()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_not_called()

    def test_include_command_adds_exec_string(self):
        """Should format docker exec command correctly."""
        self.task.container = MagicMock(id="abc123")
        self.task.working_dir = "/app"

        result = self.task.include_command("ls -la")

        self.assertIn("docker exec -t abc123", result)
        self.assertIn("cd /app", result)

    @patch("dagon.docker_task.Batch.execute_command", return_value={"output": "ok", "code": 0})
    @patch("dagon.docker_task.Task.on_execute")
    def test_on_execute_runs_batch(self, mock_task_exec, mock_batch_exec):
        """Should execute task script via Batch."""
        result = self.task.on_execute("script content", "run.sh")

        mock_task_exec.assert_called_once()
        mock_batch_exec.assert_called_with("bash /app/.dagon/run.sh")
        self.assertEqual(result["output"], "ok")

    @patch("dagon.docker_task.DockerTask.remove_container")
    @patch("dagon.docker_task.Task.on_garbage")
    def test_on_garbage_removes_container(self, mock_task_garbage, mock_remove_container):
        """Should call parent garbage and remove container."""
        self.task.on_garbage()

        mock_task_garbage.assert_called_once()
        mock_remove_container.assert_called_once()


class TestDockerRemoteTask(unittest.TestCase):
    """Unit tests for DockerRemoteTask."""

    def setUp(self):
        # Mock docker.from_env() used in DockerTask.__init__
        patcher_from_env = patch("dagon.docker_task.docker.from_env")
        self.mock_from_env = patcher_from_env.start()
        self.addCleanup(patcher_from_env.stop)
        
        self.mock_docker_instance = MagicMock()
        self.mock_from_env.return_value = self.mock_docker_instance
        
        # Mock docker.DockerClient() used in DockerRemoteTask.__init__
        patcher_docker_client = patch("dagon.docker_task.docker.DockerClient")
        self.mock_docker_client_class = patcher_docker_client.start()
        self.addCleanup(patcher_docker_client.stop)
        
        self.mock_remote_docker_instance = MagicMock()
        self.mock_docker_client_class.return_value = self.mock_remote_docker_instance

        # Mock SSHManager to avoid real SSH connection
        patcher_ssh_manager = patch("dagon.remote.SSHManager")
        self.mock_ssh_manager_class = patcher_ssh_manager.start()
        self.addCleanup(patcher_ssh_manager.stop)
        
        # Mock SSH connection
        self.mock_ssh = MagicMock()
        self.mock_ssh_manager_class.return_value = self.mock_ssh
        
        # Mock workflow
        self.mock_workflow = MagicMock()
        self.mock_workflow.get_scratch_dir_base.return_value = "/tmp"
        self.mock_workflow.logger = MagicMock()

        # Instantiate the task
        self.task = DockerRemoteTask(
            name="remote_task",
            command="echo hola",
            image="ubuntu:20.04",
            ip="192.168.1.10",
            ssh_username="user",
            keypath="/path/to/key",
            working_dir="/home/user/work",
        )
        
        # Assign the workflow
        self.task.workflow = self.mock_workflow

    def test_on_execute_runs_remote_command(self):
        """Should execute remote bash command."""
        self.mock_ssh.execute_command.return_value = {"output": "done", "code": 0}

        result = self.task.on_execute("launcher.sh", "script.sh")

        self.assertEqual(result["output"], "done")
        self.mock_ssh.execute_command.assert_called_with("bash /home/user/work/.dagon/script.sh")

    @patch("dagon.docker_task.DockerRemoteTask.remove_container")
    @patch("dagon.docker_task.RemoteTask.on_garbage")
    def test_on_garbage_cleans_remote(self, mock_remote_garbage, mock_remove):
        """Should call remote garbage and remove container."""
        self.task.on_garbage()

        mock_remote_garbage.assert_called_once()
        mock_remove.assert_called_once()



if __name__ == "__main__":
    unittest.main()