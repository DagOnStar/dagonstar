import logging
import secrets

import paramiko
from paramiko import SSHClient

from dagon.communication import is_port_open
from dagon.shell import join_command, quote


def _heredoc_delimiter(content):
    """Return a delimiter that cannot terminate the generated heredoc."""
    lines = set(content.splitlines())
    while True:
        delimiter = "DAGON_EOF_" + secrets.token_hex(16)
        if delimiter not in lines:
            return delimiter


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
    
    :ivar port: SSH port (default: 22)
    :vartype port: int

    :ivar connection: connection with the remote machine
    :vartype connection: str

    """

    def __init__(self, username, host, keypath, port=22):

        """
        :param username: ssh username
        :type username: str

        :param host: IP of the remote machine
        :type host: str

        :param keypath: path to the private key
        :type keypath: str
        
        :param port: SSH port (default: 22)
        :type port: int
        """

        self.username = username
        self.host = host
        self.keypath = keypath
        self.port = port
        self.connection = self.get_ssh_connection()
        self.logger = logging.getLogger()

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
        :type content: str
        """
        import os
        
        # Create the directory using SSH command
        directory = os.path.dirname(filepath)
        if directory:
            result = self.execute_command(join_command(("mkdir", "-p", directory)))
            if result['code'] != 0:
                raise IOError(f"Failed to create directory {directory}: {result.get('message', 'Unknown error')}")
        
        # Write the file using SSH and heredoc (avoiding SFTP completely)
        # This is more reliable than SFTP for script files
        delimiter = _heredoc_delimiter(content)
        command = (
            f"cat > {quote(filepath)} << '{delimiter}'\n"
            f"{content}\n{delimiter}"
        )
        
        result = self.execute_command(command)
        
        if result['code'] != 0:
            raise IOError(f"Failed to create file {filepath}: {result.get('message', 'Unknown error')}")

    def get_ssh_connection(self):
        """
        returns a new ssh connection with the remote machine

        :return: ssh connection
        """

        ssh = SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        # Esperar a que el puerto esté abierto (usa self.port en lugar de 22 hardcodeado)
        while not is_port_open(self.host, self.port):
            continue
        if self.keypath is None:
            ssh.connect(self.host, port=self.port, username=self.username)
        else:
            ssh.connect(self.host, port=self.port, username=self.username, key_filename=self.keypath)
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

        message = stderr if stderr else (stdout if code else "")
        return {"code": code, "message": message, "output": stdout, "error": stderr}
