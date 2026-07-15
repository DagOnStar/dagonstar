"""
Nomad Task Module for Dagon Framework
Provides integration with HashiCorp Nomad for container orchestration
"""

import os
import json
import time
import uuid
import logging
import requests
from dagon import Batch
from dagon.task import Task
from dagon.remote import RemoteTask


class NomadTask(Batch):
    """
    Represents a task running on HashiCorp Nomad.
    
    :ivar nomad_address: Nomad API address
    :vartype nomad_address: str
    
    :ivar job_id: Nomad job identifier
    :vartype job_id: str
    
    :ivar image: Docker image to use
    :vartype image: str
    
    :ivar allocation_id: Nomad allocation ID
    :vartype allocation_id: str
    """

    def __init__(self, name, command, image="ubuntu:22.04", nomad_address="http://localhost:4646",
                 working_dir=None, volume=None, cpu=100, memory=256, 
                 transversal_workflow=None, globusendpoint=None, network_mode="bridge",
                 datacenter="dc1", region="global"):
        """
        Initialize Nomad task
        
        :param name: task name
        :type name: str
        
        :param command: command to be executed
        :type command: str
        
        :param image: Docker image
        :type image: str
        
        :param nomad_address: Nomad server address
        :type nomad_address: str
        
        :param working_dir: path to the task's working directory
        :type working_dir: str
        
        :param volume: Volume to mount (host_path:container_path)
        :type volume: str
        
        :param cpu: CPU allocation in MHz
        :type cpu: int
        
        :param memory: Memory allocation in MB
        :type memory: int
        
        :param network_mode: Docker network mode
        :type network_mode: str
        
        :param datacenter: Nomad datacenter
        :type datacenter: str
        
        :param region: Nomad region
        :type region: str
        """
        
        Task.__init__(self, name, command, working_dir=working_dir,
                      transversal_workflow=transversal_workflow, 
                      globusendpoint=globusendpoint)
        
        self.command = command
        self.image = image
        self.nomad_address = nomad_address.rstrip('/')
        self.volume = volume
        self.cpu = cpu
        self.memory = memory
        self.network_mode = network_mode
        self.datacenter = datacenter
        self.region = region
        
        # Nomad job tracking
        self.job_id = None
        self.allocation_id = None
        self.task_name = "dagon-task"
        
        # Status tracking
        self.job_submitted = False
        
    def __new__(cls, *args, **kwargs):
        """Factory method to create RemoteNomadTask if 'ip' is provided"""
        if "ip" in kwargs:
            return super(Task, cls).__new__(RemoteNomadTask)
        else:
            return super(NomadTask, cls).__new__(cls)

    def _generate_job_spec(self):
        """
        Generate Nomad job specification in HCL/JSON format
        
        :return: Job specification as dictionary
        :rtype: dict
        """
        
        # Generate unique job ID
        self.job_id = f"dagon-{self.name.lower()}-{uuid.uuid4().hex[:8]}"
        
        # Parse volume configuration
        volumes = []
        if self.volume:
            if ':' in self.volume:
                host_path, container_path = self.volume.split(':', 1)
                volumes.append(f"{host_path}:{container_path}")
            else:
                volumes.append(f"{self.volume}:{self.volume}")
        
        # Build command - NO ESCAPAR, requests.post maneja JSON correctamente
        task_command = self.command.strip()
        
        # Job specification
        job_spec = {
            "Job": {
                "ID": self.job_id,
                "Name": self.job_id,
                "Type": "batch",
                "Priority": 50,
                "Datacenters": [self.datacenter],
                "Region": self.region,
                "TaskGroups": [{
                    "Name": "dagon-group",
                    "Count": 1,
                    "RestartPolicy": {
                        "Attempts": 0,
                        "Mode": "fail"
                    },
                    "Tasks": [{
                        "Name": self.task_name,
                        "Driver": "docker",
                        "Config": {
                            "image": self.image,
                            "command": "/bin/bash",
                            "args": ["-c", task_command],
                            "volumes": volumes,
                            "network_mode": self.network_mode
                        },
                        "Resources": {
                            "CPU": self.cpu,
                            "MemoryMB": self.memory
                        },
                        "LogConfig": {
                            "MaxFiles": 2,
                            "MaxFileSizeMB": 10
                        }
                    }]
                }]
            }
        }
        
        return job_spec

    def _submit_job(self):
        """
        Submit job to Nomad
        
        :return: Job submission response
        :rtype: dict
        """
        
        if self.job_submitted:
            self.workflow.logger.info(f"{self.name}: Job already submitted")
            return
        
        job_spec = self._generate_job_spec()
        
        try:
            url = f"{self.nomad_address}/v1/jobs"
            response = requests.post(url, json=job_spec, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            self.job_submitted = True
            self.workflow.logger.info(f"{self.name}: Job submitted to Nomad: {self.job_id}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.workflow.logger.error(f"{self.name}: Failed to submit job to Nomad: {e}")
            raise Exception(f"Failed to submit Nomad job: {e}")

    def _wait_for_completion(self, timeout=3600):
        """
        Wait for job to complete
        
        :param timeout: Maximum time to wait in seconds
        :type timeout: int
        
        :return: Job completion status
        :rtype: dict
        """
        
        start_time = time.time()
        check_interval = 2  # Check every 2 seconds
        
        self.workflow.logger.info(f"{self.name}: Waiting for job completion...")
        
        while time.time() - start_time < timeout:
            try:
                # Get job status
                url = f"{self.nomad_address}/v1/job/{self.job_id}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                job_status = response.json()
                status = job_status.get('Status', 'unknown')
                
                self.workflow.logger.debug(f"{self.name}: Job status: {status}")
                
                if status == 'dead':
                    # Job finished, check if successful
                    # Get allocations to check task status
                    allocs_url = f"{self.nomad_address}/v1/job/{self.job_id}/allocations"
                    allocs_response = requests.get(allocs_url, timeout=10)
                    allocs_response.raise_for_status()
                    
                    allocations = allocs_response.json()
                    
                    if allocations:
                        alloc = allocations[0]
                        self.allocation_id = alloc.get('ID')
                        task_states = alloc.get('TaskStates', {})
                        
                        if self.task_name in task_states:
                            task_state = task_states[self.task_name]
                            state = task_state.get('State')
                            
                            if state == 'dead':
                                events = task_state.get('Events', [])
                                # Check last event
                                if events:
                                    last_event = events[-1]
                                    event_type = last_event.get('Type')
                                    
                                    if event_type == 'Terminated':
                                        exit_code = last_event.get('ExitCode', 1)
                                        
                                        if exit_code == 0:
                                            self.workflow.logger.info(
                                                f"{self.name}: Job completed successfully"
                                            )
                                            return {'code': 0, 'output': 'Job completed', 'message': 'Success'}
                                        else:
                                            self.workflow.logger.error(
                                                f"{self.name}: Job failed with exit code {exit_code}"
                                            )
                                            return {'code': exit_code, 'output': 'Job failed', 
                                                   'message': f'Job failed with exit code {exit_code}'}
                    
                    # If we get here, something went wrong
                    self.workflow.logger.error(f"{self.name}: Job died without proper completion")
                    return {'code': 1, 'output': 'Job died', 'message': 'Job died without proper completion'}
                
                elif status == 'running':
                    self.workflow.logger.debug(f"{self.name}: Job is running...")
                
                time.sleep(check_interval)
                
            except requests.exceptions.RequestException as e:
                self.workflow.logger.error(f"{self.name}: Error checking job status: {e}")
                time.sleep(check_interval)
        
        # Timeout reached
        self.workflow.logger.error(f"{self.name}: Job timeout reached")
        return {'code': 1, 'output': 'Timeout', 'message': 'Job execution timeout'}

    def _get_logs(self):
        """
        Retrieve logs from completed job
        
        :return: Job logs
        :rtype: str
        """
        
        if not self.allocation_id:
            return "No logs available (no allocation ID)"
        
        try:
            # Get stdout
            stdout_url = f"{self.nomad_address}/v1/client/fs/logs/{self.allocation_id}"
            params = {
                'task': self.task_name,
                'type': 'stdout',
                'plain': 'true'
            }
            
            response = requests.get(stdout_url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.text
            else:
                return f"Could not retrieve logs: {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            return f"Error retrieving logs: {e}"

    def _cleanup_job(self):
        """
        Purge completed job from Nomad
        """
        
        if not self.job_id:
            return
        
        try:
            url = f"{self.nomad_address}/v1/job/{self.job_id}"
            params = {'purge': 'true'}
            response = requests.delete(url, params=params, timeout=10)
            
            if response.status_code == 200:
                self.workflow.logger.info(f"{self.name}: Job purged from Nomad")
            else:
                self.workflow.logger.warning(
                    f"{self.name}: Could not purge job: {response.status_code}"
                )
                
        except requests.exceptions.RequestException as e:
            self.workflow.logger.warning(f"{self.name}: Error purging job: {e}")

    def include_command(self, body):
        """
        Include the command to execute in the script body
        
        :param body: Script body
        :type body: str
        
        :return: Script body with the command
        :rtype: str
        """
        
        # For Nomad, we don't need to modify the script body
        # The command is submitted directly to Nomad
        return body.strip()

    def pre_process_command(self, command):
        """Pre-process command before execution"""
        
        # Create .dagon directory
        os.makedirs(os.path.join(self.working_dir, ".dagon"), exist_ok=True)
        
        # Submit job to Nomad
        self._submit_job()
        
        # NO llamar a super() porque intenta parsear JSON que no existe
        # En su lugar, devolver un comando dummy
        return "echo 'Job submitted to Nomad'"

    def on_execute(self, script, script_name):
        """
        Execute the task via Nomad
        
        :param script: script content
        :type script: str
        
        :param script_name: script name
        :type script_name: str
        
        :return: execution result
        :rtype: dict with the execution output (str) and code (int)
        """
        
        # Create .dagon directory if not exists
        os.makedirs(os.path.join(self.working_dir, ".dagon"), exist_ok=True)
        
        # Invoke the base method
        Task.on_execute(self, script, script_name)
        
        # Wait for job completion
        result = self._wait_for_completion()
        
        # Get logs
        if result['code'] == 0:
            logs = self._get_logs()
            result['output'] = logs
            
            # Save logs to file
            if self.working_dir:
                log_file = os.path.join(self.working_dir, ".dagon", "stdout.txt")
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                with open(log_file, 'w') as f:
                    f.write(logs)
        
        return result

    def on_garbage(self):
        """
        Call garbage collector, cleaning up Nomad jobs
        """
        super(NomadTask, self).on_garbage()
        self._cleanup_job()


class RemoteNomadTask(RemoteTask, NomadTask):
    """
    Represents a Nomad task running on a remote machine
    """

    def __init__(self, name, command, image="ubuntu:22.04", nomad_address=None,
                 ip=None, ssh_username=None, keypath=None, working_dir=None,
                 volume=None, cpu=100, memory=256, globusendpoint=None,
                 network_mode="bridge", datacenter="dc1", region="global",
                 ssh_port=22):
        """
        Initialize remote Nomad task
        
        :param name: task name
        :type name: str
        
        :param command: command to be executed
        :type command: str
        
        :param image: Docker image
        :type image: str
        
        :param nomad_address: Nomad server address (defaults to http://ip:4646)
        :type nomad_address: str
        
        :param ip: IP address of the machine running Nomad
        :type ip: str
        
        :param ssh_username: UNIX username to connect through SSH
        :type ssh_username: str
        
        :param keypath: Path to the public key
        :type keypath: str
        
        :param working_dir: path to the task's working directory
        :type working_dir: str
        
        :param volume: Volume to mount (host_path:container_path)
        :type volume: str
        
        :param cpu: CPU allocation in MHz
        :type cpu: int
        
        :param memory: Memory allocation in MB
        :type memory: int
        
        :param network_mode: Docker network mode
        :type network_mode: str
        
        :param datacenter: Nomad datacenter
        :type datacenter: str
        
        :param region: Nomad region
        :type region: str
        
        :param ssh_port: SSH port (default: 22)
        :type ssh_port: int
        """
        
        # If nomad_address not specified, construct from ip
        if nomad_address is None:
            nomad_address = f"http://{ip}:4646"
        
        NomadTask.__init__(self, name, command, image=image, 
                          nomad_address=nomad_address,
                          working_dir=working_dir, volume=volume,
                          cpu=cpu, memory=memory,
                          transversal_workflow=None,
                          globusendpoint=globusendpoint,
                          network_mode=network_mode,
                          datacenter=datacenter, region=region)
        
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username, 
                           keypath=keypath, command=command, ip=ip,
                           working_dir=working_dir, 
                           globusendpoint=globusendpoint, 
                           ssh_port=ssh_port)

    def on_execute(self, launcher_script, script_name):
        """
        Execute the task script on remote Nomad
        
        :param launcher_script: script content
        :type launcher_script: str
        
        :param script_name: script name
        :type script_name: str
        
        :return: execution result
        :rtype: dict with the execution output (str) and code (int)
        """
        
        # Submit job and wait for completion using Nomad API
        # (which can be accessed remotely via HTTP)
        return NomadTask.on_execute(self, launcher_script, script_name)

    def on_garbage(self):
        """
        Call garbage collector for remote task
        """
        RemoteTask.on_garbage(self)
        self._cleanup_job()