from dagon.task import Task
from dagon.remote import  RemoteTask
from subprocess import Popen, PIPE, STDOUT
import shutil
import json

class Checkpoint(Task):
    """
    **Set an explicit Checkpoint saving the workflow status and enabling the resume**
    """

    def __init__(self, name, command, ip=None, ssh_username=None, keypath=None, working_dir=None, 
                 globusendpoint=None, transversal_workflow=None):
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str
        
        :param ip: hostname or ip of the machine where the task will be executed
        :type ip: str
        
        :param ssh_username: username in remote machine
        :type ssh_username: str
        
        :param keypath: path to the private keypath
        :type keypath: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str
        """

        command = "__WORKDIR__/.dagon/checkpoint.sh " + command

        Task.__init__(self, name, command, working_dir, transversal_workflow=transversal_workflow,
                      globusendpoint=globusendpoint)

    def __new__(cls, *args, **kwargs):
        """Create a local checkpoint task

           Keyword arguments:
           name -- task name


           command -- command to be executed
           working_dir -- directory where the outputs will be placed
           ip -- hostname or ip of the machine where the task will be executed
           ssh_username -- username in remote machine
           keypath -- path to the private keypath
        """
        
        if "ip" in kwargs:
            return super().__new__(RemoteCheckpoint)
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

        # Implement here the code for the checkpoint saving
        # ...

        p = Popen(command.split(" "), stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True, bufsize=-1,
                  universal_newlines=True)
        
        out, err = p.communicate()

        code, message = 0, ""
        if len(err):
            code, message = 1, err
        return {"code": code, "message": message, "output": out}

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

        script = script + r"""

# Create the checkpoint.sh script        
cat > checkpoint.sh << EOF
#! /bin/bash

for var in "\$@"
do
  if ! [ -f "\$var" ]; then
    exit -1
  fi
done

# Move the files in the root of the scratch directory
mv """ + self.working_dir + """/.dagon/inputs/* """ + self.working_dir + r"""/
EOF

# Set the execution bit for the checkpoit script
chmod +x checkpoint.sh

"""
        script = script.replace("__WORKDIR__", self.working_dir)

        # Update the checkpoint
        #self.workflow.checkpoints[self.workflow.name + "." + self.getName()]["code"] = 0
        #self.workflow.checkpoints[self.workflow.name + "." + self.getName()]["working_dir"] = self.working_dir + "-checkpoint"




        # Invoke the base method
        super(Checkpoint, self).on_execute(script, script_name)
        return Checkpoint.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)

    # returns public key
    def get_public_key(self):
        """
        Return the temporal public key to this machine

        :return: public key
        :rtype: str with the public key
        """
        command = "cat " + self.working_dir + "/.dagon/ssh_key.pub"
        result = Checkpoint.execute_command(command)
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
        result = Checkpoint.execute_command(command)
        return result

    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """

        # Perform some logging
        self.workflow.logger.debug("Renaming %s", self.working_dir)

        shutil.move(self.working_dir, self.working_dir + "-checkpoint")

        # Update the working directory
        self.working_dir = self.working_dir + "-checkpoint"

        # Update the checkpoint
        self.workflow.checkpoints[self.workflow.name + "." + self.getName()]["working_dir"] = self.working_dir

        fp = open(self.name+".json", 'w')
        fp.write(json.dumps(self.workflow.checkpoints, sort_keys=True, indent=4))
        fp.close()
        

class RemoteCheckpoint(RemoteTask, Checkpoint):
    """
    **Set an explicit Checkpoint saving the workflow status and enabling the resume on remote resources**
    """

    def __init__(self, name, command, ssh_username=None, keypath=None, ip=None, working_dir=None, globusendpoint=None):
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

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str
        """
        
        command = "__WORKDIR__/.dagon/checkpoint.sh " + command
        
        RemoteTask.__init__(self, name, command, ssh_username=ssh_username, keypath=keypath, ip=ip, working_dir=working_dir,
                            globusendpoint=globusendpoint)
    
    def on_garbage(self):
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """

        # Perform some logging
        self.workflow.logger.debug("Renaming %s", self.working_dir)

        self.ssh_connection.execute_command('mv {0} {1}'.format(self.working_dir,
                                            self.working_dir + "-checkpoint"))

        # Update the working directory
        self.working_dir = self.working_dir + "-checkpoint"

        # Update the checkpoint
        self.workflow.checkpoints[self.workflow.name + "." + self.getName()]["working_dir"] = self.working_dir

        fp = open(self.name+".json", 'w')
        fp.write(json.dumps(self.workflow.checkpoints, sort_keys=True, indent=4))
        fp.close()
        
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
        
        launcher_script = launcher_script + r"""

# Create the checkpoint.sh script        
cat > checkpoint.sh << EOF
#! /bin/bash

for var in "\$@"
do
  if ! [ -f "\$var" ]; then
    exit -1
  fi
done

# Move the files in the root of the scratch directory
mv """ + self.working_dir + r"""/.dagon/inputs/* """ + self.working_dir + r"""/
EOF

# Set the execution bit for the checkpoint script
chmod +x checkpoint.sh

"""
        launcher_script = launcher_script.replace("__WORKDIR__", self.working_dir)
        
        # Invoke the base method
        RemoteTask.on_execute(self, launcher_script, script_name)
        result = self.ssh_connection.execute_command("bash " + self.working_dir + "/.dagon/" + script_name)
        return result