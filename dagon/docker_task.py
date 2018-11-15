import re
import os
import shutil

import dagon
from task import Task
from batch import Batch
from . import Workflow
from dockercontainer.docker_client import DockerClient
from dockercontainer.container import Container
from dagon.remote import DockerRemoteTask
from communication.data_transfer import DataTransfer
from communication.data_transfer import GlobusManager
from communication.data_transfer import SCPManager


class LocalDockerTask(Batch):

    # Params:
    # 1) name: task name
    # 2) command: command to be executed
    # 3) image: docker image which the container is going to be created
    # 4) host: URL of the host, by default use the unix local host
    def __init__(self, name, command, containerID=None, working_dir=None, image=None, endpoint=None):
        Batch.__init__(self, name, command, working_dir=working_dir)
        self.command = command
        self.containerID = containerID
        self.working_dir = working_dir
        self.image = image
        self.endpoint = endpoint
        self.docker_client = DockerClient()
        self.transfer = DataTransfer.inferDataTransportation("127.0.0.1", self.endpoint)
        self.ssh_connection = None

    # Return the transfer type method (globus, scp)
    def getTransferType(self):
        return self.transfer

    def getSSHClient(self):
        return None

    def isTaskRemote(self):
        return False

    # Create a Docker container
    def createContainer(self):
        command = self.strRunCont(image=self.image, detach=True,
                                  volume={"host": self.workflow.get_scratch_dir_base(),
                                          "container": self.workflow.get_scratch_dir_base()})

        result = self.docker_client.exec_command(command)
        if (result['code'] == 1):
            raise Exception(self.result["error"].rstrip())
        return result['output']

    # Method overrided
    def pre_run(self):
        Task.pre_run(self)
        self.createWorkingDir()
        if (self.containerID is None):
            self.containerID = self.createContainer()
        self.container = Container(self.containerID, self.docker_client)

    def createWorkingDir(self):
        if self.working_dir is None:
            # Set a scratch directory as working directory
            self.working_dir = self.workflow.get_scratch_dir_base() + "/" + self.get_scratch_name()
            self.local_working_dir = self.working_dir
            # Create scratch directory
            self.local_working_dir = self.working_dir
            os.makedirs(self.working_dir)

            # Set to remove the scratch directory
            self.remove_scratch_dir = True
        else:
            # Set to NOT remove the scratch directory
            self.remove_scratch_dir = False

        if self.workflow.regist_on_api: #change scratch directory on server
            try:
                self.workflow.api.update_task(self.workflow.id, self.name,"working_dir", self.working_dir)
            except Exception, e:
                self.workflow.logger.error("%s: Error updating scratch directory on server %s", self.name, e)

    # form string to create container
    def strRunCont(self, image, command=None, volume=None, ports=None, detach=False):
        docker_command = "docker run"
        if (detach):
            docker_command += " -t -d"

        if volume is not None:
            docker_command += " -v \'%s\':\'%s\'" % (volume['host'], volume['container'])
        if ports is not None:
            docker_command += " -p \'%s\':\'%s\'" % (ports['host'], ports['container'])
        docker_command += " %s" % image

        if command is not None:
            docker_command += " " + command

        return docker_command

    # # Remove the scratch directory if needed
    def remove_scratch(self):
        # Check if the scratch directory must be removed
        if self.reference_count == 0 and self.remove_scratch_dir is True:
            # Remove the scratch directory
            shutil.move(self.working_dir, self.working_dir + "-removed")
            self.workflow.logger.debug("Removed %s", self.working_dir)

    # Method overrided 
    def execute(self):
        self.workflow.logger.debug("%s: Scratch directory: %s", self.name, self.working_dir)

        # Change to the scratch directory
        # os.chdir(self.working_dir)

        # Applay some command pre processing
        command = self.pre_process_command(self.command)
        # command = self.command

        # Get the arguments splitted by the schema
        args = command.split(Workflow.SCHEMA)

        for i in range(1, len(args)):
            # Split each argument in elements by the slash
            elements = args[i].split("/")

            # The task name is the first element
            task_name = elements[0]

            # Extract the task
            task = self.workflow.find_task_by_name(task_name)
            if task is not None:
                file_input = "/".join(elements[1:])
                file_input = re.split("> |>>", file_input)[0].strip()
                file_input = re.split(" ", file_input)[0].strip()
                leaf = SCPManager.path_leaf(file_input)
                if task.isInOtherMachine(self.ip):
                    if task.getTransferType() == DataTransfer.GLOBUS and self.getTransferType() == DataTransfer.GLOBUS:
                        gm = GlobusManager(task.getEndpoint(), self.getEndpoint())
                        gm.copyData(task.working_dir + "/" + file_input, self.working_dir + "/" + file_input)
                    else:
                        scpM = SCPManager(task.getSSHClient(), self.ssh_connection)
                        scpM.copyData(task.working_dir + "/" + file_input, self.working_dir + "/" + leaf,
                                      self.local_working_dir + "/" + leaf)
                    command = command.replace(Workflow.SCHEMA + task.name, self.working_dir)
                else:
                    command = command.replace(Workflow.SCHEMA + task.name, task.working_dir)

        # Apply some command post processing
        command = self.post_process_command(command)
        # Execute the bash command
        self.result = self.container.exec_in_cont("sh -c \'" + command + "\'")

        if self.result["code"] == 1:
            raise Exception(self.result["error"].rstrip())

        # Remove the reference
        # For each workflow:// in the command

        # Get the arguments splitted by the schema
        args = self.command.split(Workflow.SCHEMA)
        for i in range(1, len(args)):
            # Split each argument in elements by the slash
            elements = args[i].split("/")

            # The task name is the first element
            task_name = elements[0]

            # Extract the task
            task = self.workflow.find_task_by_name(task_name)
            if task is not None:
                # Remove the reference from the task
                task.decrement_reference_count()

        # Remove the scratch directory
        self.remove_scratch()


class DockerTask(Task):

    def __init__(self, name, command, image=None, containerID=None, ip=None, port=None, ssh_username=None, keypath=None,
                 working_dir=None, local_working_dir=None, endpoint=None):
        Task.__init__(self, name)

    def __new__(cls, name, command, image=None, containerID=None, ip=None, port=None, ssh_username=None, keypath=None,
                working_dir=None, local_working_dir=None, endpoint=None):
        isRemote = not ip == None
        if isRemote:
            return DockerRemoteTask(name, command, image=image, containerID=containerID, ip=ip,
                                    ssh_username=ssh_username, working_dir=working_dir,
                                    local_working_dir=local_working_dir, endpoint=endpoint,
                                    keypath=keypath)
        else:
            return LocalDockerTask(name, command, containerID=containerID, working_dir=working_dir, image=image)
