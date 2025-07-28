import shutil
import glob
import os
from json import loads, dumps
from threading import Thread
from threading import Semaphore
from os import makedirs, path, chmod
from time import time, sleep
from enum import Enum
from dagon.ftp_publisher import FTP_API
import dagon


class TaskType(Enum):
    """
    Enum used to represent the main types tasks supported by dagon,
    remote tasks are supported by the RemoteClass but it should not be
    explicitly instantiate

    :cvar CHECKPOINT: Explicit checkpoint enabling saving and resuming the workflow run
    :cvar BATCH: Regular Batch task (local or remote)
    :cvar SLURM: Task executed using Slurm (local or remote)
    :cvar CLOUD: Task executed in a cloud instance (ec2, digital ocean and google cloud  tested with libcloud)
    :cvar DOCKER: Task executed on a docker container (local or remote)
    """

    CHECKPOINT = "checkpoint"
    BATCH = "batch"
    SLURM = "slurm"
    CLOUD = "cloud"
    DOCKER = "docker"


# Different types os tasks and their module and class name
tasks_types = {
    TaskType.CHECKPOINT: ("dagon.checkpoint", "Checkpoint"),
    TaskType.BATCH: ("dagon.batch", "Batch"),
    TaskType.CLOUD: ("dagon.remote", "CloudTask"),
    TaskType.DOCKER: ("dagon.docker_task", "DockerTask"),
    TaskType.SLURM: ("dagon.batch", "Slurm")
}


class DagonTask(object):
    """
    Create the instance for Dagon Tasks
    """

    def __new__(cls, class_type, *args, **kwargs):
        """
        Choose the task type and returns an instance of the task type class

        :param class_type: type of the task (:class:`Types`)
        :type class_type: :class:`TaskType`

        :param args: arguments of the task
        :type name: list[]

        :param kwargs: keyboard arguments of the task
        :type name: dict()

        :return: subclass instance of :class:`Task`
        :rtype: cls
        """

        from importlib import import_module
        task_class = tasks_types[class_type]
        module = import_module(task_class[0])
        class_ = getattr(module, task_class[1])
        return class_(*args, **kwargs)


class Task(Thread):
    """
    **Represents a task executed by DagOn**

    It can be executed on local machine, cloud instance, cluster or in a docker container

    :ivar name: unique name of the class
    :vartype name: str

    :ivar command: command to be executed
    :vartype command: str

    :ivar working_dir: path to the folder or directory where the task is going to be executed
    :vartype working_dir: str

    :ivar nexts: tasks with dependencies to this tasks, that will be executed when this task ends
    :vartype nexts: list[]

    :ivar prevs: tasks that has to be executed before of this task (dependencies to be resolved)
    :vartype prevs: list[]

    :ivar reference_count: number of references to this task
    :vartype reference_count: int

    :ivar remove_scratch_dir: True if the sratch directory has to be removed after the execution of this task
    :vartype remove_scratch_dir: bool

    :ivar running: True if the task is in execution
    :vartype running: bool

    :ivar workflow: workflow related to this task
    :vartype workflow: :class:`dagon.Workflow`

    :ivar status: actual :class:`dagon.Status` of the task
    :vartype status: :class:`dagon.Status`

    :ivar info: information of the enviroment where this task is going to be executed
    :vartype info: dict(str, object)

    """

    def __init__(self, name, command, working_dir=None, transversal_workflow=None, globusendpoint=None):
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed by the task
        :type command: str

        :param working_dir: path to the directory where the task is be executed
        :type working_dir: str

        :param endpoint: UUID of the Globus Endpoint to store the data.
        :type endpoint: str

        """
        Thread.__init__(self)
        self.ssh_connection = None
        self.name = name
        self.nexts = []
        self.prevs = []
        self.reference_count = 0
        self.remove_scratch_dir = False
        self.ip = None
        self.running = False
        self.workflow = None
        self.set_status(dagon.Status.READY)
        self.working_dir = working_dir
        self.command = command
        self.info = None
        self.dag_tps = None
        self.transversal_workflow = transversal_workflow
        self.workflows = None
        self.data_mover = None
        self.stager_mover = None
        self.mode = "sequential"
        self.globusendpoint = globusendpoint
        self.new_tasks = []

    def get_endpoint(self):
        return self.globusendpoint

    def set_endpoint(self, globusendpoint):
        self.globusendpoint = globusendpoint

    def set_mode(self, mode):
        self.mode = mode

    def get_mode(self):
        return self.mode

    def set_data_mover(self, data_mover):
        """
        Change the mode of the stager. The information is used by
        :class:`dagon.Stager` to decide the mode (COPY/LINK)

        :param data_mover: mode of the stager
        :type info: class:`dagon.DataMover`
        """
        self.data_mover = data_mover

    def set_stager_mover(self, stager_mover):
        """
        :param data_mover: mode of the stager
        :type info: class:`dagon.StagerMover`
        """
        self.stager_mover = stager_mover

    def set_info(self, info):
        """
        Change the information of the machine where the task is going to be executed. The information is used by
        :class:`dagon.Stager` to decide the data transfer protocol/application

        :param info: Machine info (ip, protocols, username)
        :type info: dict(str, object)
        """

        self.info = info

    def get_ip(self):
        """
        Returns the ip of the machine where the task is executed

        :return: IP address
        :rtype: str
        """
        from dagon.remote import CloudTask

        if isinstance(self, CloudTask):
            return self.info["public_ip"]
        else:
            return self.info["ip"] if self.ip == None else self.ip

    def get_info(self):
        """
        Returns the complete information of the machine where the task is executed

        :return: Machine information collected
        :rtype: dict(str, object)
        """
        return self.info

    def get_user(self):
        """
        Return the username who execute the task on the remote machine

        :return: Unix Username
        :rtype: str
        """

        return self.info["user"]

    def get_scratch_dir(self):
        """
        Returns the task's scratch directory as soon as it's available

        :return: Absolute path to the scratch directory
        :rtype: str
        """

        while self.working_dir is None and self.status is not dagon.Status.FAILED:
            sleep(1)
        return self.working_dir

    def get_scratch_name(self):
        """
        Generates a unique name for the task scratch directory name

        :return: Name of the scratch directory
        :rtype: str
        """
        millis = int(round(time() * 1000))
        return str(millis) + "-" + self.name

    def as_json(self):
        """"
        Generates the JSON representation of the task

        :return: JSON task representation
        :rtype: dict(str, object)
        """

        json_task = {"name": self.name, "status": self.status.name,
                     "working_dir": self.working_dir, "nexts": [], "prevs": [],
                     "command": self.command, "type": type(self).__name__.lower()}

        for t in self.nexts:
            json_task['nexts'].append(t.name)
        for t in self.prevs:
            json_task['prevs'].append(t.name)
        return json_task

    def set_workflow(self, workflow):
        """
        Set the workflow which execute this task

        :param workflow: :class:`dagon.Workflow` instance
        :type workflow: :class:`dagon.Workflow`
        """
        self.workflow = workflow

    def set_dag_tps(self, DAG_tps):
        """
        Set the DAG_tps workflow which execute this task

        :param  DAG_tps: :class:`dagon.dag_tps` instance
        :type  DAG_tps: :class:`dagon.dag_tps`
        """
        self.dag_tps = DAG_tps

    def exists_dir(self, path):
        pass

    # Set the current status
    def set_status(self, status):
        """
        Set the status for the current task

        :param status: status of the task
        :type status: :class:`dagon.task.Status`
        """
        self.status = status
        if self.workflow is not None:
            self.workflow.logger.debug("%s: %s", self.name, self.status)
            if self.workflow.is_api_available:
                self.workflow.api.update_task_status(
                    self.workflow.workflow_id, self.name, status.name)

    def execute_command(self, command):
        """"
        Executes a command
        :param command: command to be executed
        """
        pass

    def add_dependency_to(self, task):
        """
        Add a dependency to other task

        :param task: :class:`dagon.task.Task` instance dependency
        :type task: :class:`dagon.task.Task`
        """
        task.nexts.append(self)
        self.prevs.append(task)

        if self.workflow.is_api_available:  # add in the server
            self.workflow.api.add_dependency(
                self.workflow.workflow_id, self.name, task.name)

    def add_transversal_point(self, task):
        """
        Add a dependency from other task

        :param task: :class:`dagon.task.Task` instance dependency
        :type task: :class:`dagon.task.Task`
        """
        self.prevs.append(task)

        if self.workflow.is_api_available:  # add in the server
            self.workflow.api.add_dependency(
                self.workflow.workflow_id, self.name, task.name)

    # Increment the reference count
    def increment_reference_count(self):
        """
        Increments the reference count
        """
        self.reference_count = self.reference_count + 1

    # Call garbage collector (remove scratch directory, container, cloud instance, etc)
    # implemented by each task class
    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """

        # Perform some logging
        self.workflow.logger.debug("Removing %s", self.working_dir)

        shutil.move(self.working_dir, self.working_dir + "-removed")

        # Update the working directory
        self.working_dir = self.working_dir + "-removed"

        # Update the checkpoint
        self.workflow.checkpoints[self.workflow.name + "." +
                                  self.getName()]["working_dir"] = self.working_dir

    # Decrement the reference count

    def decrement_reference_count(self):
        """
        Decrement the reference count. When the number of references is equals to zero, the garbage collector is called
        """
        self.reference_count = self.reference_count - 1

        # Check if the scratch directory must be removed
        if self.reference_count == 0 and self.remove_scratch_dir is True:
            # Call garbage collector (remove scratch directory, container, cloud instace, etc)
            self.on_garbage()

            if self.workflow.checkpoint_file is not None:
                fp = open(self.workflow.checkpoint_file, 'w')
                fp.write(dumps(self.workflow.checkpoints,
                         sort_keys=True, indent=4))
                fp.close()

    def set_semaphore(self, sem):
        self.semaphore = sem

    # Method overrided
    def pre_run(self):
        """
        Resolve task dependencies
        For each workflow:// in the command string
        1) Extract the referenced task
        2) Add a reference in the referenced task

        """
        # Index of the starting position
        pos = 0
        # get workflows of dag_tps
        if self.dag_tps is not None:
            self.workflows = self.dag_tps.workflows

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object

            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            # Check if the refernced task is consistent
            if task is not None:
                # Add the dependency to the task
                if workflow_name == self.workflow.name:
                    self.add_dependency_to(task)
                else:
                    self.add_transversal_point(task)
                # Add the reference from the task
                task.increment_reference_count()

                # TODO: check this code
                """
                if self.mode == "parallel":
                    for next_task in self.nexts:
                        if self in next_task.prevs:
                            next_task.prevs.remove(self)
                        
                        for new_task in self.new_tasks:
                            next_task.add_dependency_to(new_task)
                """

            if task is None:  # if is None means that task is from another WF maybe in the dagon service
                # self.workflow.logger.debug("Adding transversal point")
                # self.workflow.logger.debug(workflow_name)
                # self.workflow.logger.debug(task)
                if self.workflow.is_api_available:
                    workflow_id = self.workflow.api.get_workflow_by_name(
                        workflow_name)
                    transversal_task = self.workflow.api.get_task(workflow_id, task_name)[
                        'task']  # get the task from the external workflow
                    transversal_task = DagonTask(TaskType[transversal_task['type'].upper()], transversal_task['name'],
                                                 transversal_task['command'],
                                                 transversal_workflow=workflow_id,
                                                 working_dir=transversal_task['working_dir'])
                    self.add_transversal_point(transversal_task)
                else:
                    raise ConnectionError("Dagon service is not available")

            # Go to the next element
            pos = pos2

    # Pre process command
    def pre_process_command(self, command):
        """
        Preprocess the command resolving the dependencies with other tasks

        :param command:
        :type command: command to be executed by the task

        :return: command preprocessed
        :rtype: str
        """
        stager = dagon.stager.base.Stager(
            self.data_mover, self.stager_mover, self.workflow.cfg)

        # Initialize the script
        header = "#! /bin/bash\n"
        header = "export PATH=\"$HOME/.local/bin:$PATH\"\n"
        header = header + "# This is the DagOn launcher script\n\n"
        header = header + "code=0\n"
        # Add and execute the howim script

        context_script = header + "cd " + self.working_dir + "/.dagon\n"

        if "dynostore" in self.workflow.cfg:

            # Check if python is available
            header += "if command -v python &>/dev/null; then\n"
            header += "PYTHON=python\n"
            header += "elif command -v python3 &>/dev/null; then\n"
            header += "PYTHON=python3\n"
            header += "else\n"
            header += " echo \"Python is not available, please install Python to use DynoStore\"\n"
            header += " exit 1\n"
            header += "fi\n"

            header += "if $PYTHON -c \"import dynostore\" &>/dev/null; then\n"
            header += " echo \"DynoStore is installed\"\n"
            header += "else\n"
            header += " echo \"DynoStore is not installed, installing...\"\n"
            header += "pip install git+https://github.com/dynostore/dynostore-client\n"
            header += " fi\n"

        header += "echo \n echo \"************************************\"\n echo \n"

        context_script += header + self.get_how_im_script() + "\n\n"

        # execute context script
        result = self.on_execute(context_script, "context.sh")
        if result['code']:
            raise Exception(result['message'])

        # Step 1: Unescape the backslashes
        unescaped_output = result['output'].encode(
            'utf-8').decode('unicode_escape')

        # Optional: remove trailing newline if needed
        unescaped_output = unescaped_output.strip()

        # Get only the JSON part of the output
        parts_output = unescaped_output.split(
            "************************************")
        if len(parts_output) > 1:
            json_output = parts_output[1].strip()
        else:
            raise ValueError("Output does not contain expected JSON format")

        info = loads(json_output)

        if "dynostore" in self.workflow.cfg:
            info['dynostore'] = self.workflow.cfg['dynostore']

            # ToDO: Check if dynostore is available
        self.set_info(info)

        # start the creation of the launcher.sh script
        # Create the header
        header = header + "# Change the current directory to the working directory\n"
        header = header + "cd " + self.working_dir + "\n"
        header = header + "if [ $? -ne 0 ]; then code=1; fi \n\n"
        header = header + "# Start staging in\n\n"

        # Create the body
        body = command

        # Index of the starting position
        pos = 0

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:

            # Get the position of the next dagon.Workflow.SCHEcdMA
            pos1 = command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(command)

            # Extract the parameter string
            arg = command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Get the rest of the string as local path
            local_path = "/" + "/".join(elements[2:])

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object
            # task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            if task is None:  # if is None means that task is from another WF maybe in the dagon service
                if self.workflow.is_api_available:
                    workflow_id = self.workflow.api.get_workflow_by_name(
                        workflow_name)
                    response = self.workflow.api.get_task(workflow_id,
                                                          task_name)  # get the task from the external workflow
                    transversal_task = response['task']
                    host_ip = response['host']
                    # if the host is the same in this computer, the task is in the same computer
                    if host_ip == self.workflow.ftpAtt['host']:
                        # the same workingdir
                        task_path = transversal_task['working_dir']
                    else:
                        task_path = self.workflow.local_path + transversal_task[
                            'working_dir']  # if not, we add an extra path
                        ftp = FTP_API(host_ip)
                        task_folder = transversal_task['working_dir'].split(
                            "/")[-1]  # the last one is the task folder
                        ftp.downloadFiles(task_folder, task_path)
                        # we need to download the data from the ftp host

                    task = DagonTask(TaskType[transversal_task['type'].upper()], transversal_task['name'],
                                     transversal_task['command'],
                                     transversal_workflow=workflow_id, working_dir=task_path)

            # Check if the referenced task is consistent
            if task is not None:
                # Evaluate the destination path
                dst_path = self.working_dir + "/.dagon/inputs/" + workflow_name + "/" + task_name

                # Create the destination directory
                header = header + "\n\n# Create the destination directory\n"
                header = header + "mkdir -p " + dst_path + \
                    "/" + path.dirname(local_path) + "\n"
                header = header + "if [ $? -ne 0 ]; then code=1; fi\n\n"
                # Add the move data command
                header = header + \
                    stager.stage_in(self, task, dst_path, local_path)

                if self.mode == "parallel":
                    files = glob.glob(
                        task.get_scratch_dir() + "/" + local_path)
                    taskType = TaskType[type(self).__name__.upper()]

                    for file in files:
                        filename, _ = path.splitext(path.basename(file))
                        taskParallelName = "{}_{}".format(self.name, filename)
                        cmd = body.replace(
                            dagon.Workflow.SCHEMA + arg, " workflow:///" + self.name + "/" + path.basename(file))

                        if type(self) == dagon.batch.Batch:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd,
                                                      transversal_workflow=self.transversal_workflow)

                        if type(self) == dagon.batch.RemoteBatch:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, ssh_username=self.ssh_username,
                                                      keypath=self.keypath, ip=self.ip)

                        elif type(self) == dagon.batch.Slurm:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, partition=self.partition,
                                                      ntasks=self.ntasks, memory=self.memory)

                        elif type(self) == dagon.batch.RemoteSlurm:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, partition=self.partition,
                                                      ntasks=self.ntasks, memory=self.memory,
                                                      ssh_username=self.ssh_username, keypath=self.keypath, ip=self.ip)

                        elif type(self) == dagon.remote.CloudTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, provider=self.provider,
                                                      ssh_username=self.ssh_username, key_options=self.key_options,
                                                      instance_id=self.instance_id, instance_flavour=self.instance_flavour,
                                                      instance_name=self.instance_name, stop_instance=self.stop_instance)

                        elif type(self) == dagon.docker_task.DockerTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                      container_id=self.container_id, remove=self.remove,
                                                      volume=self.volume, transversal_workflow=self.transversal_workflow)

                        elif type(self) == dagon.docker_task.DockerRemoteTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                      container_id=self.container_id, ssh_username=self.ssh_username,
                                                      keypath=self.keypath, ip=self.ip,
                                                      remove=self.remove, volume=self.volume,
                                                      transversal_workflow=self.transversal_workflow)

                        self.workflow.add_task(parallel_task)
                        self.new_tasks.append(parallel_task)

                    for next_task in self.nexts:
                        if self in next_task.prevs:
                            next_task.prevs.remove(self)

                        for new_task in self.new_tasks:
                            next_task.add_dependency_to(new_task)

                    self.workflow.make_dependencies()

                    body = "echo \"Starting parallel tasks...\"\n"
                    body += "ln -sf " + dst_path + "/" + local_path + " " + self.get_scratch_dir()
                else:
                    # Change the body of the command
                    body = body.replace(
                        dagon.Workflow.SCHEMA + arg, dst_path + "/" + local_path)
            pos = pos2

        # Invoke the command
        header = header + "\n\n# Invoke the command\n"
        header = header + self.include_command(body)
        header = header + "if [ $? -ne 0 ]; then code=1; fi"
        return header

    # process the command to execute
    def include_command(self, body):
        """
        Include the command to execute in the script body
        :param body: Script body
        :return: Script body with the command
        """
        return body + " |tee " + self.working_dir + "/.dagon/stdout.txt\n"

    # Post process the command
    def post_process_command(self, command):
        """
        Add some post process commands after the task execution
        :param command: Command to be executed
        :return: Command post-processed
        """
        footer = command + "\n\n"
        footer = footer + "# Perform post process\n"

        # if dynostore, push the data to dynostore
        if "dynostore" in self.workflow.cfg:
            dyno_conf = self.workflow.cfg['dynostore']
            dyno_server = f"{dyno_conf.get("host")}:{dyno_conf.get("port")}"
            footer += f"echo \"Pushing data to DynoStore server {dyno_server}\"\n"
            footer += f"dynostore --server {dyno_server} put {self.working_dir} --recursive --catalog={os.path.basename(self.working_dir)}\n"

        footer += "exit $code"
        return footer

    # Method to be overrided
    def on_execute(self, script, script_name):
        """
        Execute the task script

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # The launcher script name
        script_name = self.working_dir + "/.dagon/" + script_name
        # Create a temporary launcher script
        file = open(script_name, "w")
        file.write(script)
        file.flush()
        file.close()
        chmod(script_name, 0o744)

    # create path using mkdirs
    def mkdir_working_dir(self, path):
        """
        Make the working directory

        :param path: Path to the working directory
        :type path: str
        """
        makedirs(path, exist_ok=True)

    def create_working_dir(self):
        """
        Create the working directory
        """
        if self.working_dir is None:
            # Set a scratch directory as working directory
            self.working_dir = self.workflow.get_scratch_dir_base() + "/" + \
                self.get_scratch_name()

            # Set to remove the scratch directory
            self.remove_scratch_dir = True

        # Create scratch directory
        self.mkdir_working_dir(self.working_dir + "/.dagon")
        self.workflow.logger.debug(
            "%s: Scratch directory: %s", self.name, self.working_dir)
        if self.workflow.is_api_available:  # change scratch directory on server
            try:
                self.workflow.api.update_task(
                    self.workflow.workflow_id, self.name, "working_dir", self.working_dir)
            except Exception as e:
                self.workflow.logger.error(
                    "%s: Error updating scratch directory on server %s", self.name, e)

    def remove_reference_workflow(self):
        """
        Remove the reference
        For each workflow:// in the command
        """
        # Remove the reference
        # For each workflow:// in the command

        # Index of the starting position
        pos = 0

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object
            # task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            # Check if the refernced task is consistent
            if task is not None:
                # Remove the reference from the task
                task.decrement_reference_count()

            # Go to the next element
            pos = pos2

        if len(self.nexts) == 0 and self.remove_scratch_dir is True:
            self.on_garbage()

    # Method execute
    def execute(self):
        """
        Execute the task

        :raises Exception: a problem occurred during the task  execution
        """
        key = self.workflow.name + "." + self.getName()

        # Local checkpoint
        if key in self.workflow.checkpoints and "code" in self.workflow.checkpoints[key] and \
                self.workflow.checkpoints[key]["code"] == 0 and path.isdir(self.workflow.checkpoints[key]["working_dir"]):
            self.working_dir = self.workflow.checkpoints[key]["working_dir"]

            self.workflow.logger.debug(
                "%s Already completed ---" % (self.name))
        elif self.ssh_connection != None and key in self.workflow.checkpoints and \
            "code" in self.workflow.checkpoints[key] and self.workflow.checkpoints[key]["code"] == 0 and \
                self.exists_dir(self.workflow.checkpoints[key]["working_dir"]):
            self.working_dir = self.workflow.checkpoints[key]["working_dir"]

            self.workflow.logger.debug(
                "%s Already completed ---" % (self.name))
        else:
            self.create_working_dir()

            self.workflow.checkpoints[self.workflow.name + "." + self.getName()] = {
                "working_dir": self.working_dir,
                "workflow": self.workflow.name,
                "name": self.name
            }

            # Apply some command pre processing
            launcher_script = self.pre_process_command(self.command)
            # Apply some command post processing
            launcher_script = self.post_process_command(launcher_script)

            # Execute only if not dry
            if self.workflow.dry is False:

                # Invoke the actual executor
                start_time = time()
                self.result = self.on_execute(launcher_script, "launcher.sh")

                self.workflow.logger.debug(
                    "%s Completed in %s seconds ---" % (self.name, (time() - start_time)))

                self.workflow.checkpoints[key]["code"] = self.result['code']

                # Check if the execution failed
                if self.result['code']:
                    raise Exception(
                        'Executable raised a execption ' + self.result['message'])

        self.remove_reference_workflow()

    def run(self):
        """
        Runs the thread where the task will be executed
        """
        if self.workflow is not None:
            # Change the status

            self.set_status(dagon.Status.WAITING)

            # Wait for each previous tasks
            for task in self.prevs:
                # if its a process from other workflow
                if self.workflow.find_task_by_name(self.workflow.name, task.name) is None:
                    while True:
                        if self.workflow.is_api_available and task.transversal_workflow is not None:  # when is an asynchronous execution
                            try:
                                transversal_task = self.workflow.api.get_task(task.transversal_workflow, task.name)[
                                    'task']  # get the task from the external workflow using the api
                                if transversal_task['status'] == dagon.Status.FINISHED.value or transversal_task[
                                        'status'] == dagon.Status.FAILED.value:
                                    break
                                else:
                                    sleep(1)
                            except Exception as e:
                                task.set_status(dagon.Status.FAILED)
                                self.workflow.logger.warning(
                                    'Worflow dependence not found, Error: ' + str(e))
                                break
                        # when is used the dag_tps structure
                        elif task.status == dagon.Status.FINISHED or task.status == dagon.Status.FAILED:
                            break
                        else:
                            sleep(.5)
                else:
                    while True:
                        # if this happends, the workflow is probably a meta-workflow
                        if task.status == dagon.Status.WAITING or task.status == dagon.Status.READY:
                            sleep(.5)
                        else:
                            task.join()
                            break

            # Check if one of the previous tasks crashed
            for task in self.prevs:
                if task.status == dagon.Status.FAILED:
                    self.set_status(dagon.Status.FAILED)
                    return

            # Change the status
            self.set_status(dagon.Status.RUNNING)
            # Execute the task Job
            self.workflow.logger.debug("%s: Executing...", self.name)
            # self.semaphore.acquire()
            self.execute()
            sleep(2)
            # self.semaphore.release()
            """try:
                self.workflow.logger.debug("%s: Executing...", self.name)
                self.execute()
            except Exception, e:
                self.workflow.logger.error("%s: Except: %s", self.name, str(e))
                self.set_status(dagon.Status.FAILED)
                return
            # self.execute()"""

            # Start all next task
            for task in self.nexts:
                if task.status == dagon.Status.READY:
                    self.workflow.logger.debug(
                        "%s: Starting task: %s", self.name, task.name)
                    try:
                        task.start()
                    except:
                        self.workflow.logger.warn(
                            "%s: Task %s already started.", self.name, task.name)

            # Change the status
            # self.workflow.api.update_task(self.workflow.workflow_id, self.name, "working_dir", self.working_dir)
            self.set_status(dagon.Status.FINISHED)
            return

    def get_public_key(self):
        """
        Return the temporal public key to this machine

        :return: public key
        :rtype: str with the public key
        """
        pass

    def add_public_key(self, key):
        """
        Add a SSH public key on the remote machine

        :param key: Path to the public key
        :type key: str
        :return: result of the execution
        :rtype: dict() with the execution output (str) and code (int)
        """
        pass

    def remove_from_workflow(self):
        """
        Remove the reference to the workflow
        For each workflow:// in the command
        """
        # Remove the reference
        # For each workflow:// in the command

        # Index of the starting position
        pos = 0
        temp = self.command
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                pass
            else:
                temp = temp.replace(workflow_name, "")

            # Go to the next element
            pos = pos2
        return temp

    def get_how_im_script(self):
        """
        Create the script to get the context where the task will be executed

        :return: Context script
        :rtype: str
        """

        return r"""
# Initialize
machine_type="none"
public_id="none"
user="none"
status_sshd="none"
status_ftpd="none"
#get http communication protocol
curl_or_wget=$(if hash curl 2>/dev/null; then echo "curl"; elif hash wget 2>/dev/null; then echo "wget"; fi);


if [ $curl_or_wget = "wget" ]; then
  public_ip=`wget -q -O- https://ipinfo.io/ip`
else
  public_ip=`curl -s https://ipinfo.io/ip`
fi



# If no public ip is available, then it is a cluster node
machine_type="cluster-node"
private_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|head -n 1`

if [ "$private_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  private_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|grep -v "192.168."|grep -v "172.16."|grep -v "10."|head -n 1`
fi

#net-tools is not installed, try with ip -o route

if [ "$private_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  private_ip=`ip -o route get to 8.8.8.8 | sed -n 's/.*src \([0-9.]\+\).*/\\1/p'`
fi

# Check if the secure copy is available
status_sshd=`systemctl status sshd 2>/dev/null | grep 'Active' | awk '{print $2}'`
if [ "$status_sshd" == "" ]
then
  status_sshd="none"
fi

# Check if the ftp is available
status_ftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_ftpd" == "" ]
then
  status_ftpd="none"
fi

# Check if the grid ftp is available
status_gsiftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "" ]
then
  status_gsiftpd="none"
fi


# Get the user
user=$USER

echo "no" | ssh-keygen  -b 2048 -t rsa -f ssh_key -q -N ""  >/dev/null

# Construct the json
json="{\\\"type\\\":\\\"$machine_type\\\",\\\"public_ip\\\":\\\"$public_ip\\\",\\\"ip\\\":\\\"$private_ip\\\",\\\"user\\\":\\\"$user\\\",\\\"SCP\\\":\\\"$status_sshd\\\",\\\"FTP\\\":\\\"$status_ftpd\\\",\\\"GRIDFTP\\\":\\\"$status_gsiftpd\\\"}"
echo $json
"""
