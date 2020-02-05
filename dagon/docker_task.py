from dagon import Batch
from dagon.remote import RemoteTask
from dagon.dockercontainer import Container
from dagon.dockercontainer import DockerClient
from dagon.dockercontainer import DockerRemoteClient
from dagon.task import Task


class DockerTask(Batch):
    """
    ***Represents a task running on a docker container***

    :ivar docker_client: client to manages the container
    :vartype docker_client: :class:`dagon.dockercontainer.DockerClient`

    :ivar container: represents a docker container
    :vartype container: :class:`dagon.dockercontainer.Container`

    """

    def __init__(self, name, command, image=None, container_id=None, working_dir=None, endpoint=None, remove=True, volume=None,transversal_workflow=None):

        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param image: container image
        :type image: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str

        :param remove: if it's True the container is removed after the task ends its execution
        :type remove: bool
        """

        Task.__init__(self, name, command, working_dir=working_dir,transversal_workflow=transversal_workflow)
        self.command = command
        self.container_id = container_id
        self.container = None
        self.remove = remove
        self.image = image
        self.endpoint = endpoint
        self.volume = volume
        self.docker_client = DockerClient()

    def __new__(cls, *args, **kwargs):
        if "ip" in kwargs:
            return super(Task, cls).__new__(DockerRemoteTask)
        else:
            return super(DockerTask, cls).__new__(cls)

    def include_command(self, body):
        """
        Include the command to execute in the script body

        :param body: Script body
        :type body: str

        :return: Script body with the command
        :rtype: string
        """

        body = super(DockerTask, self).include_command(body)
        body = "cd " + self.working_dir + ";" + body
        body = self.container.exec_in_cont(body) + "\n"
        return body

    def pre_process_command(self, command):
        """
        Add some post process commands after the task execution. Also creates the docker container.

        :param command: Command to be executed
        :type command: str

        :return: Command post-processed
        :rtype: string
        """

        if self.container is None:
            self.container_id = self.create_container() if self.container_id is None else self.container_id
            self.container = Container(self.container_id.rstrip(), self.docker_client)
        return super(DockerTask, self).pre_process_command(command)

    # Create a Docker container
    def create_container(self):
        """
        Creates the container where the task will be executed

        :return: container key
        :rtype: string

        :raises Exception: a problem occurred while container creation
        """

        command = DockerClient.form_string_cont_creation(image=self.image,
                                                         volume=self.volume,
                                                         dagon_volume={"host": self.workflow.get_scratch_dir_base(),
                                                                 "container": self.workflow.get_scratch_dir_base()})

        result = self.docker_client.exec_command(command)
        if result['code']:
            raise Exception(self.result["message"].rstrip())
        return result['output']

    def remove_container(self):
        """
        Removes a docker container
        """
        self.container.stop()
        if self.remove:
            self.container.rm()

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

        # Invoke the base method
        Task.on_execute(self, script, script_name)
        return Batch.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)
        # return self.docker_client.exec_command(self.working_dir + "/.dagon/" + script_name)"""

    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """
        super(DockerTask, self).on_garbage()
        self.remove_container()


class DockerRemoteTask(RemoteTask, DockerTask):
    """
    **Represents a docker task running on a remote machine**

    :ivar docker_client: client to manages the container
    :vartype docker_client: :class:`dagon.dockercontainer.DockerRemoteClient`
    """

    def __init__(self, name, command, image=None, container_id=None, ip=None, ssh_username=None, keypath=None,
                 working_dir=None, remove=True, endpoint=None):
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param image: container image
        :type image: str

        :param endpoint: Globus endpoint ID
        :type endpoint: str

        :param remove: if it's True the container is removed after the task ends its execution
        :type remove: bool

        :param ip: IP address of the machine where the container will be created
        :type ip: str

        :param ssh_username: UNIX username to connect through SSH
        :type ssh_username: str

        :param keypath: Path to the public key
        :type keypath: str
        """

        DockerTask.__init__(self, name, command, container_id=container_id, working_dir=working_dir, image=image,
                            remove=remove, endpoint=endpoint)
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username, keypath=keypath, command=command, ip=ip,
                            working_dir=working_dir)
        self.docker_client = DockerRemoteClient(self.ssh_connection)

    def on_execute(self, launcher_script, script_name):
        """
        Execute the task script

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)

        """

        RemoteTask.on_execute(self, launcher_script, script_name)
        return self.ssh_connection.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)

    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """
        RemoteTask.on_garbage(self)
        self.remove_container()
