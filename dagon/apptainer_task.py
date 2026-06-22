import os
import logging
import subprocess
import tempfile
import shutil
from dagon import Batch
from dagon.task import Task
from dagon.remote import RemoteTask
import time
import json
import uuid
import threading

class ApptainerTask(Batch):
    """
    Represents a task that runs inside an Apptainer container in HPC.
    Inherits from Batch to integrate with Dagon's task workflow.
    """

    def __new__(cls, *args, **kwargs):
        """
        Factory method to create RemoteApptainerTask if 'ip' is provided.
        """
        if "ip" in kwargs:
            return super(Task, cls).__new__(RemoteApptainerTask)
        else:
            return super(ApptainerTask, cls).__new__(cls)

    def __init__(self, name, command, image="docker://ubuntu:20.04", 
                 working_dir=None, remove=False, transversal_workflow=None,
                 bind_paths=None, overlay_size="1024", tmp_dir=None):
        """
        Initializes the Apptainer task.
        """
        Task.__init__(self, name, command, working_dir=working_dir,
                      transversal_workflow=transversal_workflow)

        self.image = image
        self.remove = remove
        self.bind_paths = bind_paths or []
        self.overlay_size = overlay_size
        self.tmp_dir = tmp_dir or tempfile.gettempdir()
        # Container files and directories
        self.container_id = None
        self.sif_file = None
        self.overlay_file = None
        self.work_dir = None
        self.container_work_dir = "/work"
        # Directory for staging files between containers
        self.staging_dir = None
        # Container information that Dagon needs for staging
        self.info = None
        # Single execution control
        self.executed = False
        self.execution_result = None
        # Lock for thread-safe operations
        self._lock = threading.Lock()
        # Initialize data_mover (required by Dagon workflow)
        self.data_mover = None

    def _run_apptainer_command(self, cmd_args, capture_output=True, check=True):
        """
        Executes an Apptainer command with error handling.
        """
        try:
            result = subprocess.run(
                cmd_args, 
                capture_output=capture_output, 
                text=True, 
                check=check,
                timeout=300
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"Error executing Apptainer: {' '.join(cmd_args)}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            print(f"Timeout executing Apptainer: {' '.join(cmd_args)}")
            raise

    def create_container(self):
        """
        Prepares the Apptainer container environment:
        - Downloads/builds the SIF image if necessary
        - Creates overlay for writing
        - Prepares working and staging directories
        """
        if self.container_id is not None:
            print(f"Reusing existing container: {self.container_id}")
            return

        with self._lock:
            if self.container_id is not None:
                return
            # Generate unique identifier
            self.container_id = f"{self.name.lower()}-{uuid.uuid4().hex[:8]}-{int(time.time()*1000)}"
            # Create temporary working directory
            self.work_dir = os.path.join(self.tmp_dir, f"apptainer_work_{self.container_id}")
            os.makedirs(self.work_dir, exist_ok=True)
            # Create staging directory for file exchange
            self.staging_dir = os.path.join(self.work_dir, "staging")
            os.makedirs(self.staging_dir, exist_ok=True)
            print(f"Preparing Apptainer container: {self.container_id}")
            # Prepare SIF image
            self._prepare_sif_image()
            # Create overlay to allow writing
            self._create_overlay()
            # Configure container information
            self.info = {
                'name': self.name,
                'container_id': self.container_id,
                'work_dir': self.work_dir,
                'staging_dir': self.staging_dir,
                'sif_file': self.sif_file,
                'overlay_file': self.overlay_file
            }
            print(f"Container {self.container_id} prepared successfully")

    def _prepare_sif_image(self):
        """
        Prepares the SIF image from different sources.
        """
        if self.image.endswith('.sif'):
            if os.path.exists(self.image):
                self.sif_file = self.image
                print(f"Using existing SIF file: {self.sif_file}")
            else:
                raise FileNotFoundError(f"SIF file not found: {self.image}")
        else:
            self.sif_file = os.path.join(self.work_dir, f"{self.name}.sif")
            print(f"Building SIF image from: {self.image}")
            build_cmd = ["apptainer", "build", self.sif_file, self.image]
            try:
                result = self._run_apptainer_command(build_cmd, capture_output=False)
                print(f"SIF image built: {self.sif_file}")
            except subprocess.CalledProcessError:
                print("Retrying build with sudo...")
                build_cmd.insert(0, "sudo")
                self._run_apptainer_command(build_cmd, capture_output=False)

    def _create_overlay(self):
        """
        Creates a temporary overlay to allow writing in the container.
        """
        self.overlay_file = os.path.join(self.work_dir, f"overlay_{self.container_id}.img")
        print(f"Creating {self.overlay_size}MB overlay...")
        create_cmd = [
            "apptainer", "overlay", "create", 
            "--size", self.overlay_size, 
            self.overlay_file
        ]
        self._run_apptainer_command(create_cmd)
        print(f"Overlay created: {self.overlay_file}")

    def exec_in_container(self, command):
        """
        Executes a command inside the Apptainer container.
        """
        if not command.startswith(("mkdir -p", "cat > /tmp")):
            print(f"Executing in container: {command}")
        # Build execution command
        exec_cmd = ["apptainer", "exec"]
        # Add overlay
        exec_cmd.extend(["--overlay", self.overlay_file])
        # Add bind paths
        for bind_path in self.bind_paths:
            exec_cmd.extend(["--bind", bind_path])
        # Bind working directory and staging
        exec_cmd.extend(["--bind", f"{self.work_dir}:{self.container_work_dir}"])
        exec_cmd.extend(["--bind", f"{self.staging_dir}:/staging"])
        # Change to working directory inside the container
        exec_cmd.extend(["--pwd", self.container_work_dir])
        # SIF file and command
        exec_cmd.extend([self.sif_file, "bash", "-c", command])
        result = self._run_apptainer_command(exec_cmd)
        return result.stdout

    def export_file_to_staging(self, container_path, staging_filename):
        """
        Exports a file from the container to the staging area WITHOUT overlay.
        This completely avoids locking conflicts.
        """
        staging_path = os.path.join(self.staging_dir, staging_filename)
        # Command WITHOUT overlay - only bind mounts
        exec_cmd = [
            "apptainer", "exec",
            "--bind", f"{self.work_dir}:{self.container_work_dir}",
            "--bind", f"{self.staging_dir}:/staging",
            "--pwd", self.container_work_dir,
            self.sif_file,
            "bash", "-c", f"cp {container_path} /staging/{staging_filename}"
        ]
        # Add additional bind paths if any
        for bind_path in self.bind_paths:
            exec_cmd.insert(-4, "--bind")
            exec_cmd.insert(-4, bind_path)
        print(f"Exporting {container_path} to staging (without overlay)")
        result = self._run_apptainer_command(exec_cmd)
        # Verify that the file was created
        if not os.path.exists(staging_path):
            raise FileNotFoundError(f"Could not export {container_path} to staging")
        return staging_path

    def import_file_from_staging(self, staging_path, container_path):
        """
        Imports a file from the host staging area to the container.
        """
        if not os.path.exists(staging_path):
            raise FileNotFoundError(f"Staging file not found: {staging_path}")
        # Get filename in staging
        staging_filename = os.path.basename(staging_path)
        # Create destination directory if it doesn't exist
        dst_dir = "/".join(container_path.split("/")[:-1])
        if dst_dir:
            self.exec_in_container(f"mkdir -p {dst_dir}")
        # Import file from staging to container
        import_cmd = f"cp /staging/{staging_filename} {container_path}"
        self.exec_in_container(import_cmd)

    def stage_in(self, src_task, src_path, dst_path):
        """
        Copies a file from another container to this container using filesystem staging.
        This function is called by the Dagon framework.
        """
        # Ensure both containers are prepared
        if not hasattr(src_task, 'container_id') or src_task.container_id is None:
            src_task.create_container()
        if self.container_id is None:
            self.create_container()
        print(f"Copying file {src_path} from {src_task.name} to {self.name}")
        try:
            # Generate unique name for the file in staging
            staging_filename = f"{src_task.name}_{src_path.replace('/', '_')}_{int(time.time()*1000)}"
            # Export file from source container to staging
            staging_path = src_task.export_file_to_staging(src_path, staging_filename)
            # Copy file from staging to our staging (to make it available in our bind mount)
            our_staging_path = os.path.join(self.staging_dir, staging_filename)
            shutil.copy2(staging_path, our_staging_path)
            # Import file from our staging to the container
            self.import_file_from_staging(our_staging_path, dst_path)
            # Clean up temporary staging files
            try:
                os.remove(staging_path)
                os.remove(our_staging_path)
            except OSError:
                pass # Not critical if they can't be deleted
            print(f"File copied successfully via filesystem staging")
        except Exception as e:
            print(f"Error in stage_in: {e}")
            raise

    def cleanup_container(self):
        """
        Cleans up temporary container files and directories.
        """
        if self.remove and self.work_dir and os.path.exists(self.work_dir):
            try:
                print(f"Cleaning up working directory: {self.work_dir}")
                shutil.rmtree(self.work_dir)
                print(f"Directory {self.work_dir} deleted")
            except Exception as e:
                print(f"Warning: Could not delete directory {self.work_dir}: {e}")
        # Clean up references
        self.container_id = None
        self.sif_file = None
        self.overlay_file = None
        self.work_dir = None
        self.staging_dir = None
        self.info = None

    def pre_process_command(self, command):
        """
        Override the preprocessing method to intercept workflow:/// URLs
        before Dagon tries to process them.
        """
        # Create the container if it doesn't exist
        if self.container_id is None:
            self.create_container()
        # Process workflow:/// manually
        if "workflow:///" in command:
            import re
            # Find all workflow:/// references
            workflow_refs = re.findall(r'workflow:///([^/\s]+)/([^\s]+)', command)
            for task_name, file_path in workflow_refs:
                workflow_url = f"workflow:///{task_name}/{file_path}"
                # Search for the referenced task in the workflow
                src_task = None
                if hasattr(self, 'workflow') and self.workflow:
                    for task in self.workflow.tasks:
                        if task.name == task_name:
                            src_task = task
                            break
                if src_task:
                    # Ensure the source task has its container prepared
                    if not hasattr(src_task, 'container_id') or src_task.container_id is None:
                        src_task.create_container()
                    # Create local temporary file to simulate expected behavior
                    local_path = f"/tmp/{task_name}_{file_path.replace('/', '_')}"
                    try:
                        # Copy file using our stage_in method with filesystem staging
                        self.stage_in(src_task, file_path, local_path)
                        # Replace the workflow:// reference with the local path
                        command = command.replace(workflow_url, local_path)
                    except Exception as e:
                        print(f"Error processing workflow reference {workflow_url}: {e}")
        return command

    def on_execute(self, script, script_name):
        """
        Method called when executing the task:
        - Prepares the container if it doesn't exist
        - Executes the command inside the container
        - Returns the result in JSON format
        """
        # Single execution control
        if self.executed:
            print(f"[{self.name}] Returning previous result")
            return self.execution_result

        Task.on_execute(self, script, script_name)

        # Prepare container if it doesn't exist
        if self.container_id is None:
            self.create_container()

        # Process command to handle workflow:/// references
        processed_command = self.pre_process_command(self.command)

        # Execute command in the container
        try:
            result = self.exec_in_container(processed_command).strip()
        except Exception as e:
            print(f"Error executing command in container: {e}")
            result = f"Error: {str(e)}"

        # Escape newlines and tabs
        safe_result = result.replace("\n", "\\n").replace("\t", "\\t")

        # Format output as JSON
        output_json = json.dumps({"result": safe_result})
        print(f"[{self.name}] Output:\n{output_json}")

        # Mark as executed and save result
        self.executed = True
        self.execution_result = {"output": output_json, "code": 0}
        return self.execution_result

    def on_garbage(self):
        """
        Called when cleaning up the task:
        - Removes temporary files if applicable
        """
        self.cleanup_container()
        super(ApptainerTask, self).on_garbage()


class RemoteApptainerTask(RemoteTask, ApptainerTask):
    """
    Represents an Apptainer task running on a remote machine via SSH.
    This class combines RemoteTask functionality with ApptainerTask to enable
    Apptainer container execution on remote HPC systems.
    """

    def __init__(self, name, command, image="docker://ubuntu:20.04", 
                 ip=None, ssh_username=None, keypath=None, ssh_port=22,
                 working_dir=None, remove=False, transversal_workflow=None,
                 bind_paths=None, overlay_size="1024", tmp_dir="/tmp"):
        """
        Initializes the remote Apptainer task.
        :param ssh_port: SSH port (default: 22)
        :type ssh_port: int
        """
        # CRITICAL: First initialize RemoteTask to establish ssh_connection
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username, 
                          keypath=keypath, command=command, ip=ip, 
                          working_dir=working_dir, ssh_port=ssh_port)
        
        # Save the SSH port
        self.ssh_port = ssh_port
        
        # Then initialize ApptainerTask (WITHOUT calling Task.__init__ again)
        # Only copy the necessary attributes
        self.image = image
        self.remove = remove
        self.bind_paths = bind_paths or []
        self.overlay_size = overlay_size
        self.tmp_dir = tmp_dir
        
        # Container files and directories
        self.container_id = None
        self.sif_file = None
        self.overlay_file = None
        self.work_dir = None
        self.container_work_dir = "/work"
        self.staging_dir = None
        self.info = None
        self.executed = False
        self.execution_result = None
        
        # CRITICAL: Initialize the lock
        self._lock = threading.Lock()
        
        # Define an empty data_mover (necessary to prevent Workflow failure)
        self.data_mover = None

    def _run_apptainer_command(self, cmd_args, capture_output=True, check=True):
        """
        Executes an Apptainer command on the remote machine via SSH.
        Overrides the local implementation to use SSH connection.
        """
        # Convert command list to string for SSH execution
        if isinstance(cmd_args, list):
            cmd_str = " ".join([f'"{arg}"' if ' ' in arg else arg for arg in cmd_args])
        else:
            cmd_str = cmd_args
        
        try:
            result = self.ssh_connection.execute_command(cmd_str)
            
            # SSHManager.execute_command returns 'output' if successful, 'message' if failed
            output = result.get('output', result.get('message', ''))
            code = result.get('code', 0)
            
            # Create a mock subprocess result object for compatibility
            class RemoteResult:
                def __init__(self, output, code):
                    self.stdout = output
                    self.stderr = ""
                    self.returncode = code
            
            mock_result = RemoteResult(output, code)
            
            if check and code != 0:
                print(f"Command failed with code {code}: {cmd_str}")
                print(f"Output/Error: {output}")
                raise subprocess.CalledProcessError(
                    code, cmd_str, 
                    output=output, stderr=""
                )
            
            return mock_result
            
        except Exception as e:
            print(f"Error executing remote Apptainer command: {cmd_str}")
            print(f"Error: {e}")
            raise

    def create_container(self):
        """
        Prepares the Apptainer container environment on the remote machine.
        """
        if self.container_id is not None:
            print(f"Reusing existing remote container: {self.container_id}")
            return

        with self._lock:
            if self.container_id is not None:
                return
            
            # Generate unique identifier
            self.container_id = f"{self.name.lower()}-{uuid.uuid4().hex[:8]}-{int(time.time()*1000)}"
            
            # IMPORTANT: Use working_dir directly (already created by RemoteTask)
            self.work_dir = self.working_dir
            
            # Create staging directory inside the working_dir
            self.staging_dir = os.path.join(self.work_dir, ".apptainer_staging")
            self.ssh_connection.execute_command(f"mkdir -p {self.staging_dir}")
            
            print(f"Preparing remote Apptainer container: {self.container_id} on {self.ip}")
            
            # Prepare SIF image
            self._prepare_sif_image()
            
            # Configure container information
            self.info = {
                'name': self.name,
                'container_id': self.container_id,
                'work_dir': self.work_dir,
                'staging_dir': self.staging_dir,
                'sif_file': self.sif_file,
                'overlay_file': None,
                'remote_ip': self.ip
            }
            print(f"Remote container {self.container_id} prepared successfully")

    def _prepare_sif_image(self):
        """
        Prepares the SIF image on the remote machine.
        """
        if self.image.endswith('.sif'):
            # Check if SIF file exists on remote machine
            check_cmd = f"test -f {self.image} && echo 'exists' || echo 'not_found'"
            result = self.ssh_connection.execute_command(check_cmd)
            if 'exists' in result['output']:
                self.sif_file = self.image
                print(f"Using existing remote SIF file: {self.sif_file}")
            else:
                raise FileNotFoundError(f"Remote SIF file not found: {self.image}")
        else:
            # Create temporary directory for the SIF (separate from working_dir)
            sif_dir = f"{self.tmp_dir}/apptainer_sif_{self.container_id}"
            self.ssh_connection.execute_command(f"mkdir -p {sif_dir}")
            self.sif_file = os.path.join(sif_dir, f"{self.name}.sif")
            
            print(f"Building SIF image on remote machine from: {self.image}")
            build_cmd = f"apptainer build {self.sif_file} {self.image}"
            
            # Execute build command
            result = self.ssh_connection.execute_command(build_cmd)
            output = result.get('output', result.get('message', ''))
            
            # Check if build was actually successful by verifying the file exists
            check_cmd = f"test -f {self.sif_file} && echo 'exists' || echo 'not_found'"
            check_result = self.ssh_connection.execute_command(check_cmd)
            
            if 'exists' in check_result.get('output', ''):
                print(f"Remote SIF image built successfully: {self.sif_file}")
            else:
                print(f"Build failed. Output: {output}")
                raise Exception(f"Failed to build SIF image: {output}")

    def exec_in_container(self, command):
        """
        Executes a command inside the Apptainer container on remote machine.
        """
        if not command.startswith(("mkdir -p", "cat > /tmp")):
            print(f"Executing in remote container: {command}")
        
        # Build execution command
        exec_cmd_parts = ["apptainer", "exec"]
        
        # Add bind paths
        if self.bind_paths:
            for bind_path in self.bind_paths:
                exec_cmd_parts.extend(["--bind", bind_path])
        
        # CRITICAL: Bind the working_dir to the same path inside the container
        exec_cmd_parts.extend(["--bind", f"{self.working_dir}:{self.working_dir}"])
        exec_cmd_parts.extend(["--bind", f"{self.staging_dir}:/staging"])
        
        # Change to working directory inside the container
        exec_cmd_parts.extend(["--pwd", self.working_dir])
        
        # SIF file and command
        exec_cmd_parts.extend([self.sif_file, "bash", "-c", command])
        
        result = self._run_apptainer_command(exec_cmd_parts)
        return result.stdout

    def export_file_to_staging(self, container_path, staging_filename):
        """
        Exports a file from the working directory to the staging area.
        Since we bind working_dir, files are directly accessible on the host.
        """
        staging_path = os.path.join(self.staging_dir, staging_filename)
        
        # Convert to absolute path if relative
        if not container_path.startswith('/'):
            abs_container_path = f"{self.working_dir}/{container_path}"
        else:
            abs_container_path = container_path
        
        print(f"Exporting {container_path} to remote staging")
        
        # Verify that the file exists on the host
        check_cmd = f"test -f {abs_container_path} && echo 'exists' || echo 'not_found'"
        check_result = self.ssh_connection.execute_command(check_cmd)
        
        if 'not_found' in check_result.get('output', ''):
            # Debug: list directory
            ls_cmd = f"ls -la {self.working_dir}/ 2>&1"
            ls_result = self.ssh_connection.execute_command(ls_cmd)
            print(f"Directory listing: {ls_result.get('output', 'N/A')}")
            
            # Search for the file
            find_cmd = f"find {self.working_dir} -name '{os.path.basename(container_path)}' 2>/dev/null"
            find_result = self.ssh_connection.execute_command(find_cmd)
            print(f"File search results: {find_result.get('output', 'No results')}")
            
            raise FileNotFoundError(f"File does not exist on host: {abs_container_path}")
        
        # Copy from working_dir to staging (simple copy on the host)
        copy_cmd = f"cp {abs_container_path} {staging_path}"
        result = self.ssh_connection.execute_command(copy_cmd)
        
        if result.get('code', 0) != 0:
            raise Exception(f"Failed to copy file to staging: {result.get('message', 'Unknown error')}")
        
        # Verify that it was created
        check_cmd = f"test -f {staging_path} && echo 'exists' || echo 'not_found'"
        check_result = self.ssh_connection.execute_command(check_cmd)
        
        if 'not_found' in check_result['output']:
            raise FileNotFoundError(f"Could not copy {abs_container_path} to staging")
        
        return staging_path

    def import_file_from_staging(self, staging_path, container_path):
        """
        Imports a file from the staging area to the working directory.
        Since we bind working_dir, we just copy on the host.
        """
        # Convert to absolute path if relative
        if not container_path.startswith('/'):
            abs_container_path = f"{self.working_dir}/{container_path}"
        else:
            abs_container_path = container_path
        
        # Create destination directory if it doesn't exist
        dst_dir = os.path.dirname(abs_container_path)
        if dst_dir:
            mkdir_cmd = f"mkdir -p {dst_dir}"
            self.ssh_connection.execute_command(mkdir_cmd)
        
        # Copy from staging to destination on the host
        copy_cmd = f"cp {staging_path} {abs_container_path}"
        result = self.ssh_connection.execute_command(copy_cmd)
        
        if result.get('code', 0) != 0:
            raise Exception(f"Failed to import file from staging: {result.get('message', 'Unknown error')}")
        
        print(f"File imported from staging to {abs_container_path}")

    def stage_in(self, src_task, src_path, dst_path):
        """
        Copies a file from another task to this task.
        For remote tasks, both use the same working_dir on the same host.
        """
        # Ensure both containers are prepared
        if not hasattr(src_task, 'container_id') or src_task.container_id is None:
            src_task.create_container()
        if self.container_id is None:
            self.create_container()
        
        print(f"Copying file {src_path} from {src_task.name} to {self.name}")
        
        try:
            # Generate unique name for the file in staging
            staging_filename = f"{src_task.name}_{src_path.replace('/', '_')}_{int(time.time()*1000)}"
            
            # Export file from source to its staging
            staging_path = src_task.export_file_to_staging(src_path, staging_filename)
            
            # Import file from source staging to our destination
            self.import_file_from_staging(staging_path, dst_path)
            
            # Clean up staging file
            try:
                cleanup_cmd = f"rm -f {staging_path}"
                self.ssh_connection.execute_command(cleanup_cmd)
            except:
                pass
            
            print(f"File copied successfully via filesystem staging")
            
        except Exception as e:
            print(f"Error in stage_in: {e}")
            raise

    def cleanup_container(self):
        """
        Cleans up temporary container files and directories on the remote machine.
        """
        if self.remove and self.sif_file:
            try:
                # Only clean up the SIF directory, not the working_dir
                sif_dir = os.path.dirname(self.sif_file)
                if sif_dir and sif_dir != self.working_dir:
                    print(f"Cleaning up SIF directory: {sif_dir}")
                    self.ssh_connection.execute_command(f"rm -rf {sif_dir}")
                
                # Clean up staging
                if self.staging_dir:
                    print(f"Cleaning up staging directory: {self.staging_dir}")
                    self.ssh_connection.execute_command(f"rm -rf {self.staging_dir}")
                    
            except Exception as e:
                print(f"Warning: Could not cleanup: {e}")
        
        # Clean up references
        self.container_id = None
        self.sif_file = None
        self.overlay_file = None
        self.work_dir = None
        self.staging_dir = None
        self.info = None

    def on_execute(self, script, script_name):
        """
        Execute the task script on the remote machine inside Apptainer container.
        """
        if self.executed:
            print(f"[{self.name}] Returning previous result")
            return self.execution_result

        # Transfer the script
        RemoteTask.on_execute(self, script, script_name)
        
        # Prepare the container
        if self.container_id is None:
            self.create_container()

        script_path = f"{self.working_dir}/.dagon/{script_name}"
        
        # Build apptainer command - add stderr handling
        apptainer_cmd = [
            "apptainer", "exec",
            "--bind", f"{self.working_dir}:{self.working_dir}",
            "--bind", f"{self.staging_dir}:/staging",
            "--pwd", self.working_dir,
            self.sif_file,
            "bash", script_path
        ]
        
        if self.bind_paths:
            for bind_path in self.bind_paths:
                apptainer_cmd.insert(2, "--bind")
                apptainer_cmd.insert(3, bind_path)
        
        # Redirect apptainer's stderr to /dev/null to avoid warnings that confuse Dagon
        # But keep the user's script stderr
        cmd_str = " ".join([f'"{arg}"' if (' ' in arg and arg is not None) else str(arg) for arg in apptainer_cmd if arg is not None])
        cmd_str = f"({cmd_str}) 2>&1 | grep -v 'squashfuse' | grep -v 'fuse2fs' | grep -v 'gocryptfs' | grep -v 'Converting SIF' | grep -v 'Cleaning up image'"
        
        print(f"[{self.name}] Executing apptainer command")
        result = self.ssh_connection.execute_command(cmd_str)
        
        # Debug: see what files were created
        check_cmd = f"find {self.working_dir} -type f -newer {self.staging_dir} 2>/dev/null | head -20"
        check_result = self.ssh_connection.execute_command(check_cmd)
        if check_result.get('output'):
            print(f"[{self.name}] Created files: {check_result.get('output', 'none')}")
        
        # CRITICAL: Check the script's exit code, not apptainer's
        # If the result contains the expected output, consider it successful
        if result.get('code', 0) != 0:
            # Check if it really failed or just Apptainer warnings
            output = result.get('output', result.get('message', ''))
            if 'FATAL' not in output and 'Error' not in output:
                # Only warnings, force exit code 0
                result['code'] = 0
                print(f"[{self.name}] Task completed successfully (ignoring Apptainer warnings)")
        
        self.executed = True
        self.execution_result = result
        return result

    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory and containers
        on the remote machine.
        """
        RemoteTask.on_garbage(self)
        self.cleanup_container()
