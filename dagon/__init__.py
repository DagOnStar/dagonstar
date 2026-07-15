import logging
import logging.config
import os
import json
import re
from logging.config import fileConfig
import threading
from configparser import NoSectionError
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from requests.exceptions import ConnectionError

from time import time
from datetime import datetime

from dagon.config import read_config
from dagon.api import API

from dagon.stager.base import DataMover
from dagon.stager.base import StagerMover

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
                "on_dependencies_made",
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
            base_dir = os.path.abspath(base_dir)
            run_base = self.cfg['batch'].get('run_base', '')

            if run_base:
                millis = int(round(time() * 1000))
                run_base = run_base.replace("__MILLIS__", str(millis))

                subdir_name = datetime.now().strftime(run_base)
                self._scratch_dir = os.path.join(base_dir, subdir_name)
            else:
                self._scratch_dir = base_dir
    
        return self._scratch_dir
    
    def get_remove_dir_op(self) -> bool:
        """
        Returns whether the scratch directory should be removed.
        Expects True, False, 'True', 'False', 'true', or 'false'.
        Defaults to False if the key is missing or invalid.
        """
        val = self.cfg['batch'].get('remove_dir', False)

        if isinstance(val, bool):
            return val

        if val in ("True", "true"):
            return True
        elif val in ("False", "false"):
            return False
        else:
            self.logger.warning("Invalid value for 'remove_dir': '%s'. " \
            "Expected values: True, False, 'true' or 'false'", val)
            self.logger.warning("Using remove_dir=False")
            return False

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
        self._fire_event("on_dependencies_made", self)

    def enable_fair(self, profile: Any) -> Any:
        """Enable optional FAIR-by-design recording for this workflow.

        Importing the recorder here keeps the base :mod:`dagon` import free of
        FAIR implementation work until a workflow explicitly opts in.
        """
        from dagon.fair import FairRecorder, validate_profile
        validate_profile(profile, strict=profile.strict)
        recorder = FairRecorder(self, profile)
        self.fair_profile = profile
        self.fair_recorder = recorder
        return recorder

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

    def saveAsCWL(self, filename: str) -> None:
        """Save this workflow as a self-contained CWL v1.2 document.

        Each DAGonStar task is represented by an embedded ``CommandLineTool``
        which invokes its command through ``/bin/sh -c``.  Boolean completion
        outputs connect dependent steps, preserving both explicit and
        ``workflow://``-discovered ordering without inventing file outputs.

        :param filename: destination path for the JSON-form CWL document
        :raises ValueError: if a task has no command that CWL can execute
        """
        # Dependency discovery normally happens immediately before a run.  Do
        # it here as well, while retaining any explicit edges already attached
        # by callers (make_dependencies rebuilds the discovered graph).
        if not self._dependencies_made:
            explicit_edges = [
                (previous, task)
                for task in self.tasks
                for previous in task.prevs
                if previous in self.tasks
            ]
            self.make_dependencies()
            for previous, task in explicit_edges:
                if previous not in task.prevs:
                    previous.nexts.append(task)
                    task.prevs.append(previous)
            self.Validate_WF()

        def cwl_identifier(value: str, used: set) -> str:
            identifier = re.sub(r"[^A-Za-z0-9_]", "_", value)
            if not identifier or not identifier[0].isalpha():
                identifier = "task_" + identifier
            candidate = identifier
            suffix = 2
            while candidate in used:
                candidate = "%s_%d" % (identifier, suffix)
                suffix += 1
            used.add(candidate)
            return candidate

        used_ids = set()
        task_ids = {
            task: cwl_identifier(str(task.name), used_ids)
            for task in self.tasks
        }
        steps = {}
        for task in self.tasks:
            command = getattr(task, "command", None)
            if not isinstance(command, str) or not command:
                raise ValueError(
                    "Task %s has no shell command that can be exported to CWL"
                    % task.name
                )

            step_inputs = {}
            tool_inputs = {}
            for previous in task.prevs:
                if previous not in task_ids:
                    raise ValueError(
                        "Task %s depends on a task outside workflow %s"
                        % (task.name, self.name)
                    )
                input_id = "after_" + task_ids[previous]
                tool_inputs[input_id] = "boolean"
                step_inputs[input_id] = task_ids[previous] + "/completed"

            tool = {
                "class": "CommandLineTool",
                "label": str(task.name),
                "requirements": {"InlineJavascriptRequirement": {}},
                "baseCommand": ["/bin/sh", "-c", command],
                "inputs": tool_inputs,
                "outputs": {
                    "completed": {
                        "type": "boolean",
                        "outputBinding": {
                            "outputEval": "$(runtime.exitCode === 0)"
                        },
                    }
                },
            }
            image = getattr(task, "image", None)
            if image:
                tool["hints"] = {"DockerRequirement": {"dockerPull": image}}

            steps[task_ids[task]] = {
                "label": str(task.name),
                "in": step_inputs,
                "out": ["completed"],
                "run": tool,
            }

        terminal_tasks = [task for task in self.tasks if not task.nexts]
        outputs = {
            task_ids[task] + "_completed": {
                "type": "boolean",
                "outputSource": task_ids[task] + "/completed",
            }
            for task in terminal_tasks
        }
        document = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "label": self.name,
            "inputs": {},
            "outputs": outputs,
            "steps": steps,
        }
        with open(os.fspath(filename), "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=False)
            stream.write("\n")

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
            if temp['type'].upper() == 'NATIVE':
                tk = DagonTask(TaskType.NATIVE, temp['name'], temp['function'],
                               inputs=temp.get('inputs'), outputs=temp.get('outputs'),
                               executor=temp.get('executor', 'local'), resources=temp.get('resources'),
                               python=temp.get('python', 'python'), environment=temp.get('environment'),
                               working_dir=temp.get('working_dir'))
            elif temp['type'].upper() == 'WEB':
                tk = DagonTask(TaskType.WEB, temp['name'], temp['specification'],
                               executor=temp.get('executor', 'local'), resources=temp.get('resources'),
                               python=temp.get('python', 'python'), environment=temp.get('environment'),
                               working_dir=temp.get('working_dir'))
            else:
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
