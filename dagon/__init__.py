import logging
import logging.config
import os
import json
import re
from logging.config import fileConfig
import threading
from configparser import NoSectionError
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from requests.exceptions import ConnectionError

from time import time
from datetime import datetime

from dagon.config import read_config
from dagon.platform_support import shell_path
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
            checkpoint_file: Optional[str] = None,
            portable_emulation: bool = False,
            pre_stage: bool = False):
        """
        Create a workflow

        :param name: Workflow name
        :type name: str

        :param config: configuration dictionary of the workflow
        :type config: dict(str, str)

        :param config_file: Path to the configuration file of the workflow. By default, try to loads 'dagon.ini'
        :type config_file: str

        :param pre_stage: default scheduler-aware pre-staging policy of the
            workflow's tasks (``False`` by default).  When ``True``, eligible
            scheduler tasks (Slurm, RemoteSlurm) whose own ``pre_stage`` is
            ``None`` stage their ``workflow://`` inputs before requesting
            resources; every other task keeps its usual lifecycle.  See
            ``docs/scheduler_prestaging.md``.
        :type pre_stage: bool
        """
        from dagon.prestage import validate_pre_stage
        self.pre_stage = validate_pre_stage(pre_stage, allow_none=False)

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
        self.portable_emulation = bool(portable_emulation)
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
        # Workflow-scope BeeOND volumes, created on demand (see dagon.beeond).
        self.beeond_volumes: Dict[str, Any] = {}
        self._beeond_lock = threading.Lock()
        self.adhoc_filesystems: Dict[str, Any] = {}
        # Streams planned for the current run (dagon.streaming).
        self.streams: List[Any] = []
        self.run_id: Optional[str] = None
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

    def is_portable_emulation(self) -> bool:
        """Return whether external backends must use credential-free local execution."""
        return self.portable_emulation

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
            # Forward slashes on Windows so launcher scripts can use the path.
            self._scratch_dir = shell_path(self._scratch_dir)

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
        # Fail fast on an invalid or unsupported explicit pre_stage override;
        # the effective value is resolved again when the task executes.
        validate_pre_stage = getattr(task, "validate_pre_stage_declaration", None)
        if validate_pre_stage is not None:
            validate_pre_stage(self)

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
        """Rebuild the dependency graph.

        Edges are rediscovered from ``workflow://`` references; edges added
        with :meth:`dagon.task.Task.add_dependency_to` outside discovery are
        restored afterwards, so explicit edges survive whether they were added
        before or after this call (``run()`` calls it when it has not run yet).
        """
        explicit_edges = [(task, previous) for task in self.tasks
                          for previous in list(getattr(task, "explicit_prevs", []))]

        # Clean all dependencies
        for task in self.tasks:
            task.nexts = []
            task.prevs = []
            task.reference_count = 0

        # Automatically detect dependencies
        self._discovering_dependencies = True
        try:
            for task in self.tasks:
                # Invoke pre run
                task.set_semaphore(self.sem)
                task.set_dag_tps(self.dag_tps)
                task.pre_run()
        finally:
            self._discovering_dependencies = False
        for task, previous in explicit_edges:
            self._restore_explicit_edge(task, previous)
        if any(getattr(task, "is_volume_task", False) for task in self.tasks):
            # Volume tasks (dagon.volume): bind users, add volume edges, check readers.
            from dagon.volume import plan_volumes
            self._discovering_dependencies = True
            try:
                plan_volumes(self)
            finally:
                self._discovering_dependencies = False
        self.Validate_WF()
        self._dependencies_made = True
        self._fire_event("on_dependencies_made", self)

    @staticmethod
    def _restore_explicit_edge(task: Any, previous: Any) -> None:
        """Add the explicit edge previous -> task once, without service calls."""
        if previous not in task.prevs:
            task.prevs.append(previous)
        if task not in previous.nexts:
            previous.nexts.append(task)
        explicit = task.__dict__.setdefault("explicit_prevs", [])
        if previous not in explicit:
            explicit.append(previous)

    def _load_explicit_edges(self, tasks_data: Dict[str, Any]) -> None:
        """Restore serialized explicit edges after every task has been built.

        ``explicit_prevs`` names must be tasks of this workflow. JSON written
        before that field existed only has ``prevs``, which also lists edges
        discovered from ``workflow://`` references, including tasks of other
        workflows; its same-workflow names are restored as explicit edges and
        the others are left to discovery.
        """
        by_name = {task.name: task for task in self.tasks}
        for key, data in tasks_data.items():
            task = by_name[data.get('name', key)]
            if 'explicit_prevs' in data:
                names = data['explicit_prevs']
                unknown = [name for name in names if name not in by_name]
                if unknown:
                    raise ValueError("task %r has explicit dependencies on unknown tasks: %s"
                                     % (task.name, ", ".join(map(str, unknown))))
            else:
                names = [name for name in data.get('prevs', []) if name in by_name]
            for name in names:
                if by_name[name] is task:
                    raise ValueError("task %r cannot depend on itself" % task.name)
                self._restore_explicit_edge(task, by_name[name])
        self.Validate_WF()

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

    def create_beeond_volume(self, name: str = "default", **options: Any) -> Any:
        """Create a workflow-scope BeeOND volume shared by Slurm tasks.

        *options* override the ``[beeond]`` section of the configuration; see
        :class:`dagon.beeond.BeeONDConfig`.  The volume is started by the first
        task that uses it and persisted and released when :meth:`run` ends.
        """
        from dagon.beeond import BeeONDVolume, workflow_defaults
        options = dict(options, scope="workflow", volume=name)
        config = workflow_defaults(self).with_options(**options)
        with self._beeond_lock:
            if name in self.beeond_volumes:
                raise ValueError("BeeOND volume %r already exists" % name)
            volume = BeeONDVolume(self, config)
            self.beeond_volumes[name] = volume
            return volume

    def create_adhoc_filesystem(self, provider: Any, name: str = "default", scope: str = "workflow",
                                default: bool = False, export: Optional[str] = None, owner: Any = None,
                                **options: Any) -> Any:
        """Create and register an ad-hoc file system or data store resource.

        :param provider: a registered provider name (``dagonfs``, ``beeond``,
            ``hercules``, ``capio``, ``dynostore``, or one added with
            :func:`dagon.adhoc.register_provider`) or an adapter class
        :param scope: ``"workflow"`` (started before the first task, stopped
            after the last) or ``"task"`` (started and stopped around the one
            task it is bound to; see :meth:`dagon.task.Task.create_adhoc_filesystem`);
            ``"volume"`` is reserved for the resource of a ``TaskType.VOLUME``
            task, passed as *owner* (see :mod:`dagon.volume`)
        :param default: bind the workflow-scope resource to every task at run time
        :param export: an extra environment variable, chosen by the developer,
            that carries the resource's path in every task it is bound to (in
            addition to ``DAGON_ADHOC_<NAME>_PATH``); see
            :func:`dagon.adhoc.check_export_name` for the names refused
        """
        from dagon.adhoc import SCOPES, check_export_name, create
        if scope not in SCOPES:
            raise ValueError("ad-hoc scope must be one of %s" % ", ".join(SCOPES))
        if default and scope != "workflow":
            raise ValueError("only a workflow-scope resource can be the default of every task")
        if (scope == "volume") != (owner is not None):
            raise ValueError("volume-scope resources are created by a volume task (TaskType.VOLUME)")
        if name in self.adhoc_filesystems:
            raise ValueError("ad-hoc file system %r already exists" % name)
        if export is not None:
            check_export_name(export)
        filesystem = create(self, provider, name=name, **options)
        filesystem.scope = scope
        filesystem.default = bool(default)
        filesystem.export = export
        filesystem.owner = owner
        self.adhoc_filesystems[name] = filesystem
        return filesystem

    def _bind_default_adhoc_filesystems(self) -> None:
        for filesystem in self.adhoc_filesystems.values():
            if getattr(filesystem, "default", False):
                for task in self.tasks:
                    filesystem.bind(task)

    def plan_streams(self, prepare: bool = True) -> List[Any]:
        """Resolve ``workflow://...?stream`` references into stream channels.

        A reference is a stream when its query names ``stream``; it is carried
        by the streaming ad-hoc resource that both tasks are bound to (or the
        one named by ``stream=<name>``).  A consumer starts as soon as the
        producer runs when *all* its references to that producer are streams.
        Called by :meth:`run`; returns the planned channels.  With
        ``prepare=False`` (CWL export) resources are not told about the
        streams, so planning has no side effect outside the tasks.
        """
        import uuid as _uuid
        from dagon.streaming import StreamChannel, parse_reference, validate_stream_path, iter_command_references
        if self.run_id is None:
            self.run_id = _uuid.uuid4().hex[:12]
        for task in self.tasks:
            task.stream_inputs, task.stream_outputs = [], {}
            task.stream_prevs, task.stream_references = [], {}
            task.stream_started.clear()
            task.stream_launched = False
        channels: Dict[Any, Any] = {}
        for consumer in self.tasks:
            command = getattr(consumer, "command", None)
            if not isinstance(command, str) or "?" not in command:
                continue
            plain, streamed = set(), set()
            for _, _, text in iter_command_references(command, self.SCHEMA):
                reference = parse_reference(text, self.SCHEMA)
                producer = self.find_task_by_name(reference.workflow or self.name, reference.task)
                if not reference.stream:
                    plain.add(producer)
                    continue
                if reference.workflow not in ("", self.name):
                    raise ValueError("%s: streams between workflows are not supported: %s" % (consumer.name, text))
                if producer is None:
                    raise ValueError("%s: stream producer not found: %s" % (consumer.name, text))
                if producer is consumer:
                    raise ValueError("%s: a task cannot consume its own stream: %s" % (consumer.name, text))
                if getattr(producer, "is_volume_task", False):
                    raise ValueError("%s: %s is a volume task; streams are produced by command tasks bound to its "
                                     "volume: workflow:///<producer>/<path>?stream=%s"
                                     % (text, producer.name, producer.volume_name))
                for endpoint in (producer, consumer):
                    if not getattr(endpoint, "stream_capable", False):
                        raise ValueError("%s tasks cannot produce or consume streams (%s)"
                                         % (type(endpoint).__name__, text))
                path = validate_stream_path(reference.path)
                shared = [fs for fs in getattr(consumer, "adhoc_filesystems", [])
                          if fs in getattr(producer, "adhoc_filesystems", [])]
                if reference.stream_filesystem:
                    shared = [fs for fs in shared if fs.name == reference.stream_filesystem]
                    if not shared:
                        raise ValueError("%s: ad-hoc file system %r is not bound to both %s and %s"
                                         % (text, reference.stream_filesystem, producer.name, consumer.name))
                capable = [fs for fs in shared if fs.supports_streaming]
                if not capable:
                    raise ValueError("%s: %s and %s share no ad-hoc file system that supports streaming"
                                     % (text, producer.name, consumer.name))
                if len(capable) > 1:
                    raise ValueError("%s: %s and %s share several streaming resources (%s); name one with "
                                     "?stream=<name>" % (text, producer.name, consumer.name,
                                                         ", ".join(fs.name for fs in capable)))
                filesystem = capable[0]
                channel = channels.get((producer, path))
                if channel is None:
                    channel = StreamChannel(producer, path, filesystem, self.run_id,
                                            emulated=self.portable_emulation)
                    channel.location = filesystem.stream_location(channel)
                    channel.signal = os.path.join(self.get_scratch_dir_base(), ".dagon", "stream-signals",
                                                  self.run_id, channel.key + ".ended")
                    channels[(producer, path)] = channel
                    producer.stream_outputs[path] = channel
                elif channel.filesystem is not filesystem:
                    raise ValueError("stream %s/%s is carried by %s; %s names %s"
                                     % (producer.name, path, channel.filesystem.name, consumer.name, filesystem.name))
                if consumer not in channel.consumers:
                    channel.consumers.append(consumer)
                if channel not in consumer.stream_inputs:
                    consumer.stream_inputs.append(channel)
                consumer.stream_references[text] = channel
                streamed.add(producer)
            consumer.stream_prevs = [task for task in consumer.prevs if task in streamed and task not in plain]
        self.streams = list(channels.values())
        if prepare:
            for filesystem in self.adhoc_filesystems.values():
                filesystem.prepare_streams([channel for channel in self.streams if channel.filesystem is filesystem])
        return self.streams

    def _cwl_streams(self, task: Any, task_ids: Dict[Any, str], command: str, step_inputs: Dict[str, str],
                     tool_inputs: Dict[str, Any]) -> Tuple[str, Dict[str, str], Dict[str, Any], List[Dict[str, Any]]]:
        """CWL form of the streams of *task*: materialized stream Directories.

        CWL v1.2 has no concurrency between steps.  The producer's stream is a
        ``Directory`` output (the same items and markers, ended by
        ``dagon.adhoc stream close``); the consumer receives it as an input
        after the producer completes.  The ``dagon:Stream`` hint keeps the
        streaming intent for runners that can honour it.
        """
        from dagon.streaming import variable_suffix
        environment: Dict[str, str] = {}
        outputs: Dict[str, Any] = {}
        hints: List[Dict[str, Any]] = []

        def identifier(channel: Any) -> str:
            return "stream_" + re.sub(r"[^A-Za-z0-9_]", "_", channel.key.lower())

        def spec(channel: Any, location: str) -> str:
            return json.dumps({"v": 1, "location": location, "access": "posix", "adhoc": channel.filesystem.name,
                               "provider": channel.filesystem.provider, "adapter": "dagon.adhoc:AdHocFileSystem",
                               "producer": channel.producer.name, "path": channel.path, "parameters": {}},
                              sort_keys=True)

        def consumed(channel: Any) -> str:
            after = "after_" + task_ids[channel.producer]
            if after in step_inputs and self.portable_emulation:
                # The producer's whole working directory is already an input;
                # a second, nested Directory input is not staged reliably.
                return "$(inputs.%s.path)/.dagon-streams/%s" % (after, channel.path)
            input_id = identifier(channel)
            tool_inputs[input_id] = "Directory"
            step_inputs[input_id] = "%s/%s" % (task_ids[channel.producer], input_id)
            return "$(inputs.%s.path)" % input_id

        locations = {id(channel): consumed(channel) for channel in task.stream_inputs}
        for text, channel in sorted(task.stream_references.items()):
            command = command.replace(text, locations[id(channel)])
        for channel in task.stream_inputs:
            location = locations[id(channel)]
            environment["DAGON_STREAM_%s" % channel.key] = location
            environment["DAGON_STREAM_%s_SPEC" % channel.key] = spec(channel, location)
            environment["DAGON_STREAM_IN_%s" % channel.key] = location
            # Not "path": CWL processors resolve a field of that name as a URI.
            hints.append({"producer": channel.producer.name, "stream": channel.path,
                          "adhoc": channel.filesystem.name, "provider": channel.filesystem.provider})
        if len(task.stream_inputs) == 1:
            environment["DAGON_STREAM_IN"] = locations[id(task.stream_inputs[0])]
        if task.stream_inputs:
            # The materialized stream is complete when the consumer starts: a
            # missing marker is an error, not a producer still writing.
            environment["DAGON_STREAM_IDLE_TIMEOUT"] = "60"
        produced = list(task.stream_outputs.values())
        if produced:
            closes = []
            for channel in produced:
                location = "$(runtime.outdir)/.dagon-streams/%s" % channel.path
                environment["DAGON_STREAM_%s" % channel.key] = location
                environment["DAGON_STREAM_%s_SPEC" % channel.key] = spec(channel, location)
                environment["DAGON_STREAM_OUT_%s" % variable_suffix(channel.path)] = location
                outputs[identifier(channel)] = {"type": "Directory",
                                                "outputBinding": {"glob": ".dagon-streams/%s" % channel.path}}
                closes.append('"$DAGON_PYTHON" -m dagon.adhoc stream close "$DAGON_STREAM_%s" --status "$code" '
                              '|| code=1' % channel.key)
            if len(produced) == 1:
                environment["DAGON_STREAM_OUT"] = environment["DAGON_STREAM_%s" % produced[0].key]
            environment["DAGON_STREAM_STATE_DIR"] = "$(runtime.outdir)/.dagon/streams"
            command = "(%s); code=$?; %s; exit \"$code\"" % (command, "; ".join(closes))
        if environment:
            environment.setdefault("DAGON_PYTHON", "python3")
        return command, environment, outputs, hints

    def stop_adhoc_filesystems(self, raise_errors: bool = True) -> Dict[str, Optional[int]]:
        """Stop all started ad-hoc resources, continuing after errors."""
        results: Dict[str, Optional[int]] = {}
        errors = []
        for name, filesystem in reversed(list(self.adhoc_filesystems.items())):
            if not filesystem.started:
                results[name] = None
                continue
            try:
                results[name] = filesystem.stop()
            except Exception as exc:
                results[name] = None
                errors.append(str(exc))
                self.logger.error("%s", exc)
        if errors and raise_errors:
            raise RuntimeError("; ".join(errors))
        return results

    def release_volumes(self, raise_errors: bool = True) -> None:
        """Release every volume of a volume task still held at the end of a run.

        Volumes are normally released when their last reference is gone (or by
        a destroy task); this covers ``release="end"``, failed users, and
        interruptions.
        """
        errors = []
        for task in self.tasks:
            if getattr(task, "is_volume_task", False) and task.action == "create":
                try:
                    task.release_volume("workflow ended", raise_errors=True)
                except Exception as exc:
                    errors.append(str(exc))
        if errors and raise_errors:
            raise RuntimeError("; ".join(errors))

    def add_beeond_volume(self, volume: Any) -> Any:
        """Register an existing :class:`dagon.beeond.BeeONDVolume` and return it."""
        with self._beeond_lock:
            existing = self.beeond_volumes.get(volume.name)
            if existing is not None and existing is not volume:
                raise ValueError("BeeOND volume %r already exists" % volume.name)
            self.beeond_volumes[volume.name] = volume
            return volume

    def get_beeond_volume(self, name: str = "default") -> Any:
        """Return the named workflow-scope BeeOND volume, creating it from defaults."""
        with self._beeond_lock:
            volume = self.beeond_volumes.get(name)
        if volume is not None:
            return volume
        try:
            return self.create_beeond_volume(name)
        except ValueError:
            # Another task thread created it concurrently.
            return self.beeond_volumes[name]

    def stop_beeond_volumes(self, raise_errors: bool = True) -> Dict[str, Optional[int]]:
        """Persist and release every started workflow-scope BeeOND volume.

        :return: persistence code per volume (``None`` when never started)
        :raises RuntimeError: when *raise_errors* and a volume failed to persist
        """
        results: Dict[str, Optional[int]] = {}
        errors = []
        for name, volume in list(self.beeond_volumes.items()):
            try:
                results[name] = volume.stop()
            except Exception as exc:  # keep stopping the remaining volumes
                results[name] = getattr(volume, "persist_code", None)
                errors.append(str(exc))
                self.logger.error("%s", exc)
        if errors and raise_errors:
            raise RuntimeError("; ".join(errors))
        return results

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
        if self.pre_stage:
            # Only present when enabled, so default JSON documents are unchanged.
            jsonWorkflow["pre_stage"] = True
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
        # it here as well; make_dependencies() keeps explicit edges.
        if not self._dependencies_made:
            self.make_dependencies()
        streams = self.plan_streams(prepare=False)

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
        agentic_tasks = [task for task in self.tasks if type(task).__name__ == "AgenticTask"]
        # Narrow file bindings for agentic tasks: producer -> {relative path: output id}.
        file_outputs: Dict[Any, Dict[str, str]] = {}
        agentic_bindings: Dict[Any, List[Any]] = {}
        # Meta-tasks bind their workflow:// inputs the same way (File or Directory).
        meta_tasks = [task for task in self.tasks if type(task).__name__ == "MetaTask"]
        # Create volume tasks bind their staged-in references the same way.
        volume_tasks = [task for task in self.tasks if getattr(task, "is_volume_task", False)]
        output_types: Dict[Any, Dict[str, str]] = {}
        bound_tasks = agentic_tasks + (meta_tasks if not self.portable_emulation else []) + (
            [task for task in volume_tasks if task.action == "create"] if not self.portable_emulation else [])
        for task in bound_tasks:
            bindings = []
            kind = {"AgenticTask": "agentic", "VolumeTask": "volume"}.get(type(task).__name__, "meta")
            for reference, workflow_name, relative, producer in task._producers():
                if workflow_name != self.name or producer not in task_ids:
                    raise ValueError("CWL export of %s task %s supports only producers in workflow %s: %s"
                                     % (kind, task.name, self.name, reference))
                produced = file_outputs.setdefault(producer, {})
                if type(producer).__name__ == "AgenticTask":
                    names = {path: name for name, path in producer.outputs.items()}
                    if relative not in names:
                        raise ValueError("%s is not a declared output of agentic task %s" % (reference, producer.name))
                    produced[relative] = names[relative]
                elif relative not in produced:
                    reserved = {"completed", "task_dir"} | set(produced.values())
                    produced[relative] = cwl_identifier("file_" + relative, reserved)
                if kind in ("meta", "volume") and task.input_kind(reference) == "Directory":
                    output_types.setdefault(producer, {})[relative] = "Directory"
                bindings.append((reference, producer, relative, produced[relative]))
            agentic_bindings[task] = bindings
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
                tool_inputs[input_id] = "Directory" if self.portable_emulation else "boolean"
                step_inputs[input_id] = task_ids[previous] + ("/task_dir" if self.portable_emulation else "/completed")

            if type(task).__name__ == "AgenticTask":
                steps[task_ids[task]] = self._agentic_cwl_step(task, task_ids, step_inputs, tool_inputs,
                                                               agentic_bindings[task])
                continue
            if type(task).__name__ == "MetaTask" and not self.portable_emulation:
                steps[task_ids[task]] = self._meta_cwl_step(task, task_ids, step_inputs, tool_inputs,
                                                            agentic_bindings[task])
                continue
            if getattr(task, "is_volume_task", False):
                steps[task_ids[task]] = self._volume_cwl_step(task, task_ids, step_inputs, tool_inputs,
                                                              agentic_bindings.get(task, []))
                continue

            bound_command = False
            if not self.portable_emulation and agentic_tasks:
                # Narrow binding: a command that reads a declared agentic output gets that File.
                for producer in agentic_tasks:
                    if producer not in task.prevs:
                        continue
                    for output_name, relative in sorted(producer.outputs.items()):
                        for prefix in ("workflow:///%s/" % producer.name,
                                       "workflow://%s/%s/" % (self.name, producer.name)):
                            if prefix + relative in command:
                                input_id = "%s_%s" % (task_ids[producer], output_name)
                                tool_inputs[input_id] = "File"
                                step_inputs[input_id] = task_ids[producer] + "/" + output_name
                                command = command.replace(prefix + relative, "$(inputs.%s.path)" % input_id)
                                bound_command = True

            stream_environment: Dict[str, str] = {}
            stream_outputs: Dict[str, Any] = {}
            stream_hints: List[Dict[str, Any]] = []
            if task.stream_inputs or task.stream_outputs:
                command, stream_environment, stream_outputs, stream_hints = self._cwl_streams(
                    task, task_ids, command, step_inputs, tool_inputs)
                bound_command = True

            if self.portable_emulation:
                command_types = {"Checkpoint", "RemoteCheckpoint", "Batch", "RemoteBatch", "Slurm",
                                 "RemoteSlurm", "CloudTask", "DockerTask", "DockerRemoteTask",
                                 "KubernetesTask", "RemoteKubernetesTask", "ApptainerTask",
                                 "RemoteApptainerTask", "NomadTask", "RemoteNomadTask"}
                if type(task).__name__ in command_types:
                    if type(task).__name__ in {"Checkpoint", "RemoteCheckpoint"}:
                        command = command.split("checkpoint.sh ", 1)[-1]
                    for previous in task.prevs:
                        input_id = "after_" + task_ids[previous]
                        for prefix in ("workflow:///%s/" % previous.name,
                                       "workflow://%s/%s/" % (self.name, previous.name)):
                            command = command.replace(prefix, "$(inputs.%s.path)/" % input_id)
                    if type(task).__name__ in {"Checkpoint", "RemoteCheckpoint"}:
                        command = "test -f " + command
                else:
                    command = "mkdir -p outputs; printf '%s\\n' '{\"portable_emulation\":true}' > outputs/result.json"

            tool = {
                "class": "CommandLineTool",
                "label": str(task.name),
                "requirements": {"InlineJavascriptRequirement": {},
                                 **({"EnvVarRequirement": {"envDef": stream_environment}}
                                    if stream_environment else {})},
                "baseCommand": ["/bin/sh", "-c"] if self.portable_emulation or bound_command
                else ["/bin/sh", "-c", command],
                **({"arguments": [command]} if self.portable_emulation or bound_command else {}),
                "inputs": tool_inputs,
                "outputs": {
                    "completed": {
                        "type": "boolean",
                        "outputBinding": {
                            "outputEval": "$(runtime.exitCode === 0)"
                        },
                    },
                    **({"task_dir": {"type": "Directory", "outputBinding": {"glob": "."}}}
                       if self.portable_emulation else {})
                },
            }
            tool["outputs"].update(stream_outputs)
            image = getattr(task, "image", None)
            if image and not self.portable_emulation:
                tool["hints"] = {"DockerRequirement": {"dockerPull": image}}
            if stream_hints:
                tool.setdefault("hints", {})["dagon:Stream"] = {"inputs": stream_hints}

            if type(task).__name__ == "FaaSTask" and not self.portable_emulation:
                portable_spec = task._portable_spec()
                tool.update({
                    "baseCommand": ["python", "-m", "dagon.faas_runner"],
                    "arguments": ["--spec", "faas-task.json"],
                    "requirements": {
                        "InitialWorkDirRequirement": {
                            "listing": [{"entryname": "faas-task.json", "entry": json.dumps(portable_spec, sort_keys=True)}]
                        }
                    },
                    "hints": {"dagon:FaaSInvocation": {
                        "provider": task.provider, "profile": task.profile, "function": task.function,
                    }},
                })

            if type(task).__name__ == "IoTTask" and not self.portable_emulation:
                portable_spec = task._portable_spec()
                tool.update({
                    "baseCommand": ["dagon-iot-runner", "run"],
                    "arguments": ["--spec", "iot-task.json", "--workdir", ".",
                                  "--result", "outputs/result.json"],
                    "requirements": {"InitialWorkDirRequirement": {"listing": [
                        {"entryname": "iot-task.json", "entry": json.dumps(portable_spec, sort_keys=True)}]}},
                    "hints": {"dagon:IoTTask": portable_spec},
                })
                for output_name, output_path in task.outputs.items():
                    tool["outputs"][output_name] = {"type": "File", "outputBinding": {"glob": output_path}}
                step_outputs = ["completed"] + list(task.outputs)
            else:
                step_outputs = ["completed"] + (["task_dir"] if self.portable_emulation else [])

            steps[task_ids[task]] = {
                "label": str(task.name),
                "in": step_inputs,
                "out": step_outputs + sorted(stream_outputs),
                "run": tool,
            }

        if not self.portable_emulation:
            for producer, produced in file_outputs.items():
                if type(producer).__name__ == "AgenticTask":
                    continue
                step = steps[task_ids[producer]]
                for relative, output_id in sorted(produced.items(), key=lambda item: item[1]):
                    if output_id in step["run"]["outputs"]:
                        continue
                    output_type = output_types.get(producer, {}).get(relative, "File")
                    if type(producer).__name__ in ("MetaTask", "VolumeTask"):
                        output_type = producer.output_kind(relative) or output_type
                    step["run"]["outputs"][output_id] = {"type": output_type, "outputBinding": {"glob": relative}}
                    step["out"].append(output_id)

        terminal_tasks = [task for task in self.tasks if not task.nexts]
        outputs = {
            task_ids[task] + "_completed": {
                "type": "boolean",
                "outputSource": task_ids[task] + "/completed",
            }
            for task in terminal_tasks
        }
        if not self.portable_emulation:
            # The external workflow's declared outputs are workflow results.
            for task in meta_tasks:
                for output_name, declared in sorted(task.outputs.items()):
                    outputs[task_ids[task] + "_" + output_name] = {
                        "type": "Directory" if declared["type"] == "directory" else "File",
                        "outputSource": task_ids[task] + "/" + output_name}
        for task in agentic_tasks:
            for output_name in ("result", "evaluation"):
                outputs[task_ids[task] + "_" + output_name] = {
                    "type": "File", "outputSource": task_ids[task] + "/" + output_name}
        document = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "label": self.name,
            "inputs": {"dagon_config": "File"} if agentic_tasks else {},
            "outputs": outputs,
            "steps": steps,
        }
        if streams or any(type(task).__name__ in {"FaaSTask", "IoTTask", "AgenticTask", "MetaTask", "VolumeTask"}
                                for task in self.tasks):
            document["$namespaces"] = {"dagon": "https://dagonstar.org/cwl#"}
        with open(os.fspath(filename), "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=False)
            stream.write("\n")

    def _meta_cwl_step(self, task: Any, task_ids: Dict[Any, str], step_inputs: Dict[str, str],
                       tool_inputs: Dict[str, Any], bindings: List[Any]) -> Dict[str, Any]:
        """Return the executable CWL step of a meta-task (``dagon-meta-runner``).

        The credential-free specification is embedded; every ``workflow://``
        input is bound to the producer step's File or Directory output.  The
        external engine and the workflow definition named in the specification
        must be installed on the CWL execution host: what the engine does
        inside its run is outside the portable command-graph contract.
        """
        from dagon.meta.runner import workflow_identity
        arguments = ["--spec", "meta-task.json", "--workdir", "."]
        for index, (reference, producer, relative, output_id) in enumerate(bindings):
            input_id = "in_%d" % index
            tool_inputs[input_id] = task.input_kind(reference)
            step_inputs[input_id] = task_ids[producer] + "/" + output_id
            arguments += ["--bind", "%s=$(inputs.%s.path)" % (reference, input_id)]
        outputs: Dict[str, Any] = {"completed": {"type": "boolean",
                                                 "outputBinding": {"outputEval": "$(runtime.exitCode === 0)"}}}
        for name, declared in sorted(task.outputs.items()):
            outputs[name] = {"type": "Directory" if declared["type"] == "directory" else "File",
                             "outputBinding": {"glob": "outputs/" + declared["path"]}}
        spec = task.portable_spec()
        identity = workflow_identity(spec["workflow"])
        tool = {
            "class": "CommandLineTool",
            "label": str(task.name),
            "requirements": {
                "InlineJavascriptRequirement": {},
                "InitialWorkDirRequirement": {"listing": [
                    {"entryname": "meta-task.json", "entry": json.dumps(spec, sort_keys=True)}]},
            },
            "hints": {"dagon:MetaTask": {"schema_version": spec["schema_version"], "engine": spec["engine"],
                                         "workflow": spec["workflow"], "workflow_sha256": identity["sha256"]}},
            "baseCommand": ["dagon-meta-runner", "run"],
            "arguments": arguments,
            "inputs": tool_inputs,
            "outputs": outputs,
        }
        return {"label": str(task.name), "in": step_inputs, "out": list(outputs), "run": tool}

    def _volume_cwl_step(self, task: Any, task_ids: Dict[Any, str], step_inputs: Dict[str, str],
                         tool_inputs: Dict[str, Any], bindings: List[Any]) -> Dict[str, Any]:
        """Return the CWL step of a volume task: the volume in materialized form.

        CWL v1.2 has no shared, mutable storage between steps.  A create step
        materializes the staged-in content as the ``Directory`` output
        ``volume`` (``<volume>/`` of its working directory, which is also what
        ``workflow:///<task>/<volume>/...`` names); a destroy step copies its
        ``stage_out`` entries from that directory into its own working
        directory.  Data that sibling steps write into the volume during a
        DAGonStar run is not exchanged through CWL.  A ``dagon:Volume`` hint
        records the provider, volume, action, and release policy.
        """
        from dagon.shell import quote as shell_quote
        spec = task.portable_spec()
        lines = ["set -e"]
        outputs: Dict[str, Any] = {"completed": {"type": "boolean",
                                                 "outputBinding": {"outputEval": "$(runtime.exitCode === 0)"}}}
        if task.action == "create":
            owner = task
            bound = {reference: "$(inputs.%s.path)" % ("in_%d" % index)
                     for index, (reference, _, _, _) in enumerate(bindings)}
            for index, (reference, producer, relative, output_id) in enumerate(bindings):
                input_id = "in_%d" % index
                tool_inputs[input_id] = task.input_kind(reference)
                step_inputs[input_id] = task_ids[producer] + "/" + output_id
            lines.append("mkdir -p %s" % shell_quote(task.volume_name))
            for target, descriptor in sorted(task.stage_in.items()):
                location = descriptor["path"]
                if location in bound:
                    source = '"%s"' % bound[location]
                elif location.startswith(self.SCHEMA):
                    reference = location[len(self.SCHEMA):].split("/")
                    producer = self.find_task_by_name(reference[0] or self.name, reference[1])
                    if producer is None or producer not in task_ids:
                        raise ValueError("CWL export of volume task %s supports only producers in workflow %s: %s"
                                         % (task.name, self.name, location))
                    source = '"$(inputs.after_%s.path)"/%s' % (task_ids[producer], "/".join(reference[2:]))
                else:
                    source = shell_quote(location)
                destination = task.volume_name + "/" + target
                # No "$(...)" shell substitution: CWL would evaluate it as an expression.
                lines.append("mkdir -p %s && cp -R %s %s" % (shell_quote(os.path.dirname(destination)), source,
                                                            shell_quote(destination)))
            outputs["volume"] = {"type": "Directory", "outputBinding": {"glob": task.volume_name}}
        else:
            owner = task.resolve_target()
            if owner not in task_ids:
                raise ValueError("volume %s of %s is not in workflow %s" % (task.target, task.name, self.name))
            if self.portable_emulation:
                root = '"$(inputs.after_%s.path)"/%s' % (task_ids[owner], shell_quote(owner.volume_name))
            else:
                tool_inputs["volume"] = "Directory"
                step_inputs["volume"] = task_ids[owner] + "/volume"
                root = '"$(inputs.volume.path)"'
            for target, descriptor in sorted(task.stage_out.items()):
                source = root + ("/" + descriptor["path"] if descriptor["path"] else "")
                parent = os.path.dirname(target)
                lines.append("%scp -R %s %s" % ("mkdir -p %s && " % shell_quote(parent) if parent else "", source,
                                                shell_quote(target)))
                if descriptor["type"] != "auto":
                    # A declared kind is a typed CWL output; "auto" stays inside task_dir.
                    outputs["staged_" + re.sub(r"[^A-Za-z0-9_]", "_", target)] = {
                        "type": "Directory" if descriptor["type"] == "directory" else "File",
                        "outputBinding": {"glob": target}}
        if self.portable_emulation:
            outputs["task_dir"] = {"type": "Directory", "outputBinding": {"glob": "."}}
        filesystem = owner.filesystem
        tool = {
            "class": "CommandLineTool",
            "label": str(task.name),
            "requirements": {"InlineJavascriptRequirement": {}},
            "hints": {"dagon:Volume": {"schema_version": spec["schema_version"], "action": task.action,
                                       "volume": owner.volume_name, "provider": filesystem.provider,
                                       "access": filesystem.access, "release": owner.release}},
            "baseCommand": ["/bin/sh", "-c"],
            "arguments": ["\n".join(lines)],
            "inputs": tool_inputs,
            "outputs": outputs,
        }
        return {"label": str(task.name), "in": step_inputs, "out": list(outputs), "run": tool}

    def _agentic_cwl_step(self, task: Any, task_ids: Dict[Any, str], step_inputs: Dict[str, str],
                          tool_inputs: Dict[str, Any], bindings: List[Any]) -> Dict[str, Any]:
        """Return the executable CWL step of an agentic task (``dagon-agent-runner``).

        The versioned contract is embedded; the agent profile is resolved at
        run time from the ``dagon_config`` File input, so no endpoint,
        credential, or scratch path is exported.
        """
        from dagon.agentic.models import contract_digest
        arguments = ["--spec", "agent-task.json", "--config", "$(inputs.dagon_config.path)", "--workdir", ".",
                     "--workflow", self.name, "--task", str(task.name)]
        for index, (reference, producer, relative, output_id) in enumerate(bindings):
            if self.portable_emulation:
                arguments += ["--bind", "%s=$(inputs.after_%s.path)/%s" % (reference, task_ids[producer], relative)]
            else:
                input_id = "in_%d" % index
                tool_inputs[input_id] = "File"
                step_inputs[input_id] = "%s/%s" % (task_ids[producer], output_id)
                arguments += ["--bind", "%s=$(inputs.%s.path)" % (reference, input_id)]
        if self.portable_emulation:
            arguments.append("--portable-emulation")
        tool_inputs["dagon_config"] = "File"
        step_inputs["dagon_config"] = "dagon_config"
        outputs: Dict[str, Any] = {"completed": {"type": "boolean",
                                                 "outputBinding": {"outputEval": "$(runtime.exitCode === 0)"}}}
        for name, relative in sorted(task.outputs.items()):
            outputs[name] = {"type": "File", "outputBinding": {"glob": relative}}
        if self.portable_emulation:
            outputs["task_dir"] = {"type": "Directory", "outputBinding": {"glob": "."}}
        spec = task.portable_spec()
        tool = {
            "class": "CommandLineTool",
            "label": str(task.name),
            "requirements": {
                "InlineJavascriptRequirement": {},
                "InitialWorkDirRequirement": {"listing": [
                    {"entryname": "agent-task.json", "entry": json.dumps(spec, sort_keys=True)}]},
            },
            "hints": {"dagon:AgenticTask": {"schema_version": spec["schema_version"], "agent_profile": spec["agent"],
                                            "contract_sha256": contract_digest(spec)}},
            "baseCommand": ["dagon-agent-runner", "run"],
            "arguments": arguments,
            "inputs": tool_inputs,
            "outputs": outputs,
        }
        return {"label": str(task.name), "in": step_inputs, "out": list(outputs), "run": tool}

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
        self.run_id = None
        self._bind_default_adhoc_filesystems()
        self.plan_streams()
        self._fire_event("on_workflow_start", self)
        try:
            for filesystem in self.adhoc_filesystems.values():
                if getattr(filesystem, "scope", "workflow") == "workflow":
                    filesystem.start()
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

            # Persist and release workflow-scope BeeOND volumes before reporting.
            beeond_error = None
            try:
                self.stop_beeond_volumes()
            except RuntimeError as exc:
                beeond_error = exc
            adhoc_error = None
            try:
                self.release_volumes()
                self.stop_adhoc_filesystems()
            except RuntimeError as exc:
                adhoc_error = exc

            completed_in = (time() - start_time)
            self.logger.info("Workflow '" + self.name + "' completed in %s seconds ---" % completed_in)

            if self.checkpoint_file is not None:
                self.checkpoints['_scratch_dir'] = self.get_scratch_dir_base()
                with open(self.checkpoint_file, 'w') as fp:
                    fp.write(json.dumps(self.checkpoints, sort_keys=True, indent=4))
            if beeond_error is not None:
                raise beeond_error
            if adhoc_error is not None:
                raise adhoc_error
        finally:
            # Idempotent: only volumes still running (for example after an
            # interruption) are persisted and released here.
            self.stop_beeond_volumes(raise_errors=False)
            self.release_volumes(raise_errors=False)
            self.stop_adhoc_filesystems(raise_errors=False)
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
        from dagon.prestage import validate_pre_stage
        self.name = Json_data['name']
        self.workflow_id = Json_data['id']
        if 'pre_stage' in Json_data:
            self.pre_stage = validate_pre_stage(Json_data['pre_stage'], allow_none=False)
        for task in Json_data['tasks']:
            temp = Json_data['tasks'][task]
            options = {}
            if temp['type'].upper() == 'LLM':
                options['provider'] = temp.get('provider')
                options['params'] = temp.get('params')
                options['input_files'] = temp.get('input_files')
                options['output_file'] = temp.get('output_file', 'response.json')
            if temp['type'].upper() == 'SLURM' and temp.get('beeond') is not None:
                options['beeond'] = temp['beeond']
            if temp['type'].upper() == 'SLURM' and temp.get('pre_stage') is not None:
                options['pre_stage'] = temp['pre_stage']
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
            elif temp['type'].upper() == 'FAAS':
                specification = {key: temp.get(key) for key in (
                    'provider', 'profile', 'function', 'inputs', 'outputs', 'invocation', 'timeout', 'retry',
                    'completion', 'input_policy', 'output_policy', 'provider_options', 'annotations')
                    if temp.get(key) is not None}
                tk = DagonTask(TaskType.FAAS, temp['name'], specification,
                               working_dir=temp.get('working_dir'))
            elif temp['type'].upper() == 'AGENTIC':
                contract = dict(temp.get('agentic', {}))
                contract.pop('schema_version', None)
                tk = DagonTask(TaskType.AGENTIC, temp['name'], **contract)
            elif temp['type'].upper() == 'VOLUME':
                spec = dict(temp.get('volume', {}))
                spec.pop('schema_version', None)
                if spec.get('action') == 'destroy':
                    tk = DagonTask(TaskType.VOLUME, temp['name'], action='destroy', volume=spec.get('volume'),
                                   stage_out=spec.get('stage_out'), release=spec.get('release', 'auto'))
                else:
                    tk = DagonTask(TaskType.VOLUME, temp['name'], provider=spec.get('provider'),
                                   volume=spec.get('volume'), stage_in=spec.get('stage_in'),
                                   options=spec.get('options'), export=spec.get('export'),
                                   release=spec.get('release', 'auto'))
            elif temp['type'].upper() == 'META':
                tk = DagonTask(TaskType.META, temp['name'], **{key: value for key, value in dict(
                    temp.get('meta', {})).items() if key != 'schema_version'})
            elif temp['type'].upper() == 'IOT':
                raw = dict(temp.get('iot', {}))
                aliases = {'endpointRef': 'endpoint_ref', 'credentialRef': 'credential_ref',
                           'providerOptions': 'provider_options', 'schemaVersion': None}
                specification = {}
                for key, value in raw.items():
                    mapped = aliases.get(key, key)
                    if mapped is not None:
                        specification[mapped] = value
                tk = DagonTask(TaskType.IOT, temp['name'], **specification)
            else:
                tk = DagonTask(TaskType[temp['type'].upper()], temp['name'], temp['command'], **options)
            self.add_task(tk)
        self._load_explicit_edges(Json_data['tasks'])

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
