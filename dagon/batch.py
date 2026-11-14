import os
import shlex
from typing import Any, Dict, List, Optional, Union

from dagon.task import ExecutionResult, Task
from dagon.remote import RemoteTask
from subprocess import Popen, PIPE, STDOUT
from dagon.shell import join_command, quote
from dagon.platform_support import bash_executable, launcher_environment
from dagon.prestage import MARKER_NAME, STAGE_SCRIPT_NAME, validate_pre_stage


class Batch(Task):
    """
    **Executes a Batch task**
    """

    def __init__(
            self,
            name: str,
            command: str,
            working_dir: Optional[str] = None,
            globusendpoint: Optional[str] = None,
            transversal_workflow: Optional[str] = None) -> None:
        """
        :param name: task name
        :type name: str

        :param command: command to be executed
        :type command: str

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str
        """
        Task.__init__(self, name, command, working_dir,transversal_workflow = transversal_workflow, globusendpoint=globusendpoint)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create an Batch task local or remote

           Keyword arguments:
           name -- task name


           command -- command to be executed
           working_dir -- directory where the outputs will be placed
           ip -- hostname or ip of the machine where the task will be executed
           ssh_username -- username in remote machine
           keypath -- path to the private keypath
        """
        #if "ip" in kwargs:
        #    return super(Task, cls).__new__(RemoteBatch)
        #else:
        #    return super(Batch, cls).__new__(cls, *args, **kwargs)
        
        if "ip" in kwargs:
            return super().__new__(RemoteBatch)
        else:
            return super().__new__(cls)

    @staticmethod
    def execute_command(command: str) -> ExecutionResult:
        """
        Executes a local command

        :param command: command to be executed
        :type command: str
        :return: execution result
        :rtype: dict() with the execution output (str), code (int) and error (str)
        """
        # Execute the bash command
        # with settings(
        #         hide('warnings', 'running', 'stdout', 'stderr'),
        #         warn_only=True
        # ):
        #     result = local(command, capture=True)
        #     # check for an error
        #     code, message = 0, ""
        #     if len(result.stderr):
        #         code, message = 1, result.stderr
        #
        #     return {"code": code, "message": message, "output": result.stdout}
        p = Popen(shlex.split(command), stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True, bufsize=-1, universal_newlines=True,
                  env=launcher_environment())

        out, err = p.communicate()

        code, message = p.returncode, ""
        if err:
            message = err
        elif code:
            message = out
        return {"code": code, "message": message, "output": out}


    def on_execute(self, script: str, script_name: str) -> ExecutionResult:
        """
        Invoke the script specified

        :param script: content script
        :type script: str
        :param script_name: script name
        :type script_name: str
        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # Invoke the base method
        super(Batch, self).on_execute(script, script_name)
        return Batch.execute_command(join_command((bash_executable(), self.working_dir + "/.dagon/" + script_name)))

    # returns public key
    def get_public_key(self) -> str:
        """
        Return the temporal public key to this machine

        :return: public key
        :rtype: str with the public key
        """
        command = join_command(("cat", self.working_dir + "/.dagon/ssh_key.pub"))
        result = Batch.execute_command(command)
        return result['output']

    def add_public_key(self, key: str) -> ExecutionResult:
        """
        Add a SSH public key on the remote machine

        :param key: Path to the public key
        :type key: str
        :return: result of the execution
        :rtype: dict() with the execution output (str) and code (int)
        """
        command = "printf '%s\\n' " + quote(key.strip()) + " >> ~/.ssh/authorized_keys"
        result = Batch.execute_command(command)
        return result


class RemoteBatch(RemoteTask, Batch):
    """
    **Execute a Batch task on a remote machine**
    """

    def __init__(
            self,
            name: str,
            command: str,
            ssh_username: Optional[str] = None,
            keypath: Optional[str] = None,
            ip: Optional[str] = None,
            working_dir: Optional[str] = None,
            globusendpoint: Optional[str] = None) -> None:
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
        RemoteTask.__init__(self, name, command, ssh_username=ssh_username, keypath=keypath, ip=ip, working_dir=working_dir,
                            globusendpoint=globusendpoint)

    def on_execute(self, launcher_script: str, script_name: str) -> ExecutionResult:
        """
        Execute a script on the remote machine

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # Invoke the base method
        RemoteTask.on_execute(self, launcher_script, script_name)
        result = self.ssh_connection.execute_command(join_command(("bash", self.working_dir + "/.dagon/" + script_name)))
        return result


class Slurm(Batch):
    """
    **Run a task using Slurm**

    :ivar comment: some Slurm installations uses the comment to enable non standard features
    :vartype comment: str, array of str

    :ivar partition: partition where the task will be executed
    :vartype partition: str

    :ivar ntasks: number of parallel tasks to be executed
    :vartype ntasks: int

    :ivar memory: memory allocation per node
    :vartype memory: int

    :ivar time: maximum runtime in format HH:MM:SS
    :vartype time: str

    :ivar nodes: number of nodes to request
    :vartype nodes: int

    :ivar ntasks_per_node: number of tasks per node
    :vartype ntasks_per_node: int

    :ivar nodelist: explicit Slurm node list (``--nodelist``)
    :vartype nodelist: str

    :ivar sbatch_options: additional ``sbatch`` options, each passed as one argument
    :vartype sbatch_options: list[str]

    :ivar beeond: optional BeeOND volume specification (see :mod:`dagon.beeond`)
    :vartype beeond: bool, str, dict, :class:`dagon.beeond.BeeONDConfig` or
        :class:`dagon.beeond.BeeONDVolume`

    :ivar pre_stage: scheduler-aware pre-staging override (see :mod:`dagon.prestage`);
        ``None`` inherits :attr:`dagon.Workflow.pre_stage`
    :vartype pre_stage: bool or None

    """

    pre_stage_capable = True

    def __init__(
            self,
            name: str,
            command: str,
            comment: Optional[Union[str, List[str]]] = None,
            partition: Optional[str] = None,
            ntasks: Optional[int] = None,
            memory: Optional[int] = None,
            time: Optional[str] = None,
            nodes: Optional[int] = None,
            ntasks_per_node: Optional[int] = None,
            working_dir: Optional[str] = None,
            globusendpoint: Optional[str] = None,
            nodelist: Optional[str] = None,
            sbatch_options: Optional[List[str]] = None,
            beeond: Any = None,
            pre_stage: Optional[bool] = None) -> None:
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed
        :type command: str

        :param comment: slurm comments separated by a comma
        :type comment: str or array of str

        :param partition: partition where the task will be executed
        :type partition: str

        :param ntasks: number of parallel tasks to be executed
        :type ntasks: int

        :param memory: number of memory to be allocate
        :type memory: int

        :param time: maximum runtime in format HH:MM:SS
        :type time: str

        :param nodes: number of nodes to request
        :type nodes: int

        :param ntasks_per_node: number of tasks per node
        :type ntasks_per_node: int

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str

        :param nodelist: explicit node list passed as ``--nodelist``
        :type nodelist: str

        :param sbatch_options: extra ``sbatch`` options, each passed as one argument
        :type sbatch_options: list[str]

        :param beeond: BeeOND volume: ``True``/``"task"`` for a per-task volume,
            ``"workflow"``/``"workflow:<name>"`` for a per-workflow volume, a
            dict of :class:`dagon.beeond.BeeONDConfig` options, a config, or a
            :class:`dagon.beeond.BeeONDVolume`. ``None`` disables BeeOND.

        :param pre_stage: ``True`` stages the ``workflow://`` inputs on the
            submission host before ``sbatch``; ``False`` keeps stage-in inside
            the allocation; ``None`` (default) inherits the workflow setting.
            See ``docs/scheduler_prestaging.md``.
        :type pre_stage: bool or None
        """

        Batch.__init__(self, name, command, working_dir, globusendpoint=globusendpoint)
        self.comment = comment
        self.partition = partition
        self.ntasks = ntasks
        self.memory = memory
        self.time = time
        self.nodes = nodes
        self.ntasks_per_node = ntasks_per_node
        self.nodelist = nodelist
        self.sbatch_options = list(sbatch_options or [])
        self.beeond = beeond
        self._beeond_resolved: Any = None
        self._beeond_is_resolved = False
        self.pre_stage = validate_pre_stage(pre_stage)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create a Slurm task local or remote

            Keyword arguments:
            name -- task name
            command -- command to be executed
            comment -- comments as a string or array of strings
            partition -- partition where the task is going to be executed
            ntasks -- number of tasks to execute
            working_dir -- directory where the outputs will be placed
            time -- maximum runtime in format HH:MM:SS
            nodes -- number of nodes to request
            ntasks_per_node -- number of tasks per node
        """

        if "ip" in kwargs:
            return super().__new__(RemoteSlurm)
        else:
            return super().__new__(cls)

    def generate_command(self, script_name: str) -> str:

        """
        Generates the Slurm command including the partition and number of task parameters

        :param script_name: script to be executed
        :type script: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        options = []
        comments: List[str] = []
        if self.comment is not None:
            comments = [self.comment] if isinstance(self.comment, str) else list(self.comment)
            comments = [comment.strip() for comment in comments]
        beeond_config = self.beeond_task_config()
        if beeond_config is not None and beeond_config.comment.strip() not in comments:
            comments.append(beeond_config.comment.strip())
        options.extend("--comment=" + comment for comment in comments)
        if self.partition is not None:
            options.append("--partition=" + self.partition)
        if self.ntasks is not None:
            options.append("--ntasks=" + str(self.ntasks))
        if self.memory is not None:
            options.append("--mem=" + str(self.memory))
        if self.time is not None:
            options.append("--time=" + self.time)
        if self.nodes is not None:
            options.append("--nodes=" + str(self.nodes))
        if self.ntasks_per_node is not None:
            options.append("--ntasks-per-node=" + str(self.ntasks_per_node))
        if self.nodelist is not None:
            options.append("--nodelist=" + self.nodelist)
        if beeond_config is not None and beeond_config.persist and beeond_config.signal_grace:
            options.append("--signal=B:USR1@" + str(beeond_config.signal_grace))
        options.extend(self.sbatch_options)
        return join_command(["sbatch", *options, "-J", self.name, "-D", self.working_dir,
                             "-W", self.working_dir + "/.dagon/" + script_name])

    def on_execute(self, script: str, script_name: str) -> ExecutionResult:

        """
        Execute a script using slurm

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        if script_name == "context.sh":
            return self.run_on_submission_host(script, script_name)
        super(Batch, self).on_execute(script, script_name)
        volume = self.beeond_volume()
        if volume is not None:
            from dagon.beeond import LocalHost
            volume.ensure_started(LocalHost())
            return Batch.execute_command(join_command(volume.step_argv(
                self.name, self.working_dir, self.working_dir + "/.dagon/" + script_name, bash_executable())))
        command = self.generate_command(script_name)

        # Execute the bash command
        result = Batch.execute_command(command)
        return result


    # -- Scheduler-aware pre-staging (see dagon.prestage) -----------------

    def run_on_submission_host(self, script: str, script_name: str) -> ExecutionResult:
        """Write *script* to ``.dagon`` and run it with bash outside any allocation.

        This is the route ``context.sh`` has always taken; ``stage_in.sh`` takes
        the same one, so pre-staging never consumes scheduler resources.
        """
        super(Batch, self).on_execute(script, script_name)
        return Batch.execute_command(join_command((bash_executable(), self.working_dir + "/.dagon/" + script_name)))

    def run_stage_in(self, script: str) -> ExecutionResult:
        return self.run_on_submission_host(script, STAGE_SCRIPT_NAME)

    def write_stage_marker(self, content: str) -> None:
        """Write the marker through a temporary file and an atomic rename."""
        target = self.working_dir + "/.dagon/" + MARKER_NAME
        temporary = target + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)

    def read_scratch_file(self, filepath: str) -> Optional[str]:
        if not os.path.isfile(filepath):
            return None
        with open(filepath, encoding="utf-8") as stream:
            return stream.read()

    def requested_cores(self) -> Optional[int]:
        """Return ``ntasks``, or ``nodes * ntasks_per_node``, when requested."""
        if self.ntasks is not None:
            return int(self.ntasks)
        if self.nodes is not None and self.ntasks_per_node is not None:
            return int(self.nodes) * int(self.ntasks_per_node)
        return None

    def pre_stage_unsupported_reason(self) -> Optional[str]:
        reason = super().pre_stage_unsupported_reason()
        if reason is not None:
            return reason
        if self.beeond is not None and self.beeond is not False:
            return ("pre-staging is not supported together with BeeOND: BeeOND volumes exist only inside "
                    "a scheduler allocation (task scope) or a holder job (workflow scope)")
        return None

    # -- BeeOND support -------------------------------------------------

    def resolve_beeond(self) -> Any:
        """Resolve :attr:`beeond` against the workflow (cached).

        :return: ``None``, a task-scope :class:`dagon.beeond.BeeONDConfig`, or a
            workflow-scope :class:`dagon.beeond.BeeONDVolume`
        """
        if self.beeond is None or self.beeond is False:
            return None
        if not self._beeond_is_resolved:
            if self.workflow is None:
                raise RuntimeError("Task %s must belong to a workflow to resolve BeeOND" % self.name)
            from dagon.beeond import resolve
            self._beeond_resolved = resolve(self.beeond, self.workflow)
            self._beeond_is_resolved = True
        return self._beeond_resolved

    def beeond_task_config(self) -> Any:
        """Return the task-scope BeeOND configuration, if any."""
        from dagon.beeond import BeeONDConfig
        if self.beeond is None or self.beeond is False:
            return None
        if self.workflow is None:
            # Command generation without a workflow (for example in tests)
            # still honours explicit task-scope requests.
            if self.beeond is True or self.beeond == "task":
                return BeeONDConfig()
            if isinstance(self.beeond, BeeONDConfig) and self.beeond.scope == "task":
                return self.beeond
            if isinstance(self.beeond, dict) and self.beeond.get("scope", "task") == "task":
                return BeeONDConfig.from_mapping(self.beeond)
            return None
        resolved = self.resolve_beeond()
        return resolved if isinstance(resolved, BeeONDConfig) else None

    def beeond_volume(self) -> Any:
        """Return the workflow-scope BeeOND volume, if any."""
        from dagon.beeond import BeeONDVolume
        if self.beeond is None or self.beeond is False:
            return None
        resolved = self.resolve_beeond()
        return resolved if isinstance(resolved, BeeONDVolume) else None

    def beeond_persist_dir(self) -> Optional[str]:
        """Return the persistent directory of the task-scope volume."""
        config = self.beeond_task_config()
        if config is None or not config.persist or self.working_dir is None:
            return None
        target = config.persist_dir or "beeond"
        if os.path.isabs(target) or target.startswith("/"):
            return target
        return self.working_dir.rstrip("/") + "/" + target

    def launcher_prologue(self) -> str:
        from dagon.beeond import task_prologue
        volume = self.beeond_volume()
        if volume is not None:
            return volume.task_prologue()
        config = self.beeond_task_config()
        if config is None:
            return ""
        persist_dir = self.beeond_persist_dir() or ""
        return task_prologue(config, persist_dir, self.working_dir + "/.dagon")

    def launcher_epilogue(self) -> str:
        from dagon.beeond import task_epilogue
        volume = self.beeond_volume()
        if volume is not None:
            return volume.task_epilogue()
        config = self.beeond_task_config()
        return task_epilogue(config) if config is not None else ""

    def include_command(self, body: str) -> str:
        from dagon.beeond import background_command
        command = super().include_command(body)
        config = self.beeond_task_config()
        if config is not None and config.persist:
            # Run in the background so the persistence trap fires on signals.
            return background_command(command)
        return command

    def beeond_metadata(self) -> Optional[Dict[str, Any]]:
        """Return credential-free BeeOND provenance for this task."""
        volume = self.beeond_volume()
        if volume is not None:
            return volume.metadata()
        config = self.beeond_task_config()
        if config is None:
            return None
        return {"scope": "task", "comment": config.comment, "persist": config.persist,
                "persist_dir": self.beeond_persist_dir(), "verify": config.verify}

    def initialize_checkpoint(self) -> Dict[str, Any]:
        checkpoint = super().initialize_checkpoint()
        metadata = self.beeond_metadata()
        if metadata is not None:
            checkpoint["beeond"] = {key: metadata[key] for key in ("scope", "persist_dir")}
            if metadata["scope"] == "workflow":
                checkpoint["beeond"]["volume"] = metadata["volume"]
        return checkpoint

    def get_execution_metadata(self) -> Dict[str, Any]:
        metadata = dict(super().get_execution_metadata())
        try:
            beeond = self.beeond_metadata()
        except (RuntimeError, ValueError, TypeError):
            beeond = None
        if beeond is not None:
            metadata["beeond"] = beeond
        pre_stage = self.pre_stage_metadata()
        if pre_stage is not None:
            metadata["pre_stage"] = pre_stage
        return metadata

    def portable_command(self) -> str:
        """Define the emulated ``dagon_beeond_srun`` helper for BeeOND tasks."""
        command = super().portable_command()
        if self.beeond is None or self.beeond is False:
            return command
        from dagon.beeond import srun_emulation_script
        return srun_emulation_script() + command

    def portable_environment(self) -> Dict[str, str]:
        """Emulate the BeeOND mount with its persistent directory locally."""
        volume = self.beeond_volume()
        if volume is not None:
            mount = volume.persist_dir()
            os.makedirs(mount, exist_ok=True)
            return {"DAGON_BEEOND": mount, "DAGON_BEEOND_SCOPE": "workflow",
                    "DAGON_BEEOND_VOLUME": volume.name, "DAGON_BEEOND_PERSIST_DIR": mount,
                    "DAGON_BEEOND_NODES": "1"}
        config = self.beeond_task_config()
        if config is None:
            return {}
        mount = self.beeond_persist_dir() or self.working_dir.rstrip("/") + "/.dagon/beeond-emulated"
        os.makedirs(mount, exist_ok=True)
        environment = {"DAGON_BEEOND": mount, "DAGON_BEEOND_SCOPE": "task", "DAGON_BEEOND_NODES": "1"}
        if config.persist:
            environment["DAGON_BEEOND_PERSIST_DIR"] = mount
        return environment

    def as_json(self) -> Dict[str, Any]:
        json_task = super().as_json()
        if self.beeond is not None and self.beeond is not False:
            from dagon.beeond import BeeONDConfig, BeeONDVolume
            spec = self.beeond
            if isinstance(spec, BeeONDVolume):
                spec = "workflow:" + spec.name
            elif isinstance(spec, BeeONDConfig):
                spec = spec.as_dict()
            elif isinstance(spec, dict):
                spec = dict(spec)
            json_task["beeond"] = spec
        if self.pre_stage is not None:
            json_task["pre_stage"] = self.pre_stage
        return json_task


class RemoteSlurm(RemoteTask, Slurm):
    """
    ** Represent a task that runs on a remote slurm deployment **
    """

    def __init__(
            self,
            name: str,
            command: str,
            partition: Optional[str] = None,
            ntasks: Optional[int] = None,
            memory: Optional[int] = None,
            working_dir: Optional[str] = None,
            ssh_username: Optional[str] = None,
            keypath: Optional[str] = None,
            ip: Optional[str] = None,
            globusendpoint: Optional[str] = None,
            comment: Optional[Union[str, List[str]]] = None,
            time: Optional[str] = None,
            nodes: Optional[int] = None,
            ntasks_per_node: Optional[int] = None,
            nodelist: Optional[str] = None,
            sbatch_options: Optional[List[str]] = None,
            beeond: Any = None,
            ssh_port: int = 22,
            pre_stage: Optional[bool] = None) -> None:
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed
        :type command: str

        :param partition: partition where the task will be executed
        :type partition: str

        :param ntasks: number of parallel tasks to be executed
        :type ntasks: int

        :param working_dir: path to the task's working directory
        :type working_dir: str

        :param globusendpoint: Globus endpoint ID
        :type globusendpoint: str

        :param ssh_username: UNIX username on the remote
        :type endpoint: str

        :param keypath: Path to the public key
        :type keypath: str

        :param ip: IP address to connect to the remote machine
        :type ip: str

        :param comment, time, nodes, ntasks_per_node, nodelist, sbatch_options, beeond:
            same meaning as in :class:`Slurm`

        :param ssh_port: SSH port of the remote login node (default: 22)
        :type ssh_port: int

        :param pre_stage: same meaning as in :class:`Slurm`; stage-in runs on the
            remote login (submission) host over SSH
        :type pre_stage: bool or None

        """
        Slurm.__init__(self, name, command, comment=comment, working_dir=working_dir, partition=partition,
                       ntasks=ntasks, memory=memory, time=time, nodes=nodes, ntasks_per_node=ntasks_per_node,
                       globusendpoint=globusendpoint, nodelist=nodelist, sbatch_options=sbatch_options,
                       beeond=beeond, pre_stage=pre_stage)
        RemoteTask.__init__(
            self,
            name,
            command,
            ssh_username=ssh_username,
            keypath=keypath,
            ip=ip,
            ssh_port=ssh_port,
            working_dir=working_dir,
            globusendpoint=globusendpoint,
        )

    def on_execute(self, script: str, script_name: str) -> ExecutionResult:
        """
        Execute a script using slurm

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """

        if script_name == "context.sh":
            return self.run_on_submission_host(script, script_name)
        RemoteTask.on_execute(self, script, script_name)

        volume = self.beeond_volume()
        if volume is not None:
            from dagon.beeond import SSHHost
            volume.ensure_started(SSHHost(self.ssh_connection))
            return self.ssh_connection.execute_command(join_command(volume.step_argv(
                self.name, self.working_dir, self.working_dir + "/.dagon/" + script_name, "bash")))

        command = self.generate_command(script_name)
        # Execute the bash command
        result = self.ssh_connection.execute_command(command)
        return result

    def run_on_submission_host(self, script: str, script_name: str) -> ExecutionResult:
        """Write *script* on the remote login host and run it there with bash over SSH."""
        RemoteTask.on_execute(self, script, script_name)
        return self.ssh_connection.execute_command(
            join_command(("bash", self.working_dir + "/.dagon/" + script_name)))

    def write_stage_marker(self, content: str) -> None:
        """Write the marker on the remote host through a temporary file and ``mv``."""
        target = self.working_dir + "/.dagon/" + MARKER_NAME
        temporary = target + ".tmp"
        self.ssh_connection.create_file(temporary, content)
        result = self.ssh_connection.execute_command(join_command(("mv", "-f", temporary, target)))
        if result.get("code"):
            raise IOError("cannot move the stage-in marker into place: %s" % result.get("message"))

    def read_scratch_file(self, filepath: str) -> Optional[str]:
        result = self.ssh_connection.execute_command(join_command(("cat", filepath)))
        return None if result.get("code") else result.get("output")
