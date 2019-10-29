import shutil
from json import loads
from threading import Thread
from threading import Semaphore
from os import makedirs, path, chmod
from time import time, sleep
from enum import Enum

import dagon


class TaskType(Enum):
    """
    Enum used to represent the main types tasks supported by dagon,
    remote tasks are supported by the RemoteClass but it should not be
    explicitly instantiate

    :cvar BATCH: Regular Batch task (local or remote)
    :cvar SLURM: Task executed using Slurm (local or remote)
    :cvar CLOUD: Task executed in a cloud instance (ec2, digital ocean and google cloud  tested with libcloud)
    :cvar DOCKER: Task executed on a docker container (local or remote)
    """

    BATCH = "batch"
    SLURM = "slurm"
    CLOUD = "cloud"
    DOCKER = "docker"


# Different types os tasks and their module and class name
tasks_types = {
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

    def __init__(self, name, command, working_dir=None,transversal_workflow=None):
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed by the task
        :type command: str

        :param working_dir: path to the directory where the task is be executed
        :type working_dir: str

        """
        Thread.__init__(self)
        self.ssh_connection = None
        self.name = name
        self.nexts = []
        self.prevs = []
        self.reference_count = 0
        self.remove_scratch_dir = False
        self.running = False
        self.workflow = None
        self.set_status(dagon.Status.READY)
        self.working_dir = working_dir
        self.command = command
        self.info = None
        self.dag_tps = None
        self.transversal_workflow = transversal_workflow
        self.workflows=None

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
        return self.info["ip"]

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
                self.workflow.api.update_task_status(self.workflow.workflow_id, self.name, status.name)

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
            self.workflow.api.add_dependency(self.workflow.workflow_id, self.name, task.name)

    def add_transversal_point(self, task):
        """
        Add a dependency from other task

        :param task: :class:`dagon.task.Task` instance dependency
        :type task: :class:`dagon.task.Task`
        """
        self.prevs.append(task)

        if self.workflow.is_api_available:  # add in the server
            self.workflow.api.add_dependency(self.workflow.workflow_id, self.name, task.name)


    # Increment the reference count
    def increment_reference_count(self):
        """
        Increments the reference count
        """
        self.reference_count = self.reference_count + 1

    # Call garbage collector (remove scratch directory, container, cloud instace, etc)
    # implemented by each task class
    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """
        shutil.move(self.working_dir, self.working_dir + "-removed")

    # Decremet the reference count
    def decrement_reference_count(self):
        """
        Decremet the reference count. When the number of references is equals to zero, the garbage collector is called
        """
        self.reference_count = self.reference_count - 1

        # Check if the scratch directory must be removed
        if self.reference_count == 0 and self.remove_scratch_dir is True:
            # Call garbage collector (remove scratch directory, container, cloud instace, etc)
            #self.on_garbage()
            # Perform some logging
            self.workflow.logger.debug("Removed %s", self.working_dir)

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
        #get workflows of dag_tps
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
                task = self.workflow.find_task_by_name(workflow_name, task_name)
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

            if task is None: #if is None means that task is from another WF maybe in the dagon service
                if self.workflow.is_api_available:
                    workflow_id=self.workflow.api.get_workflow_by_name(workflow_name)
                    transversal_task = self.workflow.api.get_task(workflow_id,task_name) ['task']#get the task from the external workflow
                    transversal_task = DagonTask(TaskType[transversal_task['type'].upper()],transversal_task['name'],transversal_task['command'],
                        transversal_workflow=workflow_id, working_dir=transversal_task['working_dir'])
                    self.add_transversal_point(transversal_task)
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

        stager = dagon.Stager()

        # Initialize the script
        header = "#! /bin/bash\n"
        header = header + "# This is the DagOn launcher script\n\n"
        header = header + "code=0\n"
        # Add and execute the howim script

        context_script = header + "cd " + self.working_dir + "/.dagon\n"
        context_script += header + self.get_how_im_script() + "\n\n"

        result = self.on_execute(context_script, "context.sh")  # execute context script
        if result['code']:
            raise Exception(result['message'])
        self.set_info(loads(result['output']))

        ### start the creation of the launcher.sh script
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
            local_path = arg.replace(workflow_name + "/" + task_name, "")
            
            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object
            #task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None: break


            if task is None: #if is None means that task is from another WF maybe in the dagon service
                if self.workflow.is_api_available:
                    workflow_id=self.workflow.api.get_workflow_by_name(workflow_name)
                    transversal_task = self.workflow.api.get_task(workflow_id,task_name) ['task']#get the task from the external workflow
                    task = DagonTask(TaskType[transversal_task['type'].upper()],transversal_task['name'],transversal_task['command'],
                        transversal_workflow=workflow_id, working_dir=transversal_task['working_dir'])

            # Check if the refernced task is consistent
            if task is not None:
                # Evaluate the destiation path
                dst_path = self.working_dir + "/.dagon/inputs/" + workflow_name + "/" + task_name

                # Create the destination directory
                header = header + "\n\n# Create the destination directory\n"
                header = header + "mkdir -p " + dst_path + "/" + path.dirname(local_path) + "\n"
                header = header + "if [ $? -ne 0 ]; then code=1; fi\n\n"
                # Add the move data command
                header = header + stager.stage_in(self, task, dst_path, local_path)

                # Change the body of the command
                body = body.replace(dagon.Workflow.SCHEMA + arg, dst_path + "/" + local_path)
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
        chmod(script_name, 0744)

    # create path using mkdirs
    def mkdir_working_dir(self, path):
        """
        Make the working directory

        :param path: Path to the working directory
        :type path: str
        """
        makedirs(path)

    def create_working_dir(self):
        """
        Create the working directory
        """
        if self.working_dir is None:
            # Set a scratch directory as working directory
            self.working_dir = self.workflow.get_scratch_dir_base() + "/" + self.get_scratch_name()



            # Set to remove the scratch directory
            self.remove_scratch_dir = True

        # Create scratch directory
        self.mkdir_working_dir(self.working_dir + "/.dagon")
        self.workflow.logger.debug("%s: Scratch directory: %s", self.name, self.working_dir)
        if self.workflow.is_api_available:  # change scratch directory on server
            try:
                self.workflow.api.update_task(self.workflow.workflow_id, self.name, "working_dir", self.working_dir)
            except Exception, e:
                self.workflow.logger.error("%s: Error updating scratch directory on server %s", self.name, e)

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
            #task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None: break

            # Check if the refernced task is consistent
            if task is not None:
                # Remove the reference from the task
                task.decrement_reference_count()

            # Go to the next element
            pos = pos2

    # Method execute
    def execute(self):
        """
        Execute the task

        :raises Exception: a problem occurred during the task  execution
        """
        self.create_working_dir()

        # Apply some command pre processing
        launcher_script = self.pre_process_command(self.command)      
        # Apply some command post processing
        launcher_script = self.post_process_command(launcher_script)

        # Execute only if not dry
        if self.workflow.dry is False:
            # Invoke the actual executor
            start_time = time()
            self.result = self.on_execute(launcher_script, "launcher.sh")
            self.workflow.logger.debug("%s Completed in %s seconds ---" % (self.name, (time() - start_time)))

            # Check if the execution failed
            if self.result['code']:
                raise Exception('Executable raised a execption ' + self.result['message'])

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
                if self.workflow.find_task_by_name(self.workflow.name, task.name) == None: #if its a process from other workflow
                    while(True):
                        if self.workflow.is_api_available and task.transversal_workflow is not None:
                            try:
                                transversal_task = self.workflow.api.get_task(task.transversal_workflow,task.name)['task'] #get the task from the external workflow using the api
                                if transversal_task['status']==dagon.Status.FINISHED.value or transversal_task['status']==dagon.Status.FAILED.value:
                                    break
                                else:
                                    sleep(1)
                            except Exception as e:
                                task.set_status(dagon.Status.FAILED)
                                self.workflow.logger.warning('Worflow dependence not found, Error: '+str(e))
                                break
                        elif task.status==dagon.Status.FINISHED or task.status==dagon.Status.FAILED:
                            break
                        else:
                            sleep(.5)
                else:
                    while (True):
                        if task.status ==dagon.Status.WAITING or task.status ==dagon.Status.READY: #if this happends, the workflow is probably a meta-workflow
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
            self.workflow.logger.debug("%s: Executing...", self.name)
            self.semaphore.acquire()
            self.execute()
            sleep(2)
            self.semaphore.release()
            # Execute the task Job
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
                    self.workflow.logger.debug("%s: Starting task: %s", self.name, task.name)
                    try:
                        task.start()
                    except:
                        self.workflow.logger.warn("%s: Task %s already started.", self.name, task.name)

            # Change the status
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
                temp = temp.replace(workflow_name,"")
                
            # Go to the next element
            pos = pos2
        return temp

    def get_how_im_script(self):
        """
        Create the script to get the context where the task will be executed

        :return: Context script
        :rtype: str
        """
        return """
# Initialize
machine_type="none"
public_id="none"
user="none"
status_sshd="none"
status_ftpd="none"
status_skycds="none"

#get http communication protocol
curl_or_wget=$(if hash curl 2>/dev/null; then echo "curl"; elif hash wget 2>/dev/null; then echo "wget"; fi);


if [ $curl_or_wget = "wget" ]; then
  public_ip=`wget -q -O- https://ipinfo.io/ip`
else
  public_ip=`curl -s https://ipinfo.io/ip`
fi

if [ "$public_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  public_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|grep -v "192.168."|grep -v "172.16."|grep -v "10."|head -n 1`
fi

if [ "$public_ip" == "" ]
then
  # If no public ip is available, then it is a cluster node
  machine_type="cluster-node"
  public_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|head -n 1`
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

#check if skycds container is running
status_docker=`systemctl status docker 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "active" ]
then
    if [ "$(docker ps -aq -f status=running -f name=client)" ]; then
    # cleanup
        status_skycds="active"
    fi
fi

# Get the user
user=$USER

echo "no" | ssh-keygen  -b 2048 -t rsa -f ssh_key -q -N ""  >/dev/null

# Construct the json
json="{\\\"type\\\":\\\"$machine_type\\\",\\\"ip\\\":\\\"$public_ip\\\",\\\"user\\\":\\\"$user\\\",\\\"SCP\\\":\\\"$status_sshd\\\",\\\"FTP\\\":\\\"$status_ftpd\\\",\\\"GRIDFTP\\\":\\\"$status_gsiftpd\\\",\\\"SKYCDS\\\":\\\"$status_skycds\\\"}"
echo $json
"""
