from dagon import Batch
from dagon.remote import RemoteTask
from dagon.task import Task

try:
    import docker
except ImportError as exc:
    raise ImportError(
        "Docker support requires the 'docker' extra: "
        "python -m pip install 'dagonstar[docker]'"
    ) from exc


class DockerTask(Batch):
    """
    ***Represents a task running on a docker container***

    :ivar docker_client: client to manages the container
    :vartype docker_client: :class:`dagon.dockercontainer.DockerClient`

    :ivar container: represents a docker container
    :vartype container: :class:`dagon.dockercontainer.Container`

    """

    def __init__(self, name, command, image=None, container_id=None, working_dir=None, globusendpoint=None, remove=True, volume=None, transversal_workflow=None):
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param image: container image
        :type image: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str

        :param remove: if it's True the container is removed after the task ends its execution
        :type remove: bool
        """

        Task.__init__(self, name, command, working_dir=working_dir,
                      transversal_workflow=transversal_workflow, globusendpoint=globusendpoint)
        self.command = command
        self.container_id = container_id
        self.container = None
        self.remove = remove
        self.image = image
        self.volume = volume
        self.docker_client2 = docker.from_env()

        # self.docker_client = DockerClient()

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
        command = "docker exec -t " + self.container.id + " sh -c \"" + body.strip() + "\" \n"
        return command

    def pre_process_command(self, command):
        """
        Add some post process commands after the task execution. Also creates the docker container.

        :param command: Command to be executed
        :type command: str

        :return: Command post-processed
        :rtype: string
        """

        if self.container is None:
            self.container = self.create_container()
        else:
            self.container = self.get_running_container()
        return super(DockerTask, self).pre_process_command(command)

    def pull_image(self, image):
        """
        Pull a Docker image from Docker Hub

        :param image: Image name
        :type image: str

        :return: pull result
        :rtype: dict()
        """

        try:
            self.docker_client2.images.pull(image)  # Pull the Docker image
            self.workflow.logger.info(
                "%s: Successfully pulled %s", self.name, image)
        except docker.errors.APIError as e:
            self.workflow.logger.error(f"An error occurred: {e}")

        # return self.docker_client.pull_image(image)

    # Create a Docker container
    def create_container(self):
        """
        Creates the container where the task will be executed

        :return: container key
        :rtype: string

        :raises Exception: a problem occurred while container creation
        """

        self.pull_image(self.image)  # pull image

        volumes = {
            self.workflow.get_scratch_dir_base(): {"bind": self.workflow.get_scratch_dir_base(), "mode": "rw"},
        }

        if self.volume is not None:
            volumes[self.volume] = {"bind": self.volume, "mode": "rw"}

        try:
            container = self.docker_client2.containers.run(
                self.image, detach=True, stdin_open=True, volumes=volumes)
            self.workflow.logger.info(
                "%s: Container created with %s", self.name, container.id)
            return container
        except Exception as e:
            raise Exception(str(e))

    def get_running_container(self):
        try:
            container = self.docker_client2.containers.get(self.container_id)
            return container
        except Exception as e:
            raise Exception(str(e))

    def remove_container(self):
        """
        Removes a docker container
        """
        self.container.stop()
        if self.remove:
            self.container.remove()

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
                 working_dir=None, remove=True, globusendpoint=None):
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param image: container image
        :type image: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str

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
                            remove=remove, globusendpoint=globusendpoint)
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username, keypath=keypath, command=command, ip=ip,
                            working_dir=working_dir, globusendpoint=globusendpoint)
        self.docker_client2 = docker.DockerClient(base_url=f"ssh://{ssh_username}@{ip}")

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
