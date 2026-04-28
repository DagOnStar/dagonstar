from dagon import Batch
from dagon.remote import RemoteTask
from dagon.task import Task

import docker


class DockerTask(Batch):
    """
    ***Represents a task running on a docker container***

    :ivar docker_client: client to manages the container
    :vartype docker_client: :class:`dagon.dockercontainer.DockerClient`

    :ivar container: represents a docker container
    :vartype container: :class:`dagon.dockercontainer.Container`

    """

    def __init__(self, name, command, image=None, container_id=None, working_dir=None, globusendpoint=None, remove=True, volume=None, devices=None, transversal_workflow=None, pull=True):
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
        
        :param pull: if it's True the image will be pulled from registry
        :type pull: bool
        """

        Task.__init__(self, name, command, working_dir=working_dir,
                      transversal_workflow=transversal_workflow, globusendpoint=globusendpoint)
        self.command = command
        self.container_id = container_id
        self.container = None
        self.remove = remove
        self.image = image
        self.volume = volume
        self.devices = devices
        self.pull = pull  # ← AÑADIDO
        try:
            self.docker_client2 = docker.from_env()
        except Exception:
            self.docker_client2 = None

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
        
        cd_command = f"cd {self.working_dir} && "
        container_command = cd_command + body.strip()
        
        # Crear un script temporal para evitar problemas con heredocs anidados
        temp_script = f"{self.working_dir}/.dagon/container_script.sh"
        
        # Paso 1: Crear el script en el host usando cat con un delimitador único
        command = f"cat > {temp_script} << 'END_OF_CONTAINER_SCRIPT'\n"
        command += f"#!/bin/bash\n"
        command += f"{container_command}\n"
        command += "END_OF_CONTAINER_SCRIPT\n"
        
        # Paso 2: Dar permisos de ejecución
        command += f"chmod +x {temp_script}\n"
        
        # Paso 3: Copiar el script al contenedor y ejecutarlo
        command += f"docker cp {temp_script} {self.container.id}:/tmp/task_script.sh\n"
        command += f"docker exec -i {self.container.id} bash /tmp/task_script.sh | tee {self.working_dir}/.dagon/stdout.txt\n"
        
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
        except Exception as e:
            self.workflow.logger.error(f"An error occurred: {e}")

        # return self.docker_client.pull_image(image)

    def create_container(self):
        """
        Creates the container where the task will be executed
        """
        # ← MODIFICADO: Solo hacer pull si self.pull == True
        if self.pull:
            self.pull_image(self.image)

        volumes = {}
        
        # Añadir scratch directory base normalizado
        scratch_base = self.workflow.get_scratch_dir_base().rstrip('/')
        volumes[scratch_base] = {"bind": scratch_base, "mode": "rw"}

        if self.volume is not None:
            # Parse volume string (format: host_path:container_path or just host_path)
            if ':' in self.volume:
                host_path, container_path = self.volume.split(':', 1)
                host_path = host_path.rstrip('/')
                container_path = container_path.rstrip('/')
                
                if host_path not in volumes:
                    volumes[host_path] = {"bind": container_path, "mode": "rw"}
            else:
                normalized_volume = self.volume.rstrip('/')
                if normalized_volume not in volumes:
                    volumes[normalized_volume] = {"bind": normalized_volume, "mode": "rw"}

        # AÑADIR SOPORTE PARA DEVICES
        try:
            container_kwargs = {
                "image": self.image,
                "detach": True,
                "stdin_open": True,
                "volumes": volumes
            }
            
            # Añadir devices si están especificados
            if self.devices:
                container_kwargs["devices"] = self.devices
            
            container = self.docker_client2.containers.run(**container_kwargs)
            self.workflow.logger.info("%s: Container created with %s", self.name, container.id)
            return container
        except Exception as e:
            self.workflow.logger.error("%s: Failed to create container.", self.name)
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
                 working_dir=None, remove=True, globusendpoint=None, volume=None, devices=None, ssh_port=22, pull=True):  # ← AÑADIDO pull=True
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
        
        :param volume: Volume to mount in the container (host_path:container_path)
        :type volume: str
        
        :param ssh_port: SSH port (default: 22)
        :type ssh_port: int
        
        :param pull: if it's True the image will be pulled from registry
        :type pull: bool
        """

        DockerTask.__init__(self, name, command, container_id=container_id, working_dir=working_dir, image=image,
                            remove=remove, globusendpoint=globusendpoint, volume=volume, devices=devices, pull=pull)  # ← AÑADIDO pull=pull
        RemoteTask.__init__(self, name=name, ssh_username=ssh_username, keypath=keypath, command=command, ip=ip,
                            working_dir=working_dir, globusendpoint=globusendpoint, ssh_port=ssh_port)  
        
        # Construir la URL SSH con el puerto si no es el 22 por defecto
        if ssh_port != 22:
            base_url = f"ssh://{ssh_username}@{ip}:{ssh_port}"
        else:
            base_url = f"ssh://{ssh_username}@{ip}"
            
        self.docker_client2 = docker.DockerClient(base_url=base_url, timeout=300)

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