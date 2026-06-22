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


if __name__ == "__main__":
    unittest.main()