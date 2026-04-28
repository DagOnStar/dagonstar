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
        import shlex
        
        # Create the directory using SSH command
        directory = os.path.dirname(filepath)
        if directory:
            self.execute_command(f"mkdir -p {directory}")
        
        # Write the file using SSH and heredoc (avoiding SFTP completely)
        # This is more reliable than SFTP for script files
        command = f"cat > {shlex.quote(filepath)} << 'DAGON_EOF'\n{content}\nDAGON_EOF"
        
        result = self.execute_command(command)
        
        if result['code'] != 0:
            raise IOError(f"Failed to create file {filepath}: {result.get('message', 'Unknown error')}")

    def get_ssh_connection(self):
        """
        returns a new ssh connection with the remote machine

        :return: ssh connection
        """

        ssh = SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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
        if len(stderr):
            return {"code": 1, "message": stderr}
        elif code > 0:
            return {"code": 1, "message": stdout}
        else:
            return {"code": 0, "output": stdout}