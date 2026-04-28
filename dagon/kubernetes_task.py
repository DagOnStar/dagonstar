import os
import logging
from dagon import Batch
from dagon.task import Task
from dagon.remote import RemoteTask
from kubernetes import client, config
from kubernetes.stream import stream
from kubernetes.client.rest import ApiException
import time
import json
import uuid
import threading

# Reduce Kubernetes logs
logging.getLogger('kubernetes.client.rest').setLevel(logging.WARNING)

class KubernetesTask(Batch):
    """
    Represents a task that runs inside a Kubernetes pod.
    Inherits from Batch to integrate with Dagon's task workflow.
    """

    def __new__(cls, *args, **kwargs):
        """
        Factory method to create RemoteKubernetesTask if 'ip' is provided.
        """
        if "ip" in kwargs:
            return super(Task, cls).__new__(RemoteKubernetesTask)
        else:
            return super(KubernetesTask, cls).__new__(cls)

    def __init__(self, name, command, image="ubuntu:20.04", namespace="default",
                 working_dir=None, remove=False, transversal_workflow=None, cleanup_timeout=30,
                 volumes=None, devices=None, privileged=False):
        """
        Initializes the Kubernetes task.

        Args:
            name (str): Name of the task.
            command (str): Command to execute inside the pod.
            image (str): Container image to use.
            namespace (str): Kubernetes namespace.
            working_dir (str, optional): Working directory for the task.
            remove (bool): If True, removes the pod upon completion.
            transversal_workflow: Transversal workflow if applicable.
            volumes (list): List of volume mounts in format ["host_path:container_path", ...]
            devices (list): List of device mounts in format ["/dev/device:/dev/device", ...]
            privileged (bool): Run container in privileged mode (needed for device access)
        """
        # Initialize the base Dagon task
        Task.__init__(self, name, command, working_dir=working_dir,
                      transversal_workflow=transversal_workflow)

        # Load Kubernetes configuration (from ~/.kube/config)
        config.load_kube_config()

        # API for managing pods
        self.v1 = client.CoreV1Api()

        self.image = image
        self.namespace = namespace
        self.remove = remove
        self.cleanup_timeout = cleanup_timeout
        self.volumes = volumes or []
        self.devices = devices or []
        self.privileged = privileged

        # Assigned when the pod is created
        self.pod_name = None
        # Pod information that Dagon needs for staging
        self.info = None

        # Single execution control
        self.executed = False
        self.execution_result = None
        
        # CRITICAL: Initialize data_mover (required by Dagon workflow)
        self.data_mover = None

    def create_pod(self):
        """
        Creates a pod in Kubernetes only if it doesn't already exist (avoids duplicates).

        - The pod is kept in 'sleep infinity' state to allow multiple executions.
        - Supports hostPath volumes and device mounts
        """
        if self.pod_name is not None:
            # Pod already exists, reuse it
            print(f"Reusing existing pod: {self.pod_name}")
            return

        # Generate a unique name using UUID and timestamp
        self.pod_name = f"{self.name.lower()}-{uuid.uuid4().hex[:8]}-{int(time.time()*1000)}"

        # Build container spec
        container_spec = {
            "name": "main",
            "image": self.image,
            "command": ["/bin/bash", "-c", "sleep infinity"],
        }

        # Add privileged mode if needed (required for device access)
        if self.privileged or self.devices:
            container_spec["securityContext"] = {"privileged": True}

        # Add volume mounts
        volume_mounts = []
        volumes = []
        
        # Process regular volumes
        for idx, vol in enumerate(self.volumes):
            if ':' in vol:
                host_path, container_path = vol.split(':', 1)
                vol_name = f"vol-{idx}"
                
                volume_mounts.append({
                    "name": vol_name,
                    "mountPath": container_path
                })
                
                volumes.append({
                    "name": vol_name,
                    "hostPath": {
                        "path": host_path,
                        "type": "DirectoryOrCreate"
                    }
                })
        
        # Process device mounts
        for idx, dev in enumerate(self.devices):
            if ':' in dev:
                host_dev, container_dev = dev.split(':', 1)
                dev_name = f"dev-{idx}"
                
                volume_mounts.append({
                    "name": dev_name,
                    "mountPath": container_dev
                })
                
                volumes.append({
                    "name": dev_name,
                    "hostPath": {
                        "path": host_dev,
                        "type": "CharDevice"
                    }
                })
        
        if volume_mounts:
            container_spec["volumeMounts"] = volume_mounts

        # Pod definition
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": self.pod_name, "labels": {"app": self.name}},
            "spec": {
                "containers": [container_spec],
                "restartPolicy": "Never"
            }
        }
        
        if volumes:
            pod_manifest["spec"]["volumes"] = volumes

        try:
            self.v1.create_namespaced_pod(namespace=self.namespace, body=pod_manifest)
            print(f"Pod created: {self.pod_name}")
        except Exception as e:
            print(f"Error creating pod {self.pod_name}: {e}")

        # Wait for the pod to be in 'Running' state and get IP
        print(f"Waiting for pod {self.pod_name} to be ready...")
        while True:
            pod = self.v1.read_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            if pod.status.phase == "Running":
                pod_ip = pod.status.pod_ip
                print(f"Pod {self.pod_name} ready with IP: {pod_ip}")
                # Configure pod information that Dagon needs
                self.info = {
                    'name': self.name,
                    'ip': pod_ip,
                    'pod_name': self.pod_name,
                    'namespace': self.namespace
                }
                break
            elif pod.status.phase == "Failed":
                raise Exception(f"Pod {self.pod_name} failed: {pod.status.message}")
            time.sleep(0.5)

    def exec_in_pod(self, command):
        """
        Executes a command inside the pod's main container.
        Args:
            command (str): Command to execute.

        Returns:
            str: Output of the executed command.
        """
        # Reduce logging, only show important commands
        if not command.startswith(("mkdir -p", "cat > /tmp")):
            print(f"Executing: {command}")
        resp = stream(self.v1.connect_get_namespaced_pod_exec,
                      self.pod_name,
                      self.namespace,
                      command=["/bin/bash", "-c", command],
                      stderr=True, stdin=False,
                      stdout=True, tty=False,
                      container="main")
        return resp

    def stage_in(self, src_task, src_path, dst_path):
        """
        Copies a file from another pod to this pod so that workflow:/// works.
        This function is called by the Dagon framework.
        """
        # Ensure both pods are created and information is available
        if not hasattr(src_task, 'pod_name') or src_task.pod_name is None:
            src_task.create_pod()
        if self.pod_name is None:
            self.create_pod()
        print(f"Copying file {src_path} from {src_task.name} to {self.name}")
        try:
            # Read file content in the source pod
            content = src_task.exec_in_pod(f"cat {src_path}")

            # Create destination folder if it doesn't exist
            dst_dir = "/".join(dst_path.split("/")[:-1])
            if dst_dir:
                self.exec_in_pod(f"mkdir -p {dst_dir}")

            # Write content to destination using heredoc to avoid issues with special characters
            escaped_content = content.replace("'", "'\"'\"'")
            self.exec_in_pod(f"cat > {dst_path} << 'EOF'\n{escaped_content}\nEOF")
            print(f"File copied successfully")
        except Exception as e:
            print(f"Error in stage_in: {e}")
            raise

    def remove_pod(self):
        """
        Removes the pod if `remove=True`, similar to `docker run --rm`.
        Protects against non-existent pods and performs forced cleanup if needed.
        """
        if not getattr(self, "remove", False):
            return

        if not getattr(self, "pod_name", None):
            return

        pod_to_delete = self.pod_name  # Save reference before cleanup

        try:
            # Method 1: Standard deletion first
            try:
                self.v1.delete_namespaced_pod(
                    name=pod_to_delete,
                    namespace=self.namespace,
                    body=client.V1DeleteOptions(grace_period_seconds=30)
                )
                print(f"Pod {pod_to_delete} deleted")
            except ApiException as e:
                if e.status == 404:
                    print(f"Pod {pod_to_delete} no longer exists")
                else:
                    # Method 2: Force immediate deletion if standard method fails
                    print(f"Standard deletion failed, forcing deletion of {pod_to_delete}")
                    self.v1.delete_namespaced_pod(
                        name=pod_to_delete,
                        namespace=self.namespace,
                        body=client.V1DeleteOptions(
                            grace_period_seconds=0,
                            propagation_policy='Background'
                        )
                    )
                    print(f"Pod {pod_to_delete} forcefully deleted")

        except ApiException as e:
            # Method 3: Last resort if API call fails entirely
            if e.status != 404:
                print(f"Warning: Could not delete pod {pod_to_delete}: {e.reason}")
            try:
                import subprocess
                result = subprocess.run(
                    [
                        "kubectl", "delete", "pod", pod_to_delete,
                        "-n", self.namespace,
                        "--force", "--grace-period=0"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    print(f"Pod {pod_to_delete} deleted using kubectl")
                else:
                    print(f"kubectl also failed for {pod_to_delete}: {result.stderr}")
            except Exception as kubectl_error:
                print(f"kubectl not available to clean up {pod_to_delete}: {kubectl_error}")

        except Exception as e:
            # Catch-all fallback for unexpected exceptions
            print(f"Unexpected error deleting pod {pod_to_delete}: {e}")
            try:
                import subprocess
                result = subprocess.run(
                    [
                        "kubectl", "delete", "pod", pod_to_delete,
                        "-n", self.namespace,
                        "--force", "--grace-period=0"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    print(f"Pod {pod_to_delete} deleted using kubectl")
                else:
                    print(f"kubectl also failed for {pod_to_delete}: {result.stderr}")
            except Exception as kubectl_error:
                print(f"kubectl not available to clean up {pod_to_delete}: {kubectl_error}")

        finally:
            # Clean up references regardless of result
            self.pod_name = None
            self.info = None

    def pre_process_command(self, command):
        """
        Override the preprocessing method to intercept workflow:/// URLs
        before Dagon tries to process them.
        """
        # Create the pod if it doesn't exist to ensure we have information available
        if self.pod_name is None:
            self.create_pod()
        # Process workflow:/// manually to avoid KeyError
        if "workflow:///" in command:
            import re
            # Find all workflow:/// references
            workflow_refs = re.findall(r'workflow:///([^/\s]+)/([^\s]+)', command)
            for task_name, file_path in workflow_refs:
                workflow_url = f"workflow:///{task_name}/{file_path}"  # Define ANTES del try
                # Search for the referenced task in the workflow
                src_task = None
                if hasattr(self, 'workflow') and self.workflow:
                    for task in self.workflow.tasks:
                        if task.name == task_name:
                            src_task = task
                            break
                if src_task:
                    # Ensure the source task has its pod created
                    if not hasattr(src_task, 'pod_name') or src_task.pod_name is None:
                        src_task.create_pod()
                    # Create local temporary file to simulate expected behavior
                    local_path = f"/tmp/{task_name}_{file_path.replace('/', '_')}"
                    try:
                        # Copy file using our stage_in method
                        self.stage_in(src_task, file_path, local_path)
                        # Replace the workflow:// reference with the local path
                        command = command.replace(workflow_url, local_path)
                    except Exception as e:
                        print(f"Error processing workflow reference {workflow_url}: {e}")
                        raise
        return command

    def on_execute(self, script, script_name):
        """
        Method called when executing the task:

        - Creates the pod if it doesn't exist.
        - Executes the command inside the pod.
        - Returns the result in JSON format, escaping newlines and tabs.
        """
        # Single execution control
        if self.executed:
            print(f"[{self.name}] Returning previous result")
            return self.execution_result

        Task.on_execute(self, script, script_name)

        # Create pod if it doesn't exist
        if self.pod_name is None:
            self.create_pod()

        # Process command to handle workflow:/// references
        processed_command = self.pre_process_command(self.command)

        # Execute command
        result = self.exec_in_pod(processed_command).strip()

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

        - Removes the pod if applicable.
        """
        self.remove_pod()
        super(KubernetesTask, self).on_garbage()


class RemoteKubernetesTask(RemoteTask, KubernetesTask):
    """
    Represents a Kubernetes task running on a remote machine via SSH.
    This class combines RemoteTask functionality with KubernetesTask to enable
    pod execution on remote Kubernetes clusters.
    """

    def __init__(self, name, command, image="ubuntu:20.04", namespace="default",
                 ip=None, ssh_username=None, keypath=None, ssh_port=22,
                 working_dir=None, remove=False, transversal_workflow=None,
                 volumes=None, devices=None, privileged=False):
        """
        Initializes the remote Kubernetes task.
        
        :param ssh_port: SSH port (default: 22)
        :type ssh_port: int
        :param volumes: List of volume mounts ["host_path:container_path", ...]
        :param devices: List of device mounts ["/dev/device:/dev/device", ...]
        :param privileged: Run container in privileged mode
        """
        # CRITICAL: First initialize RemoteTask to establish ssh_connection
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username,
                            keypath=keypath, command=command, ip=ip,
                            working_dir=working_dir, ssh_port=ssh_port)

        # Save the SSH port
        self.ssh_port = ssh_port

        # Then initialize KubernetesTask attributes (WITHOUT calling Task.__init__ again)
        self.image = image
        self.namespace = namespace
        self.remove = remove
        self.volumes = volumes or []
        self.devices = devices or []
        self.privileged = privileged

        # Pod information
        self.pod_name = None
        self.info = None
        self.executed = False
        self.execution_result = None

        # CRITICAL: Initialize the lock
        self._lock = threading.Lock()

        # CRITICAL: Define data_mover (necessary to prevent Workflow failure)
        self.data_mover = None

    def _run_kubectl_command(self, cmd_args):
        """
        Executes a kubectl command on the remote machine via SSH.
        """
        # Convert command list to string for SSH execution
        if isinstance(cmd_args, list):
            cmd_str = " ".join([f'"{arg}"' if ' ' in arg else arg for arg in cmd_args])
        else:
            cmd_str = cmd_args

        try:
            result = self.ssh_connection.execute_command(cmd_str)
            output = result.get('output', result.get('message', ''))
            code = result.get('code', 0)

            if code != 0:
                print(f"Command failed with code {code}: {cmd_str}")
                print(f"Output/Error: {output}")
                raise Exception(f"kubectl command failed: {output}")

            return output
        except Exception as e:
            print(f"Error executing remote kubectl command: {cmd_str}")
            print(f"Error: {e}")
            raise

    def create_pod(self):
        """
        Creates a pod in the remote Kubernetes cluster with volume and device support.
        """
        if self.pod_name is not None:
            print(f"Reusing existing remote pod: {self.pod_name}")
            return

        with self._lock:
            if self.pod_name is not None:
                return

            # Generate unique identifier
            self.pod_name = f"{self.name.lower()}-{uuid.uuid4().hex[:8]}-{int(time.time()*1000)}"

            print(f"Creating remote pod: {self.pod_name} on {self.ip}")

            # Build container spec
            container_spec = {
                "name": "main",
                "image": self.image,
                "command": ["/bin/bash", "-c", "sleep infinity"],
            }

            # Add privileged mode if needed (required for device access)
            if self.privileged or self.devices:
                container_spec["securityContext"] = {"privileged": True}

            # Add volume mounts
            volume_mounts = []
            volumes = []
            
            # Process regular volumes
            for idx, vol in enumerate(self.volumes):
                if ':' in vol:
                    host_path, container_path = vol.split(':', 1)
                    vol_name = f"vol-{idx}"
                    
                    volume_mounts.append({
                        "name": vol_name,
                        "mountPath": container_path
                    })
                    
                    volumes.append({
                        "name": vol_name,
                        "hostPath": {
                            "path": host_path,
                            "type": "DirectoryOrCreate"
                        }
                    })
            
            # Process device mounts
            for idx, dev in enumerate(self.devices):
                if ':' in dev:
                    host_dev, container_dev = dev.split(':', 1)
                    dev_name = f"dev-{idx}"
                    
                    volume_mounts.append({
                        "name": dev_name,
                        "mountPath": container_dev
                    })
                    
                    volumes.append({
                        "name": dev_name,
                        "hostPath": {
                            "path": host_dev,
                            "type": "CharDevice"
                        }
                    })
            
            if volume_mounts:
                container_spec["volumeMounts"] = volume_mounts

            # Create pod manifest as JSON
            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": self.pod_name, "labels": {"app": self.name}},
                "spec": {
                    "containers": [container_spec],
                    "restartPolicy": "Never"
                }
            }
            
            if volumes:
                pod_manifest["spec"]["volumes"] = volumes

            # Write manifest to temporary file on remote machine
            manifest_path = f"/tmp/{self.pod_name}-manifest.json"
            manifest_json = json.dumps(pod_manifest)
            
            # Escape for shell
            escaped_json = manifest_json.replace("'", "'\"'\"'")
            write_cmd = f"cat > {manifest_path} << 'EOF'\n{escaped_json}\nEOF"
            self.ssh_connection.execute_command(write_cmd)

            # Create pod using kubectl
            create_cmd = f"kubectl apply -f {manifest_path} -n {self.namespace}"
            self._run_kubectl_command(create_cmd)

            # Clean up manifest file
            self.ssh_connection.execute_command(f"rm -f {manifest_path}")

            # Wait for pod to be ready
            print(f"Waiting for remote pod {self.pod_name} to be ready...")
            max_wait = 300
            for _ in range(max_wait):
                check_cmd = f"kubectl get pod {self.pod_name} -n {self.namespace} -o jsonpath='{{.status.phase}}'"
                phase = self._run_kubectl_command(check_cmd).strip()
                
                if phase == "Running":
                    # Get pod IP
                    ip_cmd = f"kubectl get pod {self.pod_name} -n {self.namespace} -o jsonpath='{{.status.podIP}}'"
                    pod_ip = self._run_kubectl_command(ip_cmd).strip()
                    print(f"Remote pod {self.pod_name} ready with IP: {pod_ip}")
                    
                    self.info = {
                        'name': self.name,
                        'ip': pod_ip,
                        'pod_name': self.pod_name,
                        'namespace': self.namespace,
                        'remote_ip': self.ip
                    }
                    break
                elif phase == "Failed":
                    raise Exception(f"Remote pod {self.pod_name} failed")
                
                time.sleep(1)
            else:
                raise Exception(f"Timeout waiting for pod {self.pod_name} to be ready")

    def exec_in_pod(self, command):
        """
        Executes a command inside the remote pod.
        """
        if not command.startswith(("mkdir -p", "cat > /tmp")):
            print(f"Executing in remote pod: {command}")

        # Escape command for kubectl exec
        escaped_cmd = command.replace("'", "'\"'\"'")
        exec_cmd = f"kubectl exec {self.pod_name} -n {self.namespace} -- /bin/bash -c '{escaped_cmd}'"
        
        result = self._run_kubectl_command(exec_cmd)
        return result

    def stage_in(self, src_task, src_path, dst_path):
        """
        Copies a file from another pod to this pod on the remote cluster.
        """
        # Ensure both pods are created
        if not hasattr(src_task, 'pod_name') or src_task.pod_name is None:
            src_task.create_pod()
        if self.pod_name is None:
            self.create_pod()

        print(f"Copying file {src_path} from {src_task.name} to {self.name}")
        
        try:
            # Read file content from source pod
            content = src_task.exec_in_pod(f"cat {src_path}")

            # Create destination folder if it doesn't exist
            dst_dir = "/".join(dst_path.split("/")[:-1])
            if dst_dir:
                self.exec_in_pod(f"mkdir -p {dst_dir}")

            # Write content to destination using heredoc
            escaped_content = content.replace("'", "'\"'\"'")
            self.exec_in_pod(f"cat > {dst_path} << 'EOF'\n{escaped_content}\nEOF")
            print(f"File copied successfully")
        except Exception as e:
            print(f"Error in stage_in: {e}")
            raise

    def remove_pod(self):
        """
        Removes the remote pod.
        """
        if self.remove and self.pod_name is not None:
            pod_to_delete = self.pod_name
            try:
                print(f"Deleting remote pod: {pod_to_delete}")
                delete_cmd = f"kubectl delete pod {pod_to_delete} -n {self.namespace} --grace-period=30"
                self._run_kubectl_command(delete_cmd)
                print(f"Remote pod {pod_to_delete} deleted")
            except Exception as e:
                # Try force delete
                try:
                    force_cmd = f"kubectl delete pod {pod_to_delete} -n {self.namespace} --force --grace-period=0"
                    self._run_kubectl_command(force_cmd)
                    print(f"Remote pod {pod_to_delete} forcefully deleted")
                except Exception as force_error:
                    print(f"Warning: Could not delete remote pod {pod_to_delete}: {force_error}")
            finally:
                self.pod_name = None
                self.info = None

    def pre_process_command(self, command):
        """
        Override the preprocessing method to intercept workflow:/// URLs
        before Dagon tries to process them.
        """
        # Create the pod if it doesn't exist
        if self.pod_name is None:
            self.create_pod()
        
        # Process workflow:/// manually
        if "workflow:///" in command:
            import re
            # Find all workflow:/// references
            workflow_refs = re.findall(r'workflow:///([^/\s]+)/([^\s]+)', command)
            
            for task_name, file_path in workflow_refs:
                workflow_url = f"workflow:///{task_name}/{file_path}"  # Define ANTES del try
                
                # Search for the referenced task
                src_task = None
                if hasattr(self, 'workflow') and self.workflow:
                    for task in self.workflow.tasks:
                        if task.name == task_name:
                            src_task = task
                            break
                
                if src_task:
                    # Ensure the source task has its pod created
                    if not hasattr(src_task, 'pod_name') or src_task.pod_name is None:
                        src_task.create_pod()
                    
                    # Use the file path directly in the pod
                    local_path = file_path
                    
                    try:
                        # Copy file using stage_in method
                        self.stage_in(src_task, file_path, local_path)
                        # Replace the workflow:// reference with the local path
                        command = command.replace(workflow_url, local_path)
                    except Exception as e:
                        print(f"Error processing workflow reference {workflow_url}: {e}")
                        raise
                else:
                    print(f"Warning: Could not find source task '{task_name}' for {workflow_url}")
        
        return command

    def on_execute(self, script, script_name):
        """
        Execute the task on the remote pod.
        """
        if self.executed:
            print(f"[{self.name}] Returning previous result")
            return self.execution_result

        # Create pod if it doesn't exist
        if self.pod_name is None:
            self.create_pod()

        # Process command to handle workflow:/// references
        processed_command = self.pre_process_command(self.command)

        # Execute command directly in pod (no script transfer needed)
        print(f"[{self.name}] Executing command in remote pod")
        result_output = self.exec_in_pod(processed_command).strip()

        # Escape newlines and tabs
        safe_result = result_output.replace("\n", "\\n").replace("\t", "\\t")

        # Format output as JSON
        output_json = json.dumps({"result": safe_result})
        print(f"[{self.name}] Output:\n{output_json}")

        result = {
            'output': output_json,
            'code': 0
        }

        self.executed = True
        self.execution_result = result
        return result

    def on_garbage(self):
        """
        Call garbage collector, removing the pod on the remote cluster.
        """
        RemoteTask.on_garbage(self)
        self.remove_pod()