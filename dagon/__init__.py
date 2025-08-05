import logging
import logging.config
import os
import json
from logging.config import fileConfig
import threading
import collections
from collections import abc

collections.MutableMapping = abc.MutableMapping
from backports.configparser import NoSectionError
from enum import Enum
from requests.exceptions import ConnectionError

from time import time
from datetime import datetime

from dagon.config import read_config
from dagon.api import API

from dagon.stager.base import DataMover
from dagon.stager.base import StagerMover


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

    def __init__(self, name, config=None, config_file='dagon.ini', max_threads=10, jsonload=None, checkpoint_file=None):
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
        print(max_threads)
        self.sem = threading.Semaphore(max_threads)
        # supress some logs
        logging.getLogger("paramiko").setLevel(logging.WARNING)
        logging.getLogger("globus_sdk").setLevel(logging.WARNING)

        self._scratch_dir = None
        self.checkpoint_file = checkpoint_file
        self.logger = logging.getLogger()
        self.dag_tps = None
        self.dry = False
        self.tasks = []
        self.checkpoints = {}
        self.workflow_id = 0
        self.is_api_available = False
        if jsonload is not None:  # load from json file
            self.load_json(jsonload)
        self.name = name

        # ftp attributes
        self.ftpAtt = dict()
        try:
            self.ftpAtt['host'] = self.cfg['ftp_pub']['ip']
            self.ftpAtt['user'] = "guess"
            self.ftpAtt['password'] = "guess"
            self.local_path = self.cfg['batch']['scratch_dir_base']
        except KeyError:
            self.logger.error("No ftp ip in config file")

        # to regist in the dagon service
        if self.cfg['dagon_service']['use'] == "True":
            try:
                #self.logger.debug("verifing dagon service")
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

        self.data_mover = DataMover.COPY
        self.stager_mover = StagerMover.NORMAL

    def get_dry(self):
        return self.dry

    def set_dry(self, dry):
        self.dry = dry

    def get_data_mover(self):
        return self.data_mover

    def set_data_mover(self, data_mover):
        self.data_mover = data_mover

    def set_stager_mover(self, stager_mover):
        self.stager_mover = stager_mover

    def get_scratch_dir_base(self):
        """
        Returns the path to the base scratch directory

        :return: Absolute path to the scratch directory
        :rtype: str with absolute path to the base scratch directory
        """
        if self._scratch_dir is None:
            base_dir = self.cfg['batch']['scratch_dir_base']
            run_base = self.cfg['batch'].get('run_base', '')

            if run_base:
                millis = int(round(time() * 1000))
                run_base = run_base.replace("__MILLIS__", str(millis))

                subdir_name = datetime.now().strftime(run_base)
                self._scratch_dir = os.path.join(base_dir, subdir_name)
            else:
                self._scratch_dir = base_dir
    
        return self._scratch_dir

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
        if task.data_mover is None:
            task.set_data_mover(self.data_mover)
        if task.stager_mover is None:
            task.set_stager_mover(self.stager_mover)

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
        self.Validate_WF()

    # Return a json representation of the workflow
    def as_json(self):
        """
        Return a json representation of the workflow

        :return: JSON representation
        :rtype: dict(str, object) with data class
        """

        jsonWorkflow = {"tasks": {}, "name": self.name, "id": self.workflow_id, "host": self.ftpAtt["host"]}
        for task in self.tasks:
            jsonWorkflow['tasks'][task.name] = task.as_json()
        return jsonWorkflow

    def run(self, resume_checkpoint_file = None):

        if resume_checkpoint_file is not None and os.path.isfile(resume_checkpoint_file) and os.stat(resume_checkpoint_file).st_size > 0:
            fp = open(resume_checkpoint_file, "r")
            self.checkpoints = json.loads(fp.read())
            fp.close()

            self.logger.debug("Resuming workflow: %s", self.name)

            self._scratch_dir = self.checkpoints.get('_scratch_dir', None)
        else:
            self.logger.debug("Running workflow: %s", self.name)

        start_time = time()
        for task in self.tasks:
            try:
                task.start()
            except:
                pass

        for task in self.tasks:
            try:
                task.join()
            except:
                pass
        
        completed_in = (time() - start_time)
        self.logger.info("Workflow '" + self.name + "' completed in %s seconds ---" % completed_in)

        if self.checkpoint_file is not None:
            self.checkpoints['_scratch_dir'] = self.get_scratch_dir_base()
            fp = open(self.checkpoint_file, 'w')
            fp.write(json.dumps(self.checkpoints, sort_keys=True, indent=4))
            fp.close()

    def load_json(self, Json_data):
        from dagon.task import DagonTask, TaskType
        self.name = Json_data['name']
        self.workflow_id = Json_data['id']
        for task in Json_data['tasks']:
            temp = Json_data['tasks'][task]
            tk = DagonTask(TaskType[temp['type'].upper()], temp['name'], temp['command'])
            self.add_task(tk)
        # self.make_dependencies()

    def Validate_WF(self):
        """
        Validate the workflow to avoid any kind of cycle in the graph.

        Raise an Exception if a cycle is found.
        """
        def visit(task, visited, stack):
            if task in stack:  # If the task is already in the exploration stack, we've found a cycle
                raise Exception(f"A cycle has been found involving task {task.name}")
            
            if task in visited:
                return  # Task already visited, no cycle detected
            
            # Mark the task as visited and explore the successors
            visited.add(task)
            stack.append(task)  # Add the task to the exploration stack

            for next_task in task.nexts:  # Explore the next tasks
                visit(next_task, visited, stack)
            
            stack.pop()  # Remove the task from the stack after exploration

        visited = set()  # Set of already visited tasks
        stack = []   # Stack for detecting cycles

        for task in self.tasks:
            if task not in visited:
                visit(task, visited, stack)

    def get_task_times(self):
        """
        Get the execution times of each task in the workflow

        :return: Dictionary with task names as keys and their execution times as values
        :rtype: dict(str, float)
        """
        task_times = {}
        for task in self.tasks:
            task_times[task.name] = task.completetion_time
        return task_times