from fabric.api import local, env
from fabric.context_managers import settings, hide

from dagon.task import Task
from dagon.remote import RemoteTask


class Batch(Task):
    """
    **Executes a Batch task**
    """

    def __init__(self, name, command, working_dir=None, endpoint=None, transversal_workflow=None):
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str
        """
        Task.__init__(self, name, command, working_dir,transversal_workflow = transversal_workflow)

    def __new__(cls, *args, **kwargs):
        """Create an Batch task local or remote

           Keyword arguments:
           name -- task name


           command -- command to be executed
           working_dir -- directory where the outputs will be placed
           ip -- hostname or ip of the machine where the task will be executed
           ssh_username -- username in remote machine
           keypath -- path to the private keypath
        """
        #if "ip" in kwargs:
        #    return super(Task, cls).__new__(RemoteBatch)
        #else:
        #    return super(Batch, cls).__new__(cls, *args, **kwargs)
        if "ip" in kwargs:
            return super().__new__(RemoteBatch)
        else:
            return super().__new__(cls)

    @staticmethod
    def execute_command(command):
        """
        Executes a local command

        :param command: command to be executed
        :type command: str
        :return: execution result
        :rtype: dict() with the execution output (str), code (int) and error (str)
        """
        # Execute the bash command
        with settings(
                hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True
        ):
            result = local(command, capture=True)
            # check for an error
            code, message = 0, ""
            if len(result.stderr):
                code, message = 1, result.stderr

            return {"code": code, "message": message, "output": result.stdout}

    def on_execute(self, script, script_name):
        """
        Invoke the script specified

        :param script: content script
        :type script: str
        :param script_name: script name
        :type script_name: str
        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # Invoke the base method
        super(Batch, self).on_execute(script, script_name)
        return Batch.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)

    # returns public key
    def get_public_key(self):
        """
        Return the temporal public key to this machine

        :return: public key
        :rtype: str with the public key
        """
        command = "cat " + self.working_dir + "/.dagon/ssh_key.pub"
        result = Batch.execute_command(command)
        return result['output']

    def add_public_key(self, key):
        """
        Add a SSH public key on the remote machine

        :param key: Path to the public key
        :type key: str
        :return: result of the execution
        :rtype: dict() with the execution output (str) and code (int)
        """
        command = "echo " + key.strip() + "| cat >> ~/.ssh/authorized_keys"
        result = Batch.execute_command(command)
        return result


class RemoteBatch(RemoteTask, Batch):
    """
    **Execute a Batch task on a remote machine**
    """

    def __init__(self, name, command, ssh_username=None, keypath=None, ip=None, working_dir=None, endpoint=None):
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed
        :type command: str

        :param ssh_username: UNIX username to connect through SSH
        :type ssh_username: str

        :param keypath: path to the public key
        :type keypath: str

        :param ip: IP address to connect to the remote machine
        :type ip: str

        :param working_dir: path of the working directory on the remote machine
        :type working_dir: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str
        """
        RemoteTask.__init__(self, name, ssh_username, keypath, command, ip=ip, working_dir=working_dir,
                            endpoint=endpoint)

    def on_execute(self, launcher_script, script_name):
        """
        Execute a script on the remote machine

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # Invoke the base method
        RemoteTask.on_execute(self, launcher_script, script_name)
        result = self.ssh_connection.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)
        return result


class Slurm(Batch):
    """
    **Run a task using Slurm**

    :ivar partition: partition where the task will be executed
    :vartype partition: str

    :ivar ntask: number of parallel tasks to be executed
    :vartype ntask: int
    """

    def __init__(self, name, command, partition=None, ntasks=None, working_dir=None, endpoint=None):

        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed
        :type command: str

        :param partition: partition where the task will be executed
        :type partition: str

        :param ntasks: number of parallel tasks to be executed
        :type ntasks: int

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str
        """

        Batch.__init__(self, name, command, working_dir, endpoint=endpoint)
        self.partition = partition
        self.ntasks = ntasks

    def __new__(cls, *args, **kwargs):
        """Create an Slurm task local or remote

           Keyword arguments:
           name -- task name
           command -- command to be executed
           partition -- partition where the task is going to be executed
           ntasks -- number of tasks to execute
           working_dir -- directory where the outputs will be placed
        """

        if "ip" in kwargs:
            return super().__new__(RemoteSlurm)
        else:
            return super().__new__(cls)

    def generate_command(self, script_name):

        """
        Generates the Slurm command including the partition and number of task parameters

        :param script_name: script to be executed
        :type script: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        partition_text = ""
        if self.partition is not None:
            partition_text = "--partition=" + self.partition

        ntasks_text = ""
        if self.ntasks is not None:
            ntasks_text = "--ntasks=" + str(self.ntasks)

        # Add the slurm batch command
        # command = "sbatch " + partition_text + " " + ntasks_text + " --job-name=" + self.name + " --chdir=" + self.working_dir + " --output=" + self.working_dir + "/.dagon/stdout.txt --wait " + self.working_dir+"/.dagon/launcher.sh"
        command = "sbatch " + partition_text + " " + ntasks_text + " -J " + self.name + " -D " \
                  + self.working_dir + " -W " + self.working_dir + "/.dagon/" + script_name
        return command

    def on_execute(self, script, script_name):

        """
        Execute a script using slurm

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        super().on_execute(script, script_name)

        if script_name == "context.sh":
            return Batch.execute_command(self.working_dir + "/.dagon/" + script_name)

        command = self.generate_command(script_name)

        # Execute the bash command
        result = Batch.execute_command(command)
        return result


class RemoteSlurm(RemoteTask, Slurm):
    """
    ** Represent a task that runs on a remote slurm deployment **
    """

    def __init__(self, name, command, partition=None, ntasks=None, working_dir=None, ssh_username=None, keypath=None,
                 ip=None, endpoint=None):
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed
        :type command: str

        :param partition: partition where the task will be executed
        :type partition: str

        :param ntasks: number of parallel tasks to be executed
        :type ntasks: int

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str

        :param ssh_username: UNIX username on the remote
        :type endpoint: str

        :param keypath: Path to the public key
        :type keypath: str

        :param ip: IP address to connect to the remote machine
        :type ip: str

        """
        Slurm.__init__(self, name, command, working_dir=working_dir, partition=partition, ntasks=ntasks,
                       endpoint=endpoint)
        RemoteTask.__init__(self, name, ssh_username, keypath, command, ip, working_dir, endpoint=None)

    def on_execute(self, script, script_name):
        """
        Execute a script using slurm

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        RemoteTask.on_execute(self, script, script_name)
        if script_name == "context.sh":
            return self.ssh_connection.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)

        command = self.generate_command(script_name)
        # Execute the bash command
        result = self.ssh_connection.execute_command(command)
        return result
