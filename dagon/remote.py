from os.path import abspath

from communication.ssh import SSHManager
from dagon.cloud import CloudManager
from task import Task


class RemoteTask(Task):
    """
    **Representates a task that is executed in a cloud instance, remote docker container,
    remote server or remove cluster HPC**

    :ivar ip: IP address to access to the remote machine
    :vartype ip: str

    :ivar keypath: Path to the SSH public key
    :vartype keypath: str

    :ivar ssh_username: Username to connect by SSH
    :vartype ssh_username: str

    :ivar ssh_connection: SSH connection with the machine
    :vartype ssh_connection: :class:`dagon.communDataFlow-Demication.ssh.SSHManager`
    """

    def __init__(self, name, ssh_username, keypath, command, ip=None, working_dir=None, endpoint=None,transversal_workflow=None):
        """

        :param name: Name of the task
        :type name: str

        :param ssh_username: UNIX username on the remote machine
        :type ssh_username: str

        :param keypath: Path to the public key
        :type keypath: str

        :param command: Command to be executed
        :type command: str

        :param ip: IP address to connect to the remote machine
        :type ip: str

        :param working_dir: Path of the working directory on the remote machine
        :type working_dir: str

        :param endpoint: Globus endpoint ID to transfer data with GridFTP
        :type endpoint: str

        """
        Task.__init__(self, name, command, working_dir=working_dir, endpoint=endpoint,transversal_workflow=transversal_workflow)
        self.transfer = None
        self.ip = ip
        self.keypath = abspath(keypath) if keypath is not None else keypath
        self.ssh_username = ssh_username
        self.ssh_connection = None
        #print name, self.ip, self.ssh_username
        if self.ip is not None and self.ssh_username is not None:
            self.ssh_connection = SSHManager(self.ssh_username, self.ip, self.keypath)

    def add_public_key(self, key):
        """
        Add a SSH public key on the remote machine

        :param key: Path to the public key
        :type key: str

        :return: result of the execution
        :rtype: dict() with result of the execution
        """
        command = "echo " + key.strip() + "| cat >> ~/.ssh/authorized_keys"
        result = self.ssh_connection.execute_command(command)
        return result

    def on_execute(self, script, script_name):
        """
        Execute an script on the remote machine

        :param script: script content
        :type key: str

        :param script_name: filename of the script
        :type key: str
        """
        # The launcher script name
        script_name = self.working_dir + "/.dagon/" + script_name
        # Create a temporary launcher script
        self.ssh_connection.create_file(script_name, script)

    # make dir
    def mkdir_working_dir(self, path):
        """
        Make a directory on the remote machine

        :param path: Path to the directory
        :type key: str

        :raises Exception: a problem occurred while the creation of the directory
        """
        #print self.ssh_connection
        res = self.ssh_connection.execute_command( "mkdir -p " + self.working_dir + "/.dagon")
        if res['code']:
            self.workflow.logger.error("%s: Error creating scratch directory on server %s", self.name, res['message'])
            raise Exception('Cannot create scratch directory on remote')

    # remove scratch directory
    def on_garbage(self):
        """
        Remove the scratch directory on the remote machine
        """
        self.ssh_connection.execute_command('mv {0} {1}'.format(self.working_dir,
                                            self.working_dir + "-removed"))

    def get_public_key(self):
        """
        Return the temporal public key to this machine

        :return: Public ke
        :rtype: str with the public key
        """
        command = "cat " + self.working_dir + "/.dagon/ssh_key.pub"
        result = self.ssh_connection.execute_command(command)
        return result['output']


class CloudTask(RemoteTask):
    """
    Class that represents a task executed on a cloud instance

    :ivar str instance_id: ID of the instance given by the cloud provider
    :ivar provider: cloud provider (see :class:`libcloud.compute.types.Provider`)
    :vartype provider: :class:`libcloud.compute.types.Provider`

    :ivar dict instance_flavour: characteristics of the instance
    :ivar dict key_options: ssh key options to connect to the instance
    :ivar node: Node where the task will be executed
    :vartype node: :class:`libcloud.compute.base.Node`

    :ivar bool stop_instance: True if the instance has to be stopped when the execution ends
    :ivar str instance_name: Name of the instance on the cloud provider
    """

    def __init__(self, name, command, provider, ssh_username, key_options, instance_id=None, instance_flavour=None,
                 instance_name=None, stop_instance=False, endpoint=None):
        """

        :param name: name of the task
        :type name: str

        :param command: command to be executed on the cloud instance
        :type command: str

        :param provider: cloud provider
        :type provider: :class:`libcloud.compute.types.Provider`

        :param ssh_username: UNIX username to connect through SSH
        :type ssh_username: str

        :param key_options: dictionary with the key options to connect to the instance
        :type key_options: dict

        :param instance_id: instance id on the cloud provider
        :type instance_id: str

        :param instance_flavour: characteristics of the instance (image, size, location)
        :type instance_flavour: dict

        :param instance_name: instance name on the cloud provider
        :type instance_name: str

        :param stop_instance: True if the instance has to be stoppend at the end of the task execution
        :type stop_instance: bool

        :param endpoint: Globus endpoint ID
        :type endpoint: str
        """
        super(CloudTask, self).__init__(name, ssh_username, key_options['key_path'], command, endpoint=endpoint)
        self.instance_id = instance_id
        self.provider = provider
        self.instance_flavour = instance_flavour
        self.key_options = key_options
        self.node = None
        self.stop_instance = stop_instance
        self.instance_name = instance_name

    def on_execute(self, script, script_name):
        """
        Execute a script on the cloud instance

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        RemoteTask.on_execute(self, script, script_name)
        return self.ssh_connection.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)

    def execute(self):
        """
        Execute the task on the remote cloud instance.

        #. Create or get the instace from the cloud provider.
        #. Get the public IPS available.
        #. Open the SSH connection with the instace.
        #. Execute the task.

        :raises Exception: a problem occurred while the execution of the task
        """
        self.instance_name = self.instance_name if self.instance_name is not None else self.workflow.name.strip() + \
                                                                                       "-" + self.name
        self.node = CloudManager.get_instance(instance_id=self.instance_id, keyparams=self.key_options,
                                              flavour=self.instance_flavour, provider=self.provider,
                                              name=self.instance_name)
        self.ip = self.node.public_ips[0]
        self.ssh_connection = SSHManager(self.ssh_username, self.ip, self.keypath)
        super(CloudTask, self).execute()

    def on_garbage(self):
        """
        Call the garbage collector

        #. Remove the scratch directory.
        #. The instance it is stopped if that is specified in the parameters of the task

        """
        RemoteTask.on_garbage(self)
        if self.stop_instance:
            self.ssh_connection.execute_command("shutdown -h now")
