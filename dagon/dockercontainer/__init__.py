from fabric.api import local, settings, hide


class DockerClient(object):
    """
    Manages the communication with a docker container
    """

    def exec_command(self, command):
        """
        executes a command on a container

        :param command: command to be executed
        :type command: str

        :return: execution results
        :rtype: dict(str, object)
        """

        with settings(
                hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True
        ):
            res = local(command, capture=True)

            if len(res.stderr):
                return {"code": 1, "message": res.stderr}
            elif res.return_code != 0:
                return {"code": 1, "message": res.stdout}
            else:
                return {"code": 0, "output": res.stdout}

    @staticmethod
    def form_string_cont_creation(image, command=None, volume=None, dagon_volume=None, ports=None):
        """
        creates an string to create the container on the remote machine

        :param image: image of the container
        :type image: str

        :param command: command to be executed
        :type command: str

        :param volume: shared volume with the host system
        :type volume: dict(str, str) => {"host":"host_path", "container":"container_path"}

        :param ports: ports expose with the host system
        :type ports: dict(str, str) => {"host":"host_port", "container":"container_port"}

        :return: string with the command to create the container
        :rtype: str
        """

        docker_command = "docker run --net=\"host\""

        docker_command += " -t -d"

        if volume is not None:
            docker_command += " -v \'%s\':\'%s\'" % (volume['host'], volume['container'])
        if dagon_volume is not None:
            docker_command += " -v \'%s\':\'%s\'" % (dagon_volume['host'], dagon_volume['container'])
        if ports is not None:
            docker_command += " -p \'%s\':\'%s\'" % (ports['host'], ports['container'])
        docker_command += " %s" % image

        if command is not None:
            docker_command += " " + command

        return docker_command


class DockerRemoteClient(DockerClient):

    """
    Manages the execution of command on remote containers
    """

    def __init__(self, ssh):
        """
        :param ssh: ssh connection with remote host
        """
        self.ssh = ssh

    def exec_command(self, command):
        """
        executes a command on remote container

        :param command: command to execute on the remote machine
        :type command: str

        :return: execution results
        :rtype: dict(str, object)
        """
        with settings(
                hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True
        ):
            result = self.ssh.execute_command(command)
            return result


class Container(object):

    """
    **Represents a docker container**
    """

    def __init__(self, key, client):
        """
        :param key: docker container key
        :type key: str

        :param client: docker client
        :type client: :class:`DockerClient`
        """
        self.key = key
        self.client = client

    def logs(self):
        """
        get the logs from the container

        :return: container logs
        :rtype: str
        """
        command = "docker logs " + self.key
        res = self.client.exec_command(command)
        return res

    def exec_in_cont(self, command):
        """
        create an string with the command to execute something on the container

        :param command: command to execute
        :type command: str

        :return: container command
        :rtype: str
        """
        docker_command = "docker exec -t " + self.key + " sh -c \"" + command.strip() + "\""
        # res = self.client.exec_command(docker_command)
        return docker_command

    def rm(self, force=False):
        """
        removes a docker container

        :param force: force to remove a container in execution
        :rtype force: bool

        :return: True if the container has been removed
        :rtype: bool
        """

        band = "-f" if force else ""
        command = "docker rm %s %s" % (band, self.key)

        try:
            self.client.exec_command(command)
        except Exception as e:
            return False
        return True

    def stop(self):
        """
        stops a container in execution

        :return: True if the container has been stopped
        :rtype: bool
        """
        command = "docker stop %s" % self.key
        try:
            self.client.exec_command(command)
        except Exception as e:
            print(e)
            return False
        return True
