import paramiko
from paramiko import SSHClient

from dagon.communication import is_port_open


# To manage SSH connections
class SSHManager:

    """
    Manages SSH connections with a remote machine

    :ivar username: ssh username
    :vartype username: str

    :ivar host: IP of the remote machine
    :vartype host: str

    :ivar keypath: path to the private key
    :vartype keypath: str

    :ivar connection: connection with the remote machine
    :vartype connection: str

    """

    def __init__(self, username, host, keypath):

        """
        :param username: ssh username
        :type username: str

        :param host: IP of the remote machine
        :type host: str

        :param keypath: path to the private key
        :type keypath: str
        """

        self.username = username
        self.host = host
        self.keypath = keypath
        self.connection = self.get_ssh_connection()

    def get_connection(self):
        """
        return the connection

        :return: connection
        """
        return self.connection

    def create_file(self, filepath, content):
        """
        creates a file on the remote machine

        :param filepath: path to the file
        :type filepath: str

        :param content: content of the file
        :type filepath: str
        """

        sftp = self.get_connection().open_sftp()
        f = sftp.open(filepath, 'w')
        f.write(content)
        f.close()

    def get_ssh_connection(self):
        """
        returns a new ssh connection with the remote machine

        :return: ssh connection
        """

        ssh = SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while not is_port_open(self.host, 22):
            continue
        if self.keypath is None:
            ssh.connect(self.host, username=self.username)
        else:
            ssh.connect(self.host, username=self.username, key_filename=self.keypath)
        return ssh

    def execute_command(self, command):
        """
        execute command in remothe machine over SSH

        :param command: command to execute on the remote machine
        :type command: str

        :return: execution results
        :rtype: dict(str, object)
        """
        _, stdout, stderr = self.connection.exec_command(command)
        code = stdout.channel.recv_exit_status()
        stdout = "\n".join(stdout.readlines())
        stderr = "\n".join(stderr.readlines())

        if code == 0:
            return {"code": 0, "output": stdout}
        else:
            return {"code": 1, "message": stdout}