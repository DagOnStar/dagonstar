
import paramiko
from fabric.api import local
from paramiko import SSHClient

from connection import Connection

#To manage SSH connections
class SSHManager:

    def __init__(self, username, host, keypath):
        self.username = username 
        self.host = host
        self.keypath = keypath
        self.connection = self.getSSHConnection()

    def getConnection(self):
        return self.connection

    #add host to know hosts
    @staticmethod
    def addToKnowHosts(node):
        command = "ssh-keyscan -H %s >> ~/.ssh/known_hosts" % (node)
        result = local(command, capture=False, shell="/bin/bash")
        # Check if the execution failed    
        if result.failed:
            raise Exception('Failed to add to know hosts')

    #Return a SSH connection
    def getSSHConnection(self):
        #SSHManager.addToKnowHosts(self.host) #add to know hosts
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while not Connection.isPortOpen(self.host, 22):
            continue
        if self.keypath is None:
            ssh.connect(self.host, username=self.username)
        else:
            ssh.connect(self.host, username=self.username, key_filename=self.keypath)
        return ssh

    #execute command in remothe machine over SSH
    def executeCommand(self, command):
        _, stdout, stderr = self.connection.exec_command(command)
        stdout = stdout.readlines()
        stderr = stderr.readlines()
        code = 0 if len(stderr) == 0 else 1
        return {"code":code,"output":'\n'.join(stdout),"error":'\n'.join(stderr)}