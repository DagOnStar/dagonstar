import logging
import logging.config
import os
from logging.config import fileConfig
import threading
from backports.configparser import NoSectionError
from enum import Enum
from requests.exceptions import ConnectionError

from time import time, sleep

from dagon.config import read_config
from dagon.api import API
from dagon.api.server import WorkflowServer
from dagon.batch import Batch
from dagon.batch import Slurm
from dagon.communication.data_transfer import GlobusManager
from dagon.communication.data_transfer import SKYCDS
from dagon.docker_task import DockerRemoteTask
from dagon.remote import RemoteTask


class Status(Enum):
    """
    Possible states that a :class:`dagon.Task` could be in

    :cvar READY: Ready to execute
    :cvar WAITING: Waiting for some tasks to end them execution
    :cvar RUNNING: On execution
    :cvar FINISHED: Executed with success
    :cvar FAILED: Executed with error
    """

    READY = "READY"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class Workflow(object):
    """
    **Represents a workflow executed by DagOn**

    :ivar name: unique name of the workflow
    :vartype name: str

    :ivar cfg: workflow configuration
    :vartype cfg: str

    :ivar tasks: Task to be executed by the workflow
    :vartype tasks: str

    :ivar workflow_id: workflow ID
    :vartype workflow_id: str

    :ivar is_api_available: True if the API is available
    :vartype is_api_available: str
    """

    SCHEMA = "workflow://"

    def __init__(self, name, config=None, config_file='dagon.ini', max_threads=10, jsonload=None):
        """
        Create a workflow

        :param name: Workflow name
        :type name: str

        :param config: configuration dictionary of the workflow
        :type config: dict(str, str)

        :param config_file: Path to the configuration file of the workflow. By default, try to loads 'dagon.ini'
        :type config_file: str
        """

        if config is not None:
            self.cfg = config
        else:
            self.cfg = read_config(config_file)
            fileConfig(config_file)
        self.sem = threading.Semaphore(max_threads)
        # supress some logs
        logging.getLogger("paramiko").setLevel(logging.WARNING)
        logging.getLogger("globus_sdk").setLevel(logging.WARNING)

        self.logger = logging.getLogger()
        self.dag_tps=None
        self.dry = False
        self.tasks = []
        self.workflow_id = 0
        self.is_api_available = False
        if jsonload is not None: #load from json file
            self.load_json(jsonload)
        self.name = name

        #ftp attributes
        self.ftpAtt = dict()
        try:
            self.ftpAtt['host'] = self.cfg['ftp_pub']['ip']
            self.ftpAtt['user'] = "guess"
            self.ftpAtt['password'] = "guess"
            self.local_path = self.cfg['batch']['scratch_dir_base']
        except KeyError:
            self.logger.error("No ftp ip in config file")

        # to regist in the dagon service
        try:
            self.api = API(self.cfg['dagon_service']['route'])
            self.is_api_available = True
        except KeyError:
            self.logger.error("No dagon URL in config file")
        except NoSectionError:
            self.logger.error("No dagon URL in config file")
        except ConnectionError as e:
            self.logger.error(e)

        if self.is_api_available:
            try:
                self.workflow_id = self.api.create_workflow(self)
                self.logger.debug("Workflow registration success id = %s" % self.workflow_id)
            except Exception as e:
                raise Exception(e)


    def get_dry(self):
        return self.dry

    def set_dry(self, dry):
        self.dry = dry

    def get_scratch_dir_base(self):
        """
        Returns the path to the base scratch directory

        :return: Absolute path to the scratch directory
        :rtype: str with absolute path to the base scratch directory
        """
        return self.cfg['batch']['scratch_dir_base']

    def find_task_by_name(self, workflow_name, task_name):
        """
        Search for a task of an specific workflow

        :param workflow_name: Name of the workflow
        :type workflow_name: str

        :param task_name: Name of the task
        :type task_name: str

        :return: task instance
        :rtype: :class:`dagon.task.Task` instance if it is found, None in other case
        """

        # Check if the workflow is the current one
        if workflow_name == self.name:

            # For each task in the tasks collection
            for task in self.tasks:

                # Check the task name
                if task_name == task.name:
                    # Return the result
                    return task

        return None

    def add_task(self, task):
        """
        Add a task to this workflow

        :param task: :class:`dagon.task.Task` instance
        :type task: :class:`dagon.task.Task`
        """
        self.tasks.append(task)
        task.set_workflow(self)
        if self.is_api_available:
            self.api.add_task(self.workflow_id, task)
    
    def set_dag_tps(self, DAG_tps):
        """
        Set the DAG_tps workflow which execute this workflow

        :param  DAG_tps: :class:`dagon.dag_tps` instance
        :type  DAG_tps: :class:`dagon.dag_tps`
        """
        self.dag_tps = DAG_tps

    def make_dependencies(self):
        """
        Looks for all the dependencies between tasks
        """

        # Clean all dependencies
        for task in self.tasks:
            task.nexts = []
            task.prevs = []
            task.reference_count = 0

        # Automatically detect dependencies
        for task in self.tasks:
            # Invoke pre run
            task.set_semaphore(self.sem)
            task.set_dag_tps(self.dag_tps)
            task.pre_run()
        #self.Validate_WF()

    # Return a json representation of the workflow
    def as_json(self):
        """
        Return a json representation of the workflow

        :return: JSON representation
        :rtype: dict(str, object) with data class
        """

        jsonWorkflow = {"tasks": {}, "name": self.name, "id": self.workflow_id, "host":self.ftpAtt["host"]}
        for task in self.tasks:
            jsonWorkflow['tasks'][task.name] = task.as_json()
        return jsonWorkflow

    def run(self):
        self.logger.debug("Running workflow: %s", self.name)
        start_time = time()
        #print self.tasks
        for task in self.tasks:
            task.start()

        for task in self.tasks:
            task.join()
        completed_in = (time() - start_time)
        self.logger.info("Workflow '"+self.name+ "' completed in %s seconds ---" % completed_in)

    def load_json(self, Json_data):
        from dagon.task import DagonTask, TaskType
        self.name = Json_data['name']
        self.workflow_id =Json_data['id']
        for task in Json_data['tasks']:
            temp = Json_data['tasks'][task]
            tk = DagonTask(TaskType[temp['type'].upper()], temp['name'], temp['command'])
            self.add_task(tk)
        #self.make_dependencies()

    def Validate_WF(self):
        """
        Validate the workflow to avoid any kind of cycle on the grap

        Raise an Exception when a cylce is founded
        """
        needed = []; needy = []
        for task in self.tasks:
            for prev in task.prevs:
                bool_needed = False; bool_needy = False
                needed.append(prev) #dependency task is added
                if task in needed or task.nexts in needed: bool_needed=True #are you or your decendents needed?
                if prev in needy: bool_needy=True #that who you need is also needed?
                if bool_needy and bool_needed:
                    logging.warning('A cycle have been found')
                    raise Exception("A cycle have been found from %s to %s" % (prev.name, task.name))
                else:
                    needy.append(task) #add the task and decendets to the needys array
                    for t in task.nexts:
                        needy.append(t)

class DataMover(Enum):
    """
    Possible transfer protocols/apps

    :cvar DONTMOVE: Don't move nothing
    :cvar LINK: Using a symbolic link
    :cvar COPY: Copying the data
    :cvar SCP: Using secure copy
    :cvar HTTP: Using HTTP
    :cvar HTTPS: Using HTTPS
    :cvar FTP: Using FTP
    :cvar SFTP: Using secure FTP
    :cvar GRIDFTP: Using Globus GridFTP
    """

    DONTMOVE = 0
    LINK = 1
    COPY = 2
    SCP = 3
    HTTP = 4
    HTTPS = 5
    FTP = 6
    SFTP = 7
    GRIDFTP = 8
    SKYCDS = 9


class ProtocolStatus(Enum):
    """
    Status of the protocol on a machine

    :cvar ACTIVE: Protocol running and active
    :cvar NONE: Protocol not installed
    :cvar INACTIVE: Protocol not running
    """

    ACTIVE = "active"
    NONE = "none"
    INACTIVE = "inactive"


class Stager(object):
    """
    Choose the transference protocol to move data between tasks
    """

    def __init__(self):
        pass

    def stage_in(self, dst_task, src_task, dst_path, local_path):
        """
        Evaluates the context of the machines and choose the transfer protocol

        :param dst_task: task where the data has to be put
        :type dst_task: :class:`dagon.task.Task`

        :param src_task: task from the data has to be taken
        :type src_task: :class:`dagon.task.Task`

        :param dst_path: path where the file is going to be save on the destiny directory
        :type dst_path: str

        :param local_path: path where is the file to be transferred on the source task
        :type local_path: str

        :return: comand to move the data
        :rtype: str with the command
        """

        data_mover = DataMover.DONTMOVE
        command = ""

        # ToDo: this have to be make automatic
        # get tasks info and select transference protocol
        dst_task_info = dst_task.get_info()
        src_task_info = src_task.get_info()

        # check transference protocols and remote machine info if is available
        if dst_task_info is not None and src_task_info is not None:
            if dst_task_info['ip'] == src_task_info['ip']:
                data_mover = DataMover.LINK
            else:
                protocols = ["GRIDFTP", "SCP", "FTP"]
                for p in protocols:
                    if ProtocolStatus(src_task_info[p]) is ProtocolStatus.ACTIVE:
                        data_mover = DataMover[p]

                        if data_mover == DataMover.GRIDFTP and \
                                not dst_task.get_endpoint() and \
                                not src_task.get_endpoint():
                            continue

                        break
        else:  # best effort (SCP)
            data_mover = DataMover.LINK

        # Check if the symbolic link have to be used...
        if data_mover == DataMover.GRIDFTP:
            # data could be copy using globus sdk
            ep1 = src_task.get_endpoint()
            ep2 = dst_task.get_endpoint()
            gm = GlobusManager(ep1, ep2)

            #generate tar with data
            tar_path = src_task.get_scratch_dir() + "/" + local_path + "/data.tar"
            command_tar = "tar -czvf %s %s --exclude=*.tar" % (tar_path, src_task.get_scratch_dir())
            result = src_task.execute_command(command_tar)

            gm.copy_data(tar_path, dst_path + "/" + local_path + "/" + "data.tar.gz")

        elif data_mover == DataMover.SKYCDS:
            skycds = SKYCDS()
            upload_result = skycds.upload_data(src_task, src_task.get_scratch_dir(), encryption=True)
            download_result = skycds.download_data(dst_task, dst_path)


        elif data_mover == DataMover.LINK:
            # Add the link command
            command = command + "# Add the link command\n"
            command = command + "ln -sf " + src_task.get_scratch_dir() + "/" + local_path + " " \
                      + dst_path + "/" + local_path + "\n\n"
        # Check if the copy have to be used...
        elif data_mover == DataMover.COPY:
            # Add the copy command
            command = command + "# Add the copy command\n"
            command = command + "cp -r " + src_task.get_scratch_dir() + "/" + local_path + " " + \
                      dst_path + "/" + local_path + "\n\n"

        # Check if the secure copy have to be used...
        elif data_mover == DataMover.SCP:
            # Add the copy command
            command = command + "# Add the secure copy command\n"
            if isinstance(src_task, RemoteTask):  # if source is accessible from destiny machine
                # copy my public key
                key = dst_task.get_public_key()
                src_task.add_public_key(key)

                command = command + "scp -o \"StrictHostKeyChecking no\" -i " + dst_task.working_dir + \
                          "/.dagon/ssh_key -r " + src_task.get_user() + "@" + src_task.get_ip() + ":" + \
                          src_task.get_scratch_dir() + "/" + local_path + " " + dst_path + "/" + local_path + "\n\n"
                command += "\nif [ $? -ne 0 ]; then code=1; fi"
                # command += "\n rm " + dst_task.working_dir + "/.dagon/ssh_key"
            else:  # if source is a local machine
                # copy my public key
                key = src_task.get_public_key()
                dst_task.add_public_key(key)

                command_mkdir = "mkdir -p " + dst_path + "/" + os.path.dirname(local_path) + "\n\n"
                res = dst_task.ssh_connection.execute_command(command_mkdir)

                if res['code']:
                    raise Exception("Couldn't create directory %s" % dst_path + "/" + os.path.dirname(local_path))

                command_local = "scp -o \"StrictHostKeyChecking no\" -i " + src_task.working_dir + \
                                "/.dagon/ssh_key -r " + src_task.get_scratch_dir() + "/" + local_path + " " + \
                                dst_task.get_user() + "@" + dst_task.get_ip() + ":" + dst_path + \
                                "/" + local_path + "\n\n"
                res = Batch.execute_command(command_local)

                if res['code']:
                    raise Exception("Couldn't copy data from %s to %s" % (src_task.get_ip(), dst_task.get_ip()))

        command += "\nif [ $? -ne 0 ]; then code=1; fi"

        return command
