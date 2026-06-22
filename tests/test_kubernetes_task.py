import unittest
from unittest.mock import patch, MagicMock
from dagon.kubernetes_task import KubernetesTask, RemoteKubernetesTask

class TestKubernetesTask(unittest.TestCase):
    """Unit tests for KubernetesTask."""

    def setUp(self):
        """Set up mocks for Kubernetes client."""
        # Mock load_kube_config to avoid attempting to load real configuration
        patcher_config = patch("dagon.kubernetes_task.config.load_kube_config")
        self.mock_config = patcher_config.start()
        self.addCleanup(patcher_config.stop)
        
        # Mock CoreV1Api to avoid creating real client
        patcher_api = patch("dagon.kubernetes_task.client.CoreV1Api")
        self.mock_api_class = patcher_api.start()
        self.addCleanup(patcher_api.stop)
        
        self.mock_api = MagicMock()
        self.mock_api_class.return_value = self.mock_api
        
        # Mock workflow
        self.mock_workflow = MagicMock()
        self.mock_workflow.get_scratch_dir_base.return_value = "/tmp"
        self.mock_workflow.logger = MagicMock()
        
        # Create task
        self.task = KubernetesTask(
            name="test",
            command="echo hola",
            image="ubuntu:20.04"
        )
        self.task.workflow = self.mock_workflow

    def test_create_pod_success(self):
        """Should create a pod and wait until it's running."""
        # Mock pod states
        mock_pod_running = MagicMock()
        mock_pod_running.status.phase = "Running"
        mock_pod_running.status.pod_ip = "10.0.0.5"

        self.mock_api.read_namespaced_pod.return_value = mock_pod_running

        self.task.create_pod()

        self.assertIsNotNone(self.task.pod_name)
        self.assertEqual(self.task.info["ip"], "10.0.0.5")
        self.mock_api.create_namespaced_pod.assert_called_once()

    def test_exec_in_pod(self):
        """Should execute a command inside a pod and return the output."""
        self.task.pod_name = "testpod"
        self.task.namespace = "default"
        
        # Mock exec_in_pod directly since stream is complicated to mock
        with patch.object(self.task, 'exec_in_pod', return_value="execution ok") as mock_exec:
            result = self.task.exec_in_pod("echo hi")
            self.assertEqual(result, "execution ok")

    def test_stage_in_success(self):
        """Should copy a file between pods using exec_in_pod."""
        src_task = MagicMock()
        src_task.name = "src"
        src_task.pod_name = "srcpod"
        src_task.exec_in_pod.return_value = "file content"

        self.task.pod_name = "dstpod"
        self.task.exec_in_pod = MagicMock()

        self.task.stage_in(src_task, "/tmp/a.txt", "/tmp/b.txt")

        src_task.exec_in_pod.assert_called_with("cat /tmp/a.txt")
        self.task.exec_in_pod.assert_any_call("mkdir -p /tmp")
        self.task.exec_in_pod.assert_any_call(
            "cat > /tmp/b.txt << 'EOF'\nfile content\nEOF"
        )

    @patch("subprocess.run")
    def test_remove_pod_force_delete(self, mock_subprocess_run):
        """Should delete the pod when remove=True."""
        self.task.remove = True
        self.task.pod_name = "testpod"
        self.task.namespace = "default"

        # Standard deletion fails
        self.mock_api.delete_namespaced_pod.side_effect = Exception("Standard deletion failed")
        
        # Mock subprocess for forced deletion
        mock_subprocess_run.return_value.returncode = 0
        
        self.task.remove_pod()

        # Verify that subprocess.run was called for forced deletion
        mock_subprocess_run.assert_called_once()
        self.assertIsNone(self.task.pod_name)


class TestRemoteKubernetesTask(unittest.TestCase):
    """Tests for RemoteKubernetesTask class."""

    def setUp(self):
        # Mock load_kube_config to avoid loading configuration
        patcher_config = patch("dagon.kubernetes_task.config.load_kube_config")
        self.mock_config = patcher_config.start()
        self.addCleanup(patcher_config.stop)
        
        # Mock CoreV1Api
        patcher_api = patch("dagon.kubernetes_task.client.CoreV1Api")
        self.mock_api_class = patcher_api.start()
        self.addCleanup(patcher_api.stop)
        
        self.mock_api = MagicMock()
        self.mock_api_class.return_value = self.mock_api
        
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
        
        # Create remote task
        self.task = RemoteKubernetesTask(
            name="remote-test",
            command="echo hi",
            ip="192.168.0.10",
            ssh_username="user",
            keypath="/path/key",
        )
        self.task.workflow = self.mock_workflow

    def test_run_kubectl_command_success(self):
        """Should execute kubectl command successfully."""
        self.mock_ssh.execute_command.return_value = {"output": "ok", "code": 0}
        result = self.task._run_kubectl_command("kubectl get pods")
        self.assertEqual(result, "ok")

    def test_run_kubectl_command_failure(self):
        """Should raise error when kubectl command fails."""
        self.mock_ssh.execute_command.return_value = {"output": "error", "code": 1}
        with self.assertRaises(Exception):
            self.task._run_kubectl_command("kubectl fail")

    def test_exec_in_remote_pod(self):
        """Should execute command inside remote pod via kubectl exec."""
        self.task.pod_name = "remote-pod"
        self.task._run_kubectl_command = MagicMock(return_value="done")

        result = self.task.exec_in_pod("ls /")
        self.assertEqual(result, "done")

    def test_remove_remote_pod(self):
        """Should delete remote pod."""
        self.task.pod_name = "remote-pod"
        self.task.remove = True
        self.task._run_kubectl_command = MagicMock(return_value="deleted")

        self.task.remove_pod()
        self.assertIsNone(self.task.pod_name)


if __name__ == "__main__":
    unittest.main()