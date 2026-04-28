import unittest
from unittest.mock import patch, MagicMock, call
from dagon.apptainer_task import ApptainerTask, RemoteApptainerTask
import subprocess
import os
import tempfile

class TestApptainerTask(unittest.TestCase):
    """Unit tests for ApptainerTask."""

    def setUp(self):
        """Set up mocks and test fixtures."""
        # Mock workflow
        self.mock_workflow = MagicMock()
        self.mock_workflow.get_scratch_dir_base.return_value = "/tmp"
        self.mock_workflow.logger = MagicMock()
        
        # Create task
        self.task = ApptainerTask(
            name="test_task",
            command="echo hola",
            image="docker://ubuntu:20.04",
            working_dir="/app",
            remove=True,
        )
        self.task.workflow = self.mock_workflow

    @patch("dagon.apptainer_task.subprocess.run")
    @patch("dagon.apptainer_task.os.makedirs")
    @patch("dagon.apptainer_task.uuid.uuid4")
    @patch("dagon.apptainer_task.time.time")
    def test_create_container_success(self, mock_time, mock_uuid, mock_makedirs, mock_subprocess):
        """Should create container successfully."""
        mock_time.return_value = 1234567890.0
        mock_uuid.return_value = MagicMock(hex="abcd1234")
        
        # Mock subprocess for build and overlay
        mock_subprocess.return_value = MagicMock(
            stdout="", 
            stderr="", 
            returncode=0
        )
        
        self.task.create_container()
        
        # Verify container was created
        self.assertIsNotNone(self.task.container_id)
        self.assertIsNotNone(self.task.sif_file)
        self.assertIsNotNone(self.task.overlay_file)
        self.assertIsNotNone(self.task.work_dir)
        
        # Verify directories were created
        self.assertTrue(mock_makedirs.called)

    @patch("dagon.apptainer_task.subprocess.run")
    @patch("dagon.apptainer_task.os.path.exists", return_value=True)
    def test_prepare_sif_image_existing_file(self, mock_exists, mock_subprocess):
        """Should use existing SIF file."""
        self.task.image = "/path/to/existing.sif"
        self.task.work_dir = "/tmp/work"
        
        self.task._prepare_sif_image()
        
        self.assertEqual(self.task.sif_file, "/path/to/existing.sif")
        mock_subprocess.assert_not_called()

    @patch("dagon.apptainer_task.subprocess.run")
    def test_prepare_sif_image_build_from_docker(self, mock_subprocess):
        """Should build SIF image from Docker Hub."""
        self.task.work_dir = "/tmp/work"
        self.task.name = "test"
        
        mock_subprocess.return_value = MagicMock(
            stdout="", 
            stderr="", 
            returncode=0
        )
        
        self.task._prepare_sif_image()
        
        self.assertTrue(self.task.sif_file.endswith(".sif"))
        mock_subprocess.assert_called_once()
        
        # Verify build command
        args = mock_subprocess.call_args[0][0]
        self.assertIn("apptainer", args)
        self.assertIn("build", args)

    @patch("dagon.apptainer_task.subprocess.run")
    def test_create_overlay(self, mock_subprocess):
        """Should create overlay file."""
        self.task.work_dir = "/tmp/work"
        self.task.container_id = "test-123"
        self.task.overlay_size = "512"
        
        mock_subprocess.return_value = MagicMock(
            stdout="", 
            stderr="", 
            returncode=0
        )
        
        self.task._create_overlay()
        
        self.assertTrue(self.task.overlay_file.endswith(".img"))
        
        # Verify overlay command
        args = mock_subprocess.call_args[0][0]
        self.assertIn("apptainer", args)
        self.assertIn("overlay", args)
        self.assertIn("create", args)

    @patch("dagon.apptainer_task.subprocess.run")
    def test_exec_in_container(self, mock_subprocess):
        """Should execute command in container."""
        self.task.sif_file = "/tmp/test.sif"
        self.task.overlay_file = "/tmp/overlay.img"
        self.task.work_dir = "/tmp/work"
        self.task.staging_dir = "/tmp/staging"
        self.task.bind_paths = []
        
        mock_subprocess.return_value = MagicMock(
            stdout="command output", 
            stderr="", 
            returncode=0
        )
        
        result = self.task.exec_in_container("echo test")
        
        self.assertEqual(result, "command output")
        
        # Verify exec command structure
        args = mock_subprocess.call_args[0][0]
        self.assertIn("apptainer", args)
        self.assertIn("exec", args)
        self.assertIn("--overlay", args)
        self.assertIn("bash", args)

    @patch("dagon.apptainer_task.subprocess.run")
    @patch("dagon.apptainer_task.os.path.exists", return_value=True)
    def test_export_file_to_staging(self, mock_exists, mock_subprocess):
        """Should export file from container to staging."""
        self.task.sif_file = "/tmp/test.sif"
        self.task.work_dir = "/tmp/work"
        self.task.staging_dir = "/tmp/staging"
        self.task.bind_paths = []
        
        mock_subprocess.return_value = MagicMock(
            stdout="", 
            stderr="", 
            returncode=0
        )
        
        staging_path = self.task.export_file_to_staging("/work/output.txt", "output.txt")
        
        self.assertTrue(staging_path.endswith("output.txt"))
        mock_subprocess.assert_called_once()

    @patch.object(ApptainerTask, 'exec_in_container')
    def test_import_file_from_staging(self, mock_exec):
        """Should import file from staging to container."""
        staging_path = "/tmp/staging/file.txt"
        
        with patch("dagon.apptainer_task.os.path.exists", return_value=True):
            self.task.import_file_from_staging(staging_path, "/work/file.txt")
        
        # Verify mkdir and cp commands were executed
        self.assertTrue(mock_exec.called)

    @patch("dagon.apptainer_task.shutil.copy2")
    @patch("dagon.apptainer_task.os.remove")
    def test_stage_in_success(self, mock_remove, mock_copy):
        """Should copy file between containers using staging."""
        src_task = ApptainerTask(
            name="src_task",
            command="echo src",
            image="docker://ubuntu:20.04"
        )
        src_task.container_id = "src-123"
        src_task.staging_dir = "/tmp/src_staging"
        src_task.sif_file = "/tmp/src.sif"
        src_task.work_dir = "/tmp/src_work"
        
        self.task.container_id = "dst-123"
        self.task.staging_dir = "/tmp/dst_staging"
        
        # Mock export and import methods
        with patch.object(src_task, 'export_file_to_staging', return_value="/tmp/src_staging/file.txt") as mock_export, \
             patch.object(self.task, 'import_file_from_staging') as mock_import:
            
            self.task.stage_in(src_task, "/work/input.txt", "/work/output.txt")
            
            mock_export.assert_called_once()
            mock_import.assert_called_once()
            mock_copy.assert_called_once()

    @patch("dagon.apptainer_task.shutil.rmtree")
    @patch("dagon.apptainer_task.os.path.exists", return_value=True)
    def test_cleanup_container(self, mock_exists, mock_rmtree):
        """Should clean up container files when remove=True."""
        self.task.remove = True
        self.task.work_dir = "/tmp/work"
        self.task.container_id = "test-123"
        
        self.task.cleanup_container()
        
        mock_rmtree.assert_called_once_with("/tmp/work")
        self.assertIsNone(self.task.container_id)
        self.assertIsNone(self.task.sif_file)

    @patch.object(ApptainerTask, 'exec_in_container')
    @patch("dagon.apptainer_task.Task.on_execute")
    def test_on_execute_success(self, mock_task_exec, mock_exec):
        """Should execute task successfully."""
        # Pre-create container to avoid double call
        self.task.container_id = "test-123"
        self.task.sif_file = "/tmp/test.sif"
        self.task.overlay_file = "/tmp/overlay.img"
        self.task.work_dir = "/tmp/work"
        self.task.staging_dir = "/tmp/staging"
        
        mock_exec.return_value = "result output"
        
        result = self.task.on_execute("script content", "script.sh")
        
        mock_exec.assert_called_once()
        self.assertTrue(self.task.executed)
        self.assertIn("output", result)

    @patch.object(ApptainerTask, 'cleanup_container')
    @patch("dagon.apptainer_task.Batch.on_garbage")
    def test_on_garbage(self, mock_batch_garbage, mock_cleanup):
        """Should call cleanup on garbage collection."""
        self.task.on_garbage()
        
        mock_cleanup.assert_called_once()
        mock_batch_garbage.assert_called_once()


class TestRemoteApptainerTask(unittest.TestCase):
    """Unit tests for RemoteApptainerTask."""

    def setUp(self):
        """Set up mocks for remote testing."""
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
        self.task = RemoteApptainerTask(
            name="remote_test",
            command="echo hi",
            ip="192.168.0.10",
            ssh_username="user",
            keypath="/path/key",
            image="docker://ubuntu:20.04",
        )
        self.task.workflow = self.mock_workflow

    def test_run_apptainer_command_success(self):
        """Should execute apptainer command successfully."""
        self.mock_ssh.execute_command.return_value = {"output": "ok", "code": 0}
        
        result = self.task._run_apptainer_command(["apptainer", "--version"])
        
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(result.returncode, 0)

    def test_run_apptainer_command_failure(self):
        """Should raise error when apptainer command fails."""
        self.mock_ssh.execute_command.return_value = {"output": "error", "code": 1}
        
        with self.assertRaises(subprocess.CalledProcessError):
            self.task._run_apptainer_command(["apptainer", "fail"], check=True)

    @patch("dagon.apptainer_task.uuid.uuid4")
    @patch("dagon.apptainer_task.time.time")
    def test_create_remote_container(self, mock_time, mock_uuid):
        """Should create container on remote machine."""
        mock_time.return_value = 1234567890.0
        mock_uuid.return_value = MagicMock(hex="abcd1234")
        
        # Set working_dir before calling create_container
        self.task.working_dir = "/remote/work"
        
        self.mock_ssh.execute_command.return_value = {"output": "exists", "code": 0}
        
        self.task.create_container()
        
        self.assertIsNotNone(self.task.container_id)
        self.assertIsNotNone(self.task.info)
        self.assertTrue(self.mock_ssh.execute_command.called)

    def test_prepare_sif_image_remote_existing(self):
        """Should use existing SIF file on remote machine."""
        self.task.image = "/remote/path/image.sif"
        self.mock_ssh.execute_command.return_value = {"output": "exists", "code": 0}
        
        self.task._prepare_sif_image()
        
        self.assertEqual(self.task.sif_file, "/remote/path/image.sif")

    def test_prepare_sif_image_remote_build(self):
        """Should build SIF image on remote machine."""
        self.task.container_id = "test-123"
        self.task.tmp_dir = "/tmp"
        
        # Mock build command and verification - need 3 calls total
        self.mock_ssh.execute_command.side_effect = [
            {"output": "", "code": 0},  # mkdir
            {"output": "Building...", "code": 0},  # build
            {"output": "exists", "code": 0},  # verification
        ]
        
        self.task._prepare_sif_image()
        
        self.assertIsNotNone(self.task.sif_file)
        self.assertTrue(self.task.sif_file.endswith(".sif"))

    def test_exec_in_remote_container(self):
        """Should execute command in remote container."""
        self.task.sif_file = "/tmp/test.sif"
        self.task.working_dir = "/work"
        self.task.staging_dir = "/staging"
        self.task.bind_paths = []
        
        self.mock_ssh.execute_command.return_value = {"output": "done", "code": 0}
        
        result = self.task.exec_in_container("ls /")
        
        self.assertEqual(result, "done")
        self.mock_ssh.execute_command.assert_called_once()

    def test_export_file_to_remote_staging(self):
        """Should export file to staging on remote machine."""
        self.task.working_dir = "/work"
        self.task.staging_dir = "/staging"
        
        self.mock_ssh.execute_command.side_effect = [
            {"output": "exists", "code": 0},  # file exists check
            {"output": "", "code": 0},  # copy command
            {"output": "exists", "code": 0},  # verify staging
        ]
        
        result = self.task.export_file_to_staging("output.txt", "output.txt")
        
        self.assertTrue(result.endswith("output.txt"))

    def test_import_file_from_remote_staging(self):
        """Should import file from staging on remote machine."""
        self.task.working_dir = "/work"
        
        self.mock_ssh.execute_command.return_value = {"output": "", "code": 0}
        
        self.task.import_file_from_staging("/staging/file.txt", "file.txt")
        
        # Verify mkdir and cp commands
        self.assertTrue(self.mock_ssh.execute_command.called)

    def test_remote_stage_in(self):
        """Should copy file between remote containers."""
        src_task = RemoteApptainerTask(
            name="src",
            command="echo src",
            ip="192.168.0.10",
            ssh_username="user",
            keypath="/path/key"
        )
        src_task.container_id = "src-123"
        src_task.staging_dir = "/staging"
        src_task.ssh_connection = self.mock_ssh
        
        self.task.container_id = "dst-123"
        self.task.staging_dir = "/staging"
        
        # Mock export and import methods
        with patch.object(src_task, 'export_file_to_staging', return_value="/staging/file.txt") as mock_export, \
             patch.object(self.task, 'import_file_from_staging') as mock_import:
            
            self.task.stage_in(src_task, "/work/input.txt", "/work/output.txt")
            
            mock_export.assert_called_once()
            mock_import.assert_called_once()

    def test_cleanup_remote_container(self):
        """Should clean up remote container files."""
        self.task.remove = True
        self.task.sif_file = "/tmp/sif/test.sif"
        self.task.staging_dir = "/staging"
        self.task.working_dir = "/work"
        
        self.mock_ssh.execute_command.return_value = {"output": "", "code": 0}
        
        self.task.cleanup_container()
        
        # Verify cleanup commands were executed
        self.assertTrue(self.mock_ssh.execute_command.called)
        self.assertIsNone(self.task.container_id)

    @patch.object(RemoteApptainerTask, 'create_container')
    @patch("dagon.apptainer_task.RemoteTask.on_execute")
    def test_remote_on_execute(self, mock_remote_exec, mock_create):
        """Should execute task on remote container."""
        self.task.working_dir = "/work"
        self.task.sif_file = "/tmp/test.sif"
        self.task.staging_dir = "/staging"
        
        self.mock_ssh.execute_command.side_effect = [
            {"output": '{"result": "done"}', "code": 0},  # apptainer exec
            {"output": "", "code": 0},  # find command
        ]
        
        result = self.task.on_execute("script.sh", "script.sh")
        
        mock_create.assert_called_once()
        self.assertTrue(self.task.executed)

    @patch.object(RemoteApptainerTask, 'cleanup_container')
    @patch("dagon.apptainer_task.RemoteTask.on_garbage")
    def test_remote_on_garbage(self, mock_remote_garbage, mock_cleanup):
        """Should call cleanup on garbage collection."""
        self.task.on_garbage()
        
        mock_remote_garbage.assert_called_once()
        mock_cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()