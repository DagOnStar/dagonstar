import logging
import logging.config
import os
import json
from logging.config import fileConfig
import threading
from configparser import NoSectionError
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from requests.exceptions import ConnectionError

from time import time, sleep
from datetime import datetime

from dagon.config import read_config
from dagon.api import API
from dagon.batch import Batch
from dagon.batch import Slurm
from dagon.remote import RemoteTask
from dagon.shell import quote, remote_target


def __getattr__(name):
    if name == "WorkflowServer":
        try:
            from dagon.api.server import WorkflowServer
        except ImportError as exc:
            if exc.name in {"flask", "flask_api", "werkzeug"}:
                raise ImportError(
                    "API server support requires the 'api' extra: "
                    "python -m pip install 'dagonstar[api]'"
                ) from exc
            raise
        return WorkflowServer
    raise AttributeError(f"module 'dagon' has no attribute {name!r}")


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


class EventHook:
    """A thread-safe collection of callbacks for a workflow lifecycle event.

    Callbacks receive the workflow for workflow events and the task for task
    events.  Use ``hook += callback`` (or :meth:`Workflow.add_listener`) to
    register a callback.
    """

    def __init__(self, workflow: "Workflow", name: str) -> None:
        self._workflow = workflow
        self.name = name
        self._listeners: List[Callable[[Any], None]] = []
        self._lock = threading.RLock()

    def __iadd__(self, listener: Callable[[Any], None]) -> "EventHook":
        self.add(listener)
        return self

    def __isub__(self, listener: Callable[[Any], None]) -> "EventHook":
        self.remove(listener)
        return self

    def add(self, listener: Callable[[Any], None]) -> None:
        if not callable(listener):
            raise TypeError("Workflow event listeners must be callable")
        with self._lock:
            self._listeners.append(listener)

    def remove(self, listener: Callable[[Any], None]) -> None:
        with self._lock:
            self._listeners.remove(listener)

    def fire(self, subject: Any) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(subject)
            except Exception:
                # Observers must not be able to terminate workflow execution.
                self._workflow.logger.exception(
                    "Listener for workflow event %s failed", self.name)


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

    def __init__(
            self,
            name: str,
            config: Optional[Dict[str, Dict[str, str]]] = None,
            config_file: str = 'dagon.ini',
            max_threads: int = 10,
            jsonload: Optional[Dict[str, Any]] = None,
            checkpoint_file: Optional[str] = None):
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

        self._scratch_dir = None
        self.checkpoint_file = checkpoint_file
        self.logger = logging.getLogger()
        self.dag_tps = None
        self.dry = False
        self.tasks: List[Any] = []
        self.checkpoints: Dict[str, Any] = {}
        self.workflow_id = 0
        self.is_api_available = False
        self.data_mover = DataMover.COPY
        self.stager_mover = StagerMover.NORMAL
        self.name = name
        self._dependencies_made = False
        self._execution_thread: Optional[threading.Thread] = None
        self._execution_lock = threading.RLock()
        self._event_hooks = {
            name: EventHook(self, name) for name in (
                "on_workflow_start", "on_workflow_end", "on_task_start",
                "on_task_end", "on_task_wait", "on_task_staging_in_start",
                "on_task_staging_in_end", "on_task_execute_start",
                "on_task_staging_out_start", "on_task_staging_out_end",
            )
        }
        for event_name, hook in self._event_hooks.items():
            setattr(self, event_name, hook)
        if jsonload is not None:  # load from json file
            self.load_json(jsonload)

        # ftp attributes
        self.ftpAtt = dict()
        self.ftpAtt['host'] = self.cfg.get('ftp_pub', {}).get('ip', 'localhost')
        self.ftpAtt['user'] = self.cfg.get('ftp_pub', {}).get('user', 'anonymous')
        self.ftpAtt['password'] = self.cfg.get('ftp_pub', {}).get('password', '')
        self.local_path = self.cfg.get('batch', {}).get('scratch_dir_base', '/tmp/')

        # to regist in the dagon service
        if self.cfg.get('dagon_service', {}).get('use', "False") == "True":
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

    def get_scratch_dir_base(self) -> str:
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

    def find_task_by_name(self, workflow_name: str, task_name: str) -> Optional[Any]:
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

    def add_task(self, task: Any) -> None:
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
        self._dependencies_made = False
        if self.is_api_available:
            self.api.add_task(self.workflow_id, task)

    def set_dag_tps(self, DAG_tps):
        """
        Set the DAG_tps workflow which execute this workflow

        :param  DAG_tps: :class:`dagon.dag_tps` instance
        :type  DAG_tps: :class:`dagon.dag_tps`
        """
        self.dag_tps = DAG_tps

    def make_dependencies(self) -> None:
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
        self._dependencies_made = True

    def add_listener(self, event_name: str, listener: Callable[[Any], None]) -> None:
        """Register *listener* for a named workflow event."""
        self._get_event_hook(event_name).add(listener)

    def remove_listener(self, event_name: str, listener: Callable[[Any], None]) -> None:
        """Remove a previously registered workflow event listener."""
        self._get_event_hook(event_name).remove(listener)

    def _get_event_hook(self, event_name: str) -> EventHook:
        try:
            return self._event_hooks[event_name]
        except KeyError as exc:
            raise ValueError("Unknown workflow event: %s" % event_name) from exc

    def _fire_event(self, event_name: str, subject: Any) -> None:
        self._get_event_hook(event_name).fire(subject)

    def _prepare_run(self) -> None:
        if not self._dependencies_made:
            self.make_dependencies()

    # Return a json representation of the workflow
    def as_json(self) -> Dict[str, Any]:
        """
        Return a json representation of the workflow

        :return: JSON representation
        :rtype: dict(str, object) with data class
        """

        jsonWorkflow = {"tasks": {}, "name": self.name, "id": self.workflow_id, "host": self.ftpAtt.get("host", "localhost")}
        for task in self.tasks:
            jsonWorkflow['tasks'][task.name] = task.as_json()
        return jsonWorkflow

    def run(self, resume_checkpoint_file = None):
        """Run the workflow in the current thread."""
        with self._execution_lock:
            self._prepare_run()

        if resume_checkpoint_file is not None and os.path.isfile(resume_checkpoint_file) and os.stat(resume_checkpoint_file).st_size > 0:
            fp = open(resume_checkpoint_file, "r")
            self.checkpoints = json.loads(fp.read())
            fp.close()

            self.logger.debug("Resuming workflow: %s", self.name)

            self._scratch_dir = self.checkpoints.get('_scratch_dir', None)
        else:
            self.logger.debug("Running workflow: %s", self.name)

        start_time = time()
        self._fire_event("on_workflow_start", self)
        try:
            for task in self.tasks:
                try:
                    task.start()
                except RuntimeError:
                    self.logger.debug("Task %s was already started", task.name)

            for task in self.tasks:
                try:
                    task.join()
                except RuntimeError:
                    self.logger.debug("Task %s could not be joined before start", task.name)

            completed_in = (time() - start_time)
            self.logger.info("Workflow '" + self.name + "' completed in %s seconds ---" % completed_in)

            if self.checkpoint_file is not None:
                self.checkpoints['_scratch_dir'] = self.get_scratch_dir_base()
                with open(self.checkpoint_file, 'w') as fp:
                    fp.write(json.dumps(self.checkpoints, sort_keys=True, indent=4))
        finally:
            self._fire_event("on_workflow_end", self)

    def launch(self, resume_checkpoint_file=None) -> threading.Thread:
        """Start the workflow in a background thread and return that thread."""
        with self._execution_lock:
            if self._execution_thread is not None and self._execution_thread.is_alive():
                raise RuntimeError("Workflow %s is already running" % self.name)
            self._prepare_run()
            self._execution_thread = threading.Thread(
                target=self.run,
                args=(resume_checkpoint_file,),
                name="DAGonStar-Workflow-%s" % self.name,
            )
            self._execution_thread.start()
            return self._execution_thread

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until a launched workflow ends; return ``True`` if it ended."""
        with self._execution_lock:
            execution_thread = self._execution_thread
        if execution_thread is None:
            return True
        execution_thread.join(timeout)
        return not execution_thread.is_alive()

    def load_json(self, Json_data):
        from dagon.task import DagonTask, TaskType
        self.name = Json_data['name']
        self.workflow_id = Json_data['id']
        for task in Json_data['tasks']:
            temp = Json_data['tasks'][task]
            options = {}
            if temp['type'].upper() == 'LLM':
                options['provider'] = temp.get('provider')
                options['params'] = temp.get('params')
                options['input_files'] = temp.get('input_files')
                options['output_file'] = temp.get('output_file', 'response.json')
            tk = DagonTask(TaskType[temp['type'].upper()], temp['name'], temp['command'], **options)
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


class StagerMover(Enum):
    """
    Possible mode

    :cvar NORMAL: sequential
    :cvar PARALLEL: using threads
    :cvar SLURM: using Slurm
    """
    NORMAL = 0
    PARALLEL = 1
    SLURM = 2


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

    def __init__(self, data_mover: DataMover, stager_mover: StagerMover, cfg: Dict[str, Dict[str, str]]):
        self.data_mover = data_mover
        self.stager_mover = stager_mover
        self.cfg = cfg

    def stage_in(self, dst_task: Any, src_task: Any, dst_path: str, local_path: str) -> str:
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
                data_mover = self.data_mover
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
            data_mover = self.data_mover

        src = src_task.get_scratch_dir() + "/" + local_path

        dst = dst_path + "/" + os.path.dirname(os.path.abspath(local_path))

        # Check if the symbolic link have to be used...
        if data_mover == DataMover.GRIDFTP:
            from dagon.communication.data_transfer import GlobusManager

            # data could be copy using globus sdk
            ep1 = src_task.get_endpoint()
            ep2 = dst_task.get_endpoint()
            gm = GlobusManager(ep1, ep2, self.cfg["globus"]["clientid"], self.cfg["globus"]["intermadiate_endpoint"])

            # generate tar with data
            #tar_path = src + "/data.tar"
            #command_tar = "tar -czvf %s %s --exclude=*.tar" % (tar_path, src_task.get_scratch_dir())
            #result = src_task.execute_command(command_tar)

            #get filename from path 
            intermediate_filename = os.path.basename(local_path)
            dst = dst_path + "/" + os.path.dirname(os.path.abspath(local_path)) + "/" + intermediate_filename

            gm.copy_data(src, dst, intermediate_filename)# + "/" + "data.tar.gz")

        elif data_mover == DataMover.SKYCDS:
            from dagon.communication.data_transfer import SKYCDS

            skycds = SKYCDS()
            upload_result = skycds.upload_data(src_task, src_task.get_scratch_dir(), encryption=True)
            download_result = skycds.download_data(dst_task, dst_path)


        elif data_mover == DataMover.LINK:
            # Add the link command
            command = command + "# Add the link command\n"
            cmd = "ln -sf \"$file\" \"$dst\""
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "ln -sf {} \"$dst\""
            command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)
                      
        # Check if the copy have to be used...
        elif data_mover == DataMover.COPY:
            # Add the copy command
            command = command + "# Add the copy command\n"
            cmd = "cp -r \"$file\" \"$dst\""
            if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                cmd = "cp -r {} \"$dst\""
            command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)

        # Check if the secure copy have to be used...
        elif data_mover == DataMover.SCP:
            # Add the copy command
            command = command + "# Add the secure copy command\n"
            if isinstance(src_task, RemoteTask):  # if source is accessible from destiny machine
                # copy my public key
                key = dst_task.get_public_key()
                src_task.add_public_key(key)
                key_path = dst_task.working_dir + "/.dagon/ssh_key"
                source = remote_target(src_task.get_user(), src_task.get_ip(), '"$file"')
                cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                       "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                       " -r " + source + ' "$dst"\n\n')
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    source = remote_target(src_task.get_user(), src_task.get_ip(), "{}")
                    cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                           "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                           " -r " + source + ' "$dst"\n\n')
                command = command + self.generate_command(src, dst, cmd, self.stager_mover.value)
                command += "\nif [ $? -ne 0 ]; then code=1; fi"
                # command += "\n rm " + dst_task.working_dir + "/.dagon/ssh_key"
            else:  # if source is a local machine
                # copy my public key
                key = src_task.get_public_key()
                dst_task.add_public_key(key)

                command_mkdir = "mkdir -p " + quote(dst_path + "/" + os.path.dirname(local_path)) + "\n\n"
                res = dst_task.ssh_connection.execute_command(command_mkdir)

                if res['code']:
                    raise Exception("Couldn't create directory %s" % dst_path + "/" + os.path.dirname(local_path))

                key_path = src_task.working_dir + "/.dagon/ssh_key"
                destination = remote_target(dst_task.get_user(), dst_task.get_ip(), '"$dst"')
                cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                       "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                       ' -r "$file" ' + destination + "\n\n")
                if StagerMover(self.stager_mover) == StagerMover.PARALLEL:
                    destination = remote_target(dst_task.get_user(), dst_task.get_ip(), '"$dst"')
                    cmd = ("scp -r -o LogLevel=ERROR -o StrictHostKeyChecking=no "
                           "-o UserKnownHostsFile=/dev/null -i " + quote(key_path) +
                           " -r {} " + destination + "\n\n")
                command_local = self.generate_command(src, dst, cmd, self.stager_mover.value)
                res = Batch.execute_command(command_local)

                if res['code']:
                    raise Exception("Couldn't copy data from %s to %s" % (src_task.get_ip(), dst_task.get_ip()))

        command += "\nif [ $? -ne 0 ]; then code=1; fi"

        return command

    def generate_command(self, src: str, dst: str, cmd: str, mode: int) -> str:
        batch_cfg = self.cfg.get("batch", {})
        slurm_cfg = self.cfg.get("slurm", {})
        jobs = batch_cfg.get("threads", "1")
        partition = slurm_cfg.get("partition", "")
        return """
#! /bin/bash

src={}
dst={}
mode={}
jobs={}
partition={}

job_ids=()

for file in $src
do
cmd="{}"
case $mode in
    1)
    # Run in parallel using local queue
    find $src -type f,l | parallel -j$jobs "$cmd"
    break
    ;;
    2)
    # Run in parallel using slurm
    job_id=$(sbatch --job-name=stagein --partition=$partition --ntasks=1 --cpus-per-task=1 --mem=1024 --wrap="$cmd" | awk '{{print $4}}')
    job_ids+=($job_id)
    ;;
    *)
    # Run requentially
    eval "$cmd"
    ;;
esac
done

# Wait for all sbatch jobs to complete
if [ "${{#job_ids[@]}}" -gt 0 ]; then
    echo "Waiting for all copies to complete..."
    while true; do
        # Check if any jobs are still in the queue
        pending_jobs=$(squeue -j "${{job_ids[*]}}" -h -o '%A')
        if [ -z "$pending_jobs" ]; then
            break
        fi
        # Wait a few seconds before checking again
        sleep 5
    done
fi
        """.format(
            quote(src),
            quote(dst),
            int(mode),
            quote(jobs),
            quote(partition),
            cmd.replace('"', '\\"'),
        )
