import logging
import re
import shutil
import uuid
import glob
import os
import subprocess
import shlex
from json import loads, dumps
from threading import Thread
from threading import Semaphore
from os import makedirs, path, chmod
from time import time, sleep
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dagon.ftp_publisher import FTP_API
import dagon
from dagon.shell import quote
from dagon.platform_support import bash_executable, launcher_environment, shell_path
from dagon.prestage import (
    ALLOCATION_STARTED_NAME, COMPUTE_RECORD_NAME, DESTINATION_IDENTITY_NAME, IDENTITY_NAME, INTEGRITY_CONTENT, LOCK_BUSY_EXIT, INTEGRITY_EXISTENCE, MARKER_NAME,
    PRE_STAGE_POLICY_VERSION, PreparedTask, PreStageConfigurationError, ScheduledExecutionError,
    SchedulerSubmissionError, StageInFailedError, StageInput, TaskPhase, compute_record_problem,
    estimated_core_hours_saved,
    identity_digest, identity_script, marker_document, utc_now, validate_pre_stage, validate_reference_path,
)

# ``sbatch --parsable`` prints ``<job id>`` or ``<job id>;<cluster>`` on its first line.
_PARSABLE_JOB_ID = re.compile(r"^(\d+(?:_\d+)?)(?:;\S+)?$")


def parsable_job_id(output: Any) -> Optional[str]:
    """Return the job identifier printed by ``sbatch --parsable``, or ``None``.

    Only the first non-empty output line is inspected, and only a bare numeric
    identifier (optionally followed by ``;<cluster>``) is accepted, so display
    text such as ``Submitted batch job 42`` or an error message never counts as
    evidence that the scheduler accepted the job.
    """
    for line in str(output or "").splitlines():
        line = line.strip()
        if line:
            match = _PARSABLE_JOB_ID.match(line)
            return match.group(1) if match else None
    return None


class TaskType(Enum):
    """
    Enum used to represent the main types tasks supported by dagon,
    remote tasks are supported by the RemoteClass but it should not be
    explicitly instantiate

    :cvar CHECKPOINT: Explicit checkpoint enabling saving and resuming the workflow run
    :cvar BATCH: Regular Batch task (local or remote)
    :cvar SLURM: Task executed using Slurm (local or remote)
    :cvar CLOUD: Task executed in a cloud instance (ec2, digital ocean and google cloud  tested with libcloud)
    :cvar DOCKER: Task executed on a docker container (local or remote)
    :cvar APPTAINER: Task executed in an Apptainer container (HPC environments)
    """

    CHECKPOINT = "checkpoint"
    BATCH = "batch"
    SLURM = "slurm"
    CLOUD = "cloud"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    APPTAINER = "apptainer"
    NOMAD = "nomad"
    LLM = "llm"
    NATIVE = "native"
    WEB = "web"
    FAAS = "faas"
    IOT = "iot"


# Different types os tasks and their module and class name
ExecutionResult = Dict[str, Any]
TaskInfo = Dict[str, Any]
TaskTypeSpec = Tuple[str, str]


tasks_types: Dict[TaskType, TaskTypeSpec] = {
    TaskType.CHECKPOINT: ("dagon.checkpoint", "Checkpoint"),
    TaskType.BATCH: ("dagon.batch", "Batch"),
    TaskType.CLOUD: ("dagon.remote", "CloudTask"),
    TaskType.DOCKER: ("dagon.docker_task", "DockerTask"),
    TaskType.SLURM: ("dagon.batch", "Slurm"),
    TaskType.KUBERNETES: ("dagon.kubernetes_task", "KubernetesTask"),
    TaskType.APPTAINER: ("dagon.apptainer_task", "ApptainerTask"),
    TaskType.NOMAD: ("dagon.nomad_task", "NomadTask"),
    TaskType.LLM: ("dagon.llm", "LLMTask"),
    TaskType.NATIVE: ("dagon.native", "NativeTask"),
    TaskType.WEB: ("dagon.web", "WebTask"),
    TaskType.FAAS: ("dagon.faas", "FaaSTask"),
    TaskType.IOT: ("dagon.iot", "IoTTask"),
}


class DagonTask(object):
    """
    Create the instance for Dagon Tasks
    """

    def __new__(cls, class_type: TaskType, *args: Any, **kwargs: Any) -> Any:
        """
        Choose the task type and returns an instance of the task type class

        :param class_type: type of the task (:class:`Types`)
        :type class_type: :class:`TaskType`

        :param args: arguments of the task
        :type name: list[]

        :param kwargs: keyboard arguments of the task
        :type name: dict()

        :return: subclass instance of :class:`Task`
        :rtype: cls
        """

        from importlib import import_module
        task_class = tasks_types[class_type]
        module = import_module(task_class[0])
        class_ = getattr(module, task_class[1])
        return class_(*args, **kwargs)


class Task(Thread):
    task_type = None
    # Optional BeeOND volume specification (see dagon.beeond); only the
    # Slurm task family currently accepts one.
    beeond: Any = None
    # Declared scheduler-aware pre-staging override (see dagon.prestage):
    # ``None`` inherits ``Workflow.pre_stage``.  Class attributes (rather than
    # ``__init__`` assignments) survive the repeated ``Task.__init__`` calls of
    # multiply-inherited backends such as RemoteSlurm.
    pre_stage: Optional[bool] = None
    # Backends whose scheduler submission can be separated from stage-in set
    # this to True and implement the submission-host helpers.
    pre_stage_capable: bool = False
    """
    **Represents a task executed by DagOn**

    It can be executed on local machine, cloud instance, cluster or in a docker container

    :ivar name: unique name of the class
    :vartype name: str

    :ivar command: command to be executed
    :vartype command: str

    :ivar working_dir: path to the folder or directory where the task is going to be executed
    :vartype working_dir: str

    :ivar nexts: tasks with dependencies to this tasks, that will be executed when this task ends
    :vartype nexts: list[]

    :ivar prevs: tasks that has to be executed before of this task (dependencies to be resolved)
    :vartype prevs: list[]

    :ivar reference_count: number of references to this task
    :vartype reference_count: int

    :ivar remove_scratch_dir: True if the sratch directory has to be removed after the execution of this task
    :vartype remove_scratch_dir: bool

    :ivar running: True if the task is in execution
    :vartype running: bool

    :ivar workflow: workflow related to this task
    :vartype workflow: :class:`dagon.Workflow`

    :ivar status: actual :class:`dagon.Status` of the task
    :vartype status: :class:`dagon.Status`

    :ivar info: information of the enviroment where this task is going to be executed
    :vartype info: dict(str, object)

    """

    def __init__(
            self,
            name: str,
            command: str,
            working_dir: Optional[str] = None,
            transversal_workflow: Optional[str] = None,
            globusendpoint: Optional[str] = None):
        """
        :param name: name of the task
        :type name: str

        :param command: command to be executed by the task
        :type command: str

        :param working_dir: path to the directory where the task is be executed
        :type working_dir: str

        :param endpoint: UUID of the Globus Endpoint to store the data.
        :type endpoint: str

        """
        Thread.__init__(self)
        self.ssh_connection = None
        self.name = name
        self.nexts: List[Any] = []
        self.prevs: List[Any] = []
        self.reference_count = 0
        self.remove_scratch_dir = False
        self.ip = None
        self.running = False
        self.workflow = None
        self.set_status(dagon.Status.READY)
        self.working_dir = shell_path(working_dir) if working_dir else working_dir
        self.command = command
        self.info: Optional[Dict[str, Any]] = None
        self.dag_tps = None
        self.transversal_workflow = transversal_workflow
        self.workflows = None
        self.data_mover = None
        self.stager_mover = None
        self.mode = "sequential"
        self.globusendpoint = globusendpoint
        self.new_tasks = []
        self.completetion_time = 0
        self.logger = logging.getLogger()
        # Declarations are inert unless the owning workflow enables FAIR.
        self.fair_inputs = []
        self.fair_outputs = []
        self.fair_annotations = {}
        self.fair_checkpoint_reused = False
        # Scheduler-aware pre-staging state (only used when it is effective).
        self.pre_stage_phase: Optional[TaskPhase] = None
        self.pre_stage_metrics: Dict[str, Any] = {}
        self.prepared_task: Optional[PreparedTask] = None
        # True only while a pre-staged compute launcher is being submitted.
        self.pre_stage_submission = False
        self.failure_phase: Optional[str] = None


    def declare_inputs(self, *artifacts: Any) -> "Task":
        """Attach intentional input artifact metadata and return this task."""
        self.fair_inputs.extend(artifacts)
        return self

    def declare_outputs(self, *artifacts: Any) -> "Task":
        """Attach intentional output artifact metadata and return this task."""
        self.fair_outputs.extend(artifacts)
        return self

    def annotate(self, **metadata: Any) -> "Task":
        """Attach task-level FAIR annotations and return this task."""
        self.fair_annotations.update(metadata)
        return self

    def get_execution_metadata(self) -> Dict[str, Any]:
        """Return sanitized backend metadata for optional provenance recorders."""
        return {}

    # -- Scheduler-aware pre-staging -------------------------------------

    def pre_stage_unsupported_reason(self) -> Optional[str]:
        """Return why this task cannot pre-stage, or ``None`` when it can.

        Eligibility is a backend capability (:attr:`pre_stage_capable`) plus
        per-task conditions that backends may extend, never the task type name.
        """
        if not self.pre_stage_capable:
            return ("%s tasks do not support scheduler-aware pre-staging; "
                    "only Slurm and RemoteSlurm tasks do" % type(self).__name__)
        if self.mode == "parallel":
            return "pre-staging is not supported for tasks in parallel mode"
        stager_mover = self.stager_mover
        if stager_mover is not None and \
                dagon.stager.base.StagerMover(stager_mover) == dagon.stager.base.StagerMover.SLURM:
            return ("pre-staging is not supported with StagerMover.SLURM: its copy jobs are scheduler "
                    "submissions, and pre-staging must not request scheduler resources before stage-in "
                    "has succeeded")
        return self._shared_working_dir_reason(self.workflow)

    def _shared_working_dir_reason(self, workflow: Any) -> Optional[str]:
        other = self.shared_working_dir_task(workflow)
        if other is None:
            return None
        return ("pre-staging is not supported for a working directory shared with task %s: stage-in "
                "replaces the staged inputs, marker, and records in that directory" % other.name)

    def shared_working_dir_task(self, workflow: Any = None) -> Optional["Task"]:
        """Return another task of the workflow with the same fixed working directory, if any.

        Directories are compared on the same host (``ip``) after normalisation.
        Generated scratch directories are unique per task, so only explicit
        ``working_dir`` values can collide.
        """
        workflow = workflow if workflow is not None else self.workflow
        if workflow is None or not self.working_dir:
            return None
        mine = (getattr(self, "ip", None), path.normpath(str(self.working_dir)))
        for task in getattr(workflow, "tasks", []):
            if task is self or not getattr(task, "working_dir", None):
                continue
            if (getattr(task, "ip", None), path.normpath(str(task.working_dir))) == mine:
                return task
        return None

    def validate_pre_stage_declaration(self, workflow: Any = None) -> None:
        """Validate the declared override; reject an explicit request that cannot be honoured.

        :raises PreStageConfigurationError: for a non-boolean value, or for
            ``pre_stage=True`` on a task that cannot pre-stage
        """
        declared = validate_pre_stage(self.pre_stage)
        if declared is True:
            reason = self.pre_stage_unsupported_reason()
            if reason is None and workflow is not None and workflow is not self.workflow:
                # Called by Workflow.add_task before the task joins *workflow*.
                reason = self._shared_working_dir_reason(workflow)
            if reason is not None:
                raise PreStageConfigurationError("Task %s: %s" % (self.name, reason))

    def resolve_pre_stage(self) -> bool:
        """Return whether pre-staging is effective for this task.

        ``effective = task.pre_stage if task.pre_stage is not None else workflow.pre_stage``,
        restricted to eligible tasks.  An explicit ``pre_stage=True`` on an
        ineligible task raises; an inherited workflow default keeps the legacy
        lifecycle for ineligible tasks and logs why.  The declared override is
        never modified.

        :raises PreStageConfigurationError: see :meth:`validate_pre_stage_declaration`
        """
        self.validate_pre_stage_declaration()
        declared = self.pre_stage
        if declared is False:
            return False
        default = bool(getattr(self.workflow, "pre_stage", False)) if self.workflow is not None else False
        if not (declared if declared is not None else default):
            return False
        reason = self.pre_stage_unsupported_reason()
        if reason is None:
            return True
        if self.pre_stage_capable and self.workflow is not None:
            # Only scheduler tasks are expected to honour the workflow default;
            # tell users when an eligible backend falls back for a task reason.
            self.workflow.logger.warning(
                "%s: workflow pre_stage=True not applied, using the legacy lifecycle: %s", self.name, reason)
        return False

    def pre_stage_requested(self) -> bool:
        """Return whether pre-staging is configured at all for this task (effective or not)."""
        workflow_default = bool(getattr(self.workflow, "pre_stage", False)) if self.workflow is not None else False
        return self.pre_stage is not None or (workflow_default and self.pre_stage_capable)

    def run_stage_in(self, script: str) -> ExecutionResult:
        """Write and run the stage-in script on the submission host (backend specific)."""
        raise PreStageConfigurationError("%s cannot run a stage-in script" % type(self).__name__)

    def write_stage_marker(self, content: str) -> None:
        """Atomically write the stage-in completion marker (backend specific)."""
        raise PreStageConfigurationError("%s cannot write a stage-in marker" % type(self).__name__)

    def read_scratch_file(self, filepath: str) -> Optional[str]:
        """Return the content of a scratch file, or ``None`` (backend specific)."""
        return None

    def release_stage_lock(self, token: str) -> None:
        """Remove the stage-in lock if *token* owns it (backend specific)."""
        return None

    def run_identity_check(self, script: str) -> ExecutionResult:
        """Run a read-only identity script on the submission host (backend specific).

        Used only to validate a pre-staged checkpoint before it is reused.
        """
        raise PreStageConfigurationError("%s cannot validate pre-staged inputs" % type(self).__name__)

    def requested_cores(self) -> Optional[int]:
        """Return the number of cores requested from the scheduler, when known."""
        return None

    def _set_pre_stage_phase(self, phase: TaskPhase) -> None:
        self.pre_stage_phase = phase
        self.pre_stage_metrics["phase"] = phase.value
        if self.workflow is not None:
            self.workflow.logger.debug("%s: pre-stage phase %s", self.name, phase.value)

    def execute_pre_staged(self, key: str) -> None:
        """Run the scheduler-aware pre-staging lifecycle.

        ``context -> stage plan -> stage_in.sh on the submission host -> verify
        -> marker -> compute-only launcher -> scheduler``.  The scheduler is
        never contacted when stage-in fails or its success cannot be confirmed.
        """
        metrics = self.pre_stage_metrics
        metrics.clear()
        metrics.update({"pre_stage_effective": True, "policy_version": PRE_STAGE_POLICY_VERSION, "allocation_wait_seconds": None,
                        "execution_seconds": None})
        checkpoint = self.workflow.checkpoints[key]
        checkpoint["pre_stage"] = {"effective": True, "staged": False}
        self._set_pre_stage_phase(TaskPhase.PREPARING)

        # The staging hooks surround context discovery, planning, and the
        # actual transfer (unlike the legacy lifecycle, where the transfer
        # happens later, inside the scheduler job).
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            try:
                prepared = self.prepare_task(self.command, strict_staging=True)
            except Exception as exc:
                self.failure_phase = "staging"
                self._set_pre_stage_phase(TaskPhase.FAILED)
                raise StageInFailedError("%s: stage-in planning failed: %s" % (self.name, exc)) from exc
            self.prepared_task = prepared
            metrics["inputs"] = len(prepared.inputs)
            metrics["inputs_content_verified"] = sum(
                1 for item in prepared.inputs if item.integrity == INTEGRITY_CONTENT)
            # The stage-in lock is held from stage-in until the scheduler job
            # has returned, so no other run can replace these inputs meanwhile.
            lock_token = uuid.uuid4().hex
            try:
                self._run_stage_in(prepared, key, lock_token)
            except BaseException:
                self._release_stage_lock(lock_token)
                raise
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        try:
            self._submit_pre_staged(prepared, checkpoint)
        finally:
            self._release_stage_lock(lock_token)

    def _release_stage_lock(self, token: str) -> None:
        try:
            self.release_stage_lock(token)
        except Exception as exc:  # never hide the task outcome behind a cleanup failure
            self.workflow.logger.warning("%s: could not release the stage-in lock: %s", self.name, exc)

    def _submit_pre_staged(self, prepared: PreparedTask, checkpoint: Dict[str, Any]) -> None:
        """Submit the compute-only launcher and classify the outcome from the job identifier."""
        metrics = self.pre_stage_metrics
        launcher_script = self.post_process_command(prepared.compute_launcher())
        self.workflow._fire_event("on_task_execute_start", self)

        self._set_pre_stage_phase(TaskPhase.SUBMITTED)
        metrics["submission_started_at"] = utc_now()
        submitted = time()
        # Submit with ``--parsable`` so acceptance is judged from the job
        # identifier, not from display text (see :func:`parsable_job_id`).
        self.pre_stage_submission = True
        try:
            self.result = self.on_execute(launcher_script, "launcher.sh")
        finally:
            self.pre_stage_submission = False
        returned = time()
        self.completetion_time = returned - submitted
        metrics["scheduler_returned_at"] = utc_now()
        # sbatch -W returns when the job ends: this includes queue time.
        metrics["scheduler_wall_seconds"] = round(self.completetion_time, 3)
        self.workflow.logger.debug("%s Completed in %s seconds ---" % (self.name, self.completetion_time))
        self._record_allocation_timing(submitted, returned)
        job_id = parsable_job_id(self.result.get("output"))
        metrics["scheduler_job_id"] = job_id
        if not self.result['code'] and job_id is None:
            # A successful exit is not evidence that the scheduler accepted and
            # ran the job: without a job identifier the outcome is unconfirmed.
            checkpoint["code"] = 1
            self._set_pre_stage_phase(TaskPhase.FAILED)
            self.failure_phase = "submission"
            raise SchedulerSubmissionError(
                "%s: the scheduler returned success without a job identifier (sbatch --parsable printed "
                "none), so acceptance of the job cannot be confirmed (staged inputs kept)" % self.name)
        checkpoint["code"] = self.result['code']
        if self.result['code']:
            self._set_pre_stage_phase(TaskPhase.FAILED)
            if job_id is not None:
                self.failure_phase = "execution"
                raise ScheduledExecutionError(
                    "%s: scheduler job %s failed after pre-staging; see its output (by default "
                    "slurm-%s.out in the working directory)" % (self.name, job_id, job_id))
            self.failure_phase = "submission"
            raise SchedulerSubmissionError(
                "%s: scheduler submission failed after successful pre-staging (staged inputs kept): %s"
                % (self.name, self.result.get('message')))
        # sbatch -W also exits 0 for a job cancelled before it started: require
        # the record that the compute launcher writes when it ends.
        problem = self._compute_completion_problem(job_id)
        if problem is not None:
            checkpoint["code"] = 1
            self._set_pre_stage_phase(TaskPhase.FAILED)
            self.failure_phase = "execution"
            raise ScheduledExecutionError(
                "%s: scheduler job %s returned success, but %s; the task is not treated as completed "
                "(for example, the job was cancelled before it started)" % (self.name, job_id, problem))
        metrics["compute_completion_confirmed"] = True
        self._set_pre_stage_phase(TaskPhase.COMPLETED)

    def _compute_completion_problem(self, job_id: str, attempts: int = 5) -> Optional[str]:
        """Return why the job's completion record does not confirm success, or ``None``.

        A missing record is read again a few times, one second apart, because a
        shared file system may show a file written on a compute node with a delay.
        """
        path = self.working_dir + "/.dagon/" + COMPUTE_RECORD_NAME
        problem = None
        for attempt in range(attempts):
            record = self.read_scratch_file(path)
            problem = compute_record_problem(record, job_id)
            if record is not None and record.strip():
                return problem
            if attempt + 1 < attempts:
                sleep(1)
        return problem

    def plan_pre_staged_dry_run(self) -> PreparedTask:
        """Plan a pre-staged task without any side effect (dry run).

        The ``workflow://`` references are parsed and checked
        (:func:`dagon.prestage.validate_reference_path`), and the planned order
        is logged.  No scratch directory is created and nothing runs on the
        submission host, so the data mover, which context discovery would
        choose, is not resolved, and integrity levels are not decided.
        Directories that do not exist yet are shown as placeholders.
        """
        metrics = self.pre_stage_metrics
        metrics.clear()
        metrics.update({"pre_stage_effective": True, "policy_version": PRE_STAGE_POLICY_VERSION,
                        "dry_run": True})
        self._set_pre_stage_phase(TaskPhase.PREPARING)
        working_dir = self.working_dir or "<scratch of %s>" % self.name
        inputs: List[StageInput] = []
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            command = self.command
            pos = 0
            while True:
                pos1 = command.find(dagon.Workflow.SCHEMA, pos)
                if pos1 == -1:
                    break
                pos2 = command.find(" ", pos1)
                if pos2 == -1:
                    pos2 = len(command)
                arg = command[pos1:pos2].replace(dagon.Workflow.SCHEMA, "")
                elements = arg.split("/")
                workflow_name = elements[0] or self.workflow.name
                task_name = elements[1] if len(elements) > 1 else ""
                local_path = "/" + "/".join(elements[2:])
                try:
                    validate_reference_path(workflow_name, task_name, local_path)
                except PreStageConfigurationError as exc:
                    self.failure_phase = "staging"
                    self._set_pre_stage_phase(TaskPhase.FAILED)
                    raise StageInFailedError("%s: stage-in planning failed: %s" % (self.name, exc)) from exc
                producer = self.workflow.find_task_by_name(workflow_name, task_name)
                source_root = (producer.working_dir if producer is not None and producer.working_dir
                               else "<scratch of %s>" % task_name)
                destination = working_dir + "/.dagon/inputs/" + workflow_name + "/" + task_name
                inputs.append(StageInput(reference=dagon.Workflow.SCHEMA + arg, workflow=workflow_name,
                                         task=task_name, local_path=local_path,
                                         source=source_root + "/" + local_path,
                                         destination=destination + "/" + local_path))
                pos = pos2
            prepared = PreparedTask(working_dir=working_dir, header="", prologue="", stage_blocks=[], invoke="",
                                    resolved_command=command, inputs=inputs)
            self.prepared_task = prepared
            metrics["inputs"] = len(inputs)
            self.workflow.logger.info("%s: dry run, planned pre-staged order: %s",
                                      self.name, " -> ".join(prepared.planned_order()))
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        self.workflow._fire_event("on_task_execute_start", self)
        return prepared

    def _run_stage_in(self, prepared: PreparedTask, key: str, lock_token: Optional[str] = None) -> None:
        metrics = self.pre_stage_metrics
        self._set_pre_stage_phase(TaskPhase.STAGING)
        started_at = utc_now()
        metrics["staging_started_at"] = started_at
        started = time()
        try:
            result = self.run_stage_in(prepared.stage_in_script(lock_token))
        except Exception as exc:
            result = {"code": 1, "message": str(exc), "output": ""}
        staging_seconds = time() - started
        finished_at = utc_now()
        metrics.update({"staging_finished_at": finished_at, "staging_seconds": round(staging_seconds, 3)})
        self.workflow.checkpoints[key]["pre_stage"]["stage_in_code"] = result.get("code")
        if result.get("code"):
            self.failure_phase = "staging"
            self._set_pre_stage_phase(TaskPhase.FAILED)
            if result.get("code") == LOCK_BUSY_EXIT:
                metrics["stage_in_lock_busy"] = True
            raise StageInFailedError(
                "%s: stage-in failed on the submission host; no scheduler job was submitted: %s"
                % (self.name, (result.get("message") or result.get("output") or "").strip()))
        try:
            listing = self.read_scratch_file(self.working_dir + "/.dagon/" + IDENTITY_NAME)
            if listing is None:
                raise IOError("the stage-in identity record .dagon/%s is missing" % IDENTITY_NAME)
            source_identity = identity_digest(listing)
            staged = self.read_scratch_file(self.working_dir + "/.dagon/" + DESTINATION_IDENTITY_NAME)
            if staged is None:
                raise IOError("the staged-input record .dagon/%s is missing" % DESTINATION_IDENTITY_NAME)
            self.write_stage_marker(marker_document(self, prepared, started_at, finished_at, staging_seconds,
                                                    source_identity, identity_digest(staged)))
        except Exception as exc:
            self.failure_phase = "staging"
            self._set_pre_stage_phase(TaskPhase.FAILED)
            raise StageInFailedError("%s: could not record stage-in completion; no scheduler job was "
                                     "submitted: %s" % (self.name, exc)) from exc
        # The checkpoint keeps what is needed to re-verify the inputs before a
        # completed result is reused (see :meth:`validate_pre_staged_checkpoint`).
        self.workflow.checkpoints[key]["pre_stage"].update(
            {"staged": True, "marker": ".dagon/" + MARKER_NAME,
             "policy_version": PRE_STAGE_POLICY_VERSION,
             "source_identity_sha256": source_identity,
             "inputs": [{"reference": item.reference, "workflow": item.workflow, "task": item.task,
                         "local_path": item.local_path, "integrity": item.integrity}
                        for item in prepared.inputs]})
        cores = self.requested_cores()
        metrics["requested_cores"] = cores
        metrics["estimated_allocated_core_hours_saved"] = estimated_core_hours_saved(cores, staging_seconds)
        self._set_pre_stage_phase(TaskPhase.STAGED)

    def _record_allocation_timing(self, submitted: float, returned: float) -> None:
        """Derive queue and execution time from the launcher's start stamp, when available.

        The stamp is written by the compute node; clock skew between it and the
        submission host makes these values approximate.
        """
        try:
            content = self.read_scratch_file(self.working_dir + "/.dagon/" + ALLOCATION_STARTED_NAME)
            started = float((content or "").strip())
        except (TypeError, ValueError, OSError):
            return
        # ``date +%s`` has whole-second precision; tolerate one second either side.
        if submitted - 1 <= started <= returned + 1:
            started = min(max(started, submitted), returned)
            self.pre_stage_metrics["allocation_wait_seconds"] = round(max(started - submitted, 0.0), 3)
            self.pre_stage_metrics["execution_seconds"] = round(max(returned - started, 0.0), 3)
            self.pre_stage_metrics["allocation_timing_resolution_seconds"] = 1

    def pre_stage_metadata(self) -> Optional[Dict[str, Any]]:
        """Return credential- and path-free pre-staging provenance, if configured."""
        return dict(self.pre_stage_metrics) if self.pre_stage_metrics else None

    def checkpoint_key(self) -> str:
        """Return the stable checkpoint key used by every task backend."""
        if self.workflow is None:
            raise RuntimeError("Task must belong to a workflow before checkpoint access")
        return self.workflow.name + "." + self.name

    def reuse_checkpoint(self) -> bool:
        """Reuse a successful, still-accessible checkpoint working directory.

        Local and structured task implementations share this contract. Remote
        command tasks additionally use their backend ``exists_dir`` check.
        """
        checkpoint = self.workflow.checkpoints.get(self.checkpoint_key(), {})
        if checkpoint.get("code") != 0:
            return False
        working_dir = checkpoint.get("working_dir")
        if not isinstance(working_dir, str) or not working_dir:
            return False
        accessible = path.isdir(working_dir)
        if not accessible and self.ssh_connection is not None:
            accessible = bool(self.exists_dir(working_dir))
        if not accessible:
            return False
        pre_stage = checkpoint.get("pre_stage")
        if isinstance(pre_stage, dict) and pre_stage.get("effective"):
            reason = self.validate_pre_staged_checkpoint(pre_stage)
            if reason is not None:
                self.workflow.logger.warning(
                    "%s: completed pre-staged checkpoint not reused, the task runs again: %s", self.name, reason)
                return False
        self.working_dir = working_dir
        self.fair_checkpoint_reused = True
        return True

    def validate_pre_staged_checkpoint(self, record: Dict[str, Any]) -> Optional[str]:
        """Return why a completed pre-staged checkpoint must not be reused, or ``None``.

        A completed checkpoint is reused only when the content of every input
        can be re-read on the submission host and still matches the identity
        recorded after the successful stage-in.  Inputs are resolved against the
        producers' *current* scratch directories, so a producer that ran again
        with different output invalidates the consumer.  Inputs whose source
        was not readable on the submission host (for example ``SCP``) cannot be
        re-verified, so such a checkpoint is never reused.  The stage-in
        marker is never consulted: it is provenance, not a skip token.
        """
        if record.get("policy_version") != PRE_STAGE_POLICY_VERSION or "source_identity_sha256" not in record:
            return "the checkpoint has no input identity for this pre-staging policy version"
        entries = record.get("inputs")
        if not isinstance(entries, list):
            return "the checkpoint has no input manifest"
        inputs = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("integrity") != INTEGRITY_CONTENT:
                return "input %s cannot be re-verified on the submission host" % (
                    entry.get("reference") if isinstance(entry, dict) else entry)
            producer = self.workflow.find_task_by_name(entry.get("workflow"), entry.get("task"))
            if producer is None or not producer.working_dir:
                return "the producer of %s is not available" % entry.get("reference")
            inputs.append(StageInput(
                reference=str(entry.get("reference")), workflow=str(entry.get("workflow")),
                task=str(entry.get("task")), local_path=str(entry.get("local_path")),
                source=str(producer.working_dir) + "/" + str(entry.get("local_path")),
                destination="", integrity=INTEGRITY_CONTENT))
        if not inputs:
            return None
        try:
            result = self.run_identity_check(identity_script(inputs))
        except Exception as exc:
            return "the inputs could not be re-verified: %s" % exc
        if result.get("code"):
            return "the inputs could not be re-verified: %s" % (result.get("message") or "").strip()
        if identity_digest(result.get("output") or "") != record.get("source_identity_sha256"):
            return "the content of at least one input changed since the checkpoint was written"
        return None

    def initialize_checkpoint(self) -> Dict[str, Any]:
        """Create the common checkpoint record after a working directory exists."""
        checkpoint = {
            "working_dir": self.working_dir,
            "workflow": self.workflow.name,
            "name": self.name,
        }
        self.workflow.checkpoints[self.checkpoint_key()] = checkpoint
        return checkpoint

    def portable_command(self) -> str:
        """Resolve workflow references to local producer artifacts."""
        command = self.command
        checkpoint_task = type(self).__name__ in {"Checkpoint", "RemoteCheckpoint"}
        if checkpoint_task:
            command = command.split("checkpoint.sh ", 1)[-1]
        for previous in self.prevs:
            for prefix in ("workflow:///%s/" % previous.name,
                           "workflow://%s/%s/" % (self.workflow.name, previous.name)):
                while prefix in command:
                    start = command.index(prefix)
                    end = start + len(prefix)
                    while end < len(command) and not command[end].isspace() and command[end] not in "'\";|)&":
                        end += 1
                    relative = command[start + len(prefix):end]
                    command = command[:start] + shell_path(os.path.join(previous.working_dir, relative)) + command[end:]
        return "test -f " + " ".join(shlex.quote(item) for item in command.split()) if checkpoint_task else command

    def execute_portable(self) -> None:
        """Execute a command task locally without contacting its configured backend."""
        key = self.checkpoint_key()
        if self.reuse_checkpoint():
            self.remove_reference_workflow()
            return
        self.remove_scratch_dir = self.workflow.get_remove_dir_op()
        if self.working_dir is None:
            self.working_dir = shell_path(os.path.join(self.workflow.get_scratch_dir_base(), self.get_scratch_name()))
        os.makedirs(os.path.join(self.working_dir, ".dagon"), exist_ok=True)
        self.initialize_checkpoint()
        self.workflow._fire_event("on_task_execute_start", self)
        environment = launcher_environment()
        extra_environment = self.portable_environment()
        if extra_environment:
            environment = dict(environment if environment is not None else os.environ)
            environment.update(extra_environment)
        completed = subprocess.run([bash_executable(), "-c", self.portable_command()],
                                   cwd=self.working_dir, text=True, capture_output=True,
                                   env=environment)
        self.result = {"code": completed.returncode, "message": completed.stderr,
                       "output": completed.stdout}
        self.workflow.checkpoints[key]["code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError("Portable task failed: " + completed.stderr)
        self.remove_reference_workflow()

    def get_endpoint(self) -> Optional[str]:
        return self.globusendpoint

    def set_endpoint(self, globusendpoint: Optional[str]) -> None:
        self.globusendpoint = globusendpoint

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def get_mode(self) -> str:
        return self.mode

    def set_data_mover(self, data_mover: Any) -> None:
        """
        Change the mode of the stager. The information is used by
        :class:`dagon.Stager` to decide the mode (COPY/LINK)

        :param data_mover: mode of the stager
        :type info: class:`dagon.DataMover`
        """
        self.data_mover = data_mover

    def set_stager_mover(self, stager_mover: Any) -> None:
        """
        :param data_mover: mode of the stager
        :type info: class:`dagon.StagerMover`
        """
        self.stager_mover = stager_mover

    def set_info(self, info: TaskInfo) -> None:
        """
        Change the information of the machine where the task is going to be executed. The information is used by
        :class:`dagon.Stager` to decide the data transfer protocol/application

        :param info: Machine info (ip, protocols, username)
        :type info: dict(str, object)
        """

        self.info = info

    def get_ip(self) -> str:
        """
        Returns the ip of the machine where the task is executed

        :return: IP address
        :rtype: str
        """
        from dagon.remote import CloudTask

        if isinstance(self, CloudTask):
            return self.info["public_ip"]
        else:
            return self.info["ip"] if self.ip == None else self.ip

    def get_info(self) -> Optional[TaskInfo]:
        """
        Returns the complete information of the machine where the task is executed

        :return: Machine information collected
        :rtype: dict(str, object)
        """
        return self.info

    def get_user(self) -> str:
        """
        Return the username who execute the task on the remote machine

        :return: Unix Username
        :rtype: str
        """

        return self.info["user"]

    def get_scratch_dir(self) -> Optional[str]:
        """
        Returns the task's scratch directory as soon as it's available

        :return: Absolute path to the scratch directory
        :rtype: str
        """

        while self.working_dir is None and self.status is not dagon.Status.FAILED:
            sleep(1)
        return self.working_dir

    def get_scratch_name(self) -> str:
        """
        Generates a unique name for the task scratch directory name

        :return: Name of the scratch directory
        :rtype: str
        """
        millis = int(round(time() * 1000))
        return str(millis) + "-" + self.name

    def as_json(self) -> Dict[str, Any]:
        """"
        Generates the JSON representation of the task

        :return: JSON task representation
        :rtype: dict(str, object)
        """

        explicit_type = self.task_type.value if self.task_type is not None else type(self).__name__.lower()
        json_task = {"name": self.name, "status": self.status.name,
                     "working_dir": self.working_dir, "nexts": [], "prevs": [],
                     "command": self.command, "type": explicit_type}

        for t in self.nexts:
            json_task['nexts'].append(t.name)
        for t in self.prevs:
            json_task['prevs'].append(t.name)
        return json_task

    def set_workflow(self, workflow: Any) -> None:
        """
        Set the workflow which execute this task

        :param workflow: :class:`dagon.Workflow` instance
        :type workflow: :class:`dagon.Workflow`
        """
        self.workflow = workflow

    def set_dag_tps(self, DAG_tps: Any) -> None:
        """
        Set the DAG_tps workflow which execute this task

        :param  DAG_tps: :class:`dagon.dag_tps` instance
        :type  DAG_tps: :class:`dagon.dag_tps`
        """
        self.dag_tps = DAG_tps

    def exists_dir(self, path: str) -> Optional[bool]:
        pass

    # Set the current status
    def set_status(self, status: Any) -> None:
        """
        Set the status for the current task

        :param status: status of the task
        :type status: :class:`dagon.task.Status`
        """
        self.status = status
        if self.workflow is not None:
            self.workflow.logger.debug("%s: %s", self.name, self.status)
            if self.workflow.is_api_available:
                self.workflow.api.update_task_status(
                    self.workflow.workflow_id, self.name, status.name)

    def execute_command(self, command: str) -> Optional[ExecutionResult]:
        """"
        Executes a command
        :param command: command to be executed
        """
        pass

    def add_dependency_to(self, task: Any) -> None:
        """
        Add a dependency to other task

        :param task: :class:`dagon.task.Task` instance dependency
        :type task: :class:`dagon.task.Task`
        """
        task.nexts.append(self)
        self.prevs.append(task)

        if self.workflow.is_api_available:  # add in the server
            self.workflow.api.add_dependency(
                self.workflow.workflow_id, self.name, task.name)

    def add_transversal_point(self, task: Any) -> None:
        """
        Add a dependency from other task

        :param task: :class:`dagon.task.Task` instance dependency
        :type task: :class:`dagon.task.Task`
        """
        self.prevs.append(task)

        if self.workflow.is_api_available:  # add in the server
            self.workflow.api.add_dependency(
                self.workflow.workflow_id, self.name, task.name)

    # Increment the reference count
    def increment_reference_count(self) -> None:
        """
        Increments the reference count
        """
        self.reference_count = self.reference_count + 1

    # Call garbage collector (remove scratch directory, container, cloud instance, etc)
    # implemented by each task class
    def on_garbage(self) -> None:
        """
        Call garbage collector, removing the scratch directory, containers and instances related to the
        task
        """

        # Perform some logging
        self.workflow.logger.debug("Removing %s", self.working_dir)

        shutil.move(self.working_dir, self.working_dir + "-removed")

        # Update the working directory
        self.working_dir = self.working_dir + "-removed"

        # Update the checkpoint
        self.workflow.checkpoints[self.workflow.name + "." +
                                  self.name]["working_dir"] = self.working_dir

    # Decrement the reference count

    def decrement_reference_count(self) -> None:
        """
        Decrement the reference count. When the number of references is equals to zero, the garbage collector is called
        """
        self.reference_count = self.reference_count - 1

        # Check if the scratch directory must be removed
        if self.reference_count == 0 and self.remove_scratch_dir is True:
            # Call garbage collector (remove scratch directory, container, cloud instace, etc)
            self.on_garbage()

            if self.workflow.checkpoint_file is not None:
                fp = open(self.workflow.checkpoint_file, 'w')
                fp.write(dumps(self.workflow.checkpoints,
                         sort_keys=True, indent=4))
                fp.close()

    def set_semaphore(self, sem: Semaphore) -> None:
        self.semaphore = sem

    # Method overrided
    def pre_run(self) -> None:
        """
        Resolve task dependencies
        For each workflow:// in the command string
        1) Extract the referenced task
        2) Add a reference in the referenced task

        """
        # Index of the starting position
        pos = 0
        # get workflows of dag_tps
        if self.dag_tps is not None:
            self.workflows = self.dag_tps.workflows

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object

            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            # Check if the referenced task is consistent
            if task is not None:
                # Add the dependency to the task
                if workflow_name == self.workflow.name:
                    self.add_dependency_to(task)
                else:
                    self.add_transversal_point(task)
                # Add the reference from the task
                task.increment_reference_count()

                # TODO: check this code
                """
                if self.mode == "parallel":
                    for next_task in self.nexts:
                        if self in next_task.prevs:
                            next_task.prevs.remove(self)
                        
                        for new_task in self.new_tasks:
                            next_task.add_dependency_to(new_task)
                """

            if task is None:  # if is None means that task is from another WF maybe in the dagon service
                # self.workflow.logger.debug("Adding transversal point")
                # self.workflow.logger.debug(workflow_name)
                # self.workflow.logger.debug(task)
                if self.workflow.is_api_available:
                    workflow_id = self.workflow.api.get_workflow_by_name(
                        workflow_name)
                    transversal_task = self.workflow.api.get_task(workflow_id, task_name)[
                        'task']  # get the task from the external workflow
                    transversal_task = DagonTask(TaskType[transversal_task['type'].upper()], transversal_task['name'],
                                                 transversal_task['command'],
                                                 transversal_workflow=workflow_id,
                                                 working_dir=transversal_task['working_dir'])
                    self.add_transversal_point(transversal_task)
                else:
                    raise ConnectionError("Dagon service is not available")

            # Go to the next element
            pos = pos2

    def discover_context(self) -> str:
        """
        Run ``context.sh`` on the execution host and return the launcher header

        The context script reports the host address and the available transfer
        protocols, which :class:`dagon.stager.base.Stager` uses to choose a data
        mover.  It runs where :meth:`on_execute` runs ``context.sh`` (for Slurm
        tasks: the submission host, outside any allocation).

        :return: launcher header shared by every generated script
        :rtype: str
        """
        # Initialize the script
        header = "#! /bin/bash\n"
        header += "export PATH=\"$HOME/.local/bin:$PATH\"\n"
        header += "# This is the DagOn launcher script\n\n"
        header += "code=0\n"
        # Add and execute the script

        # Quoted: shell syntax or spaces in a scratch path must never be executed
        # or split while the context is discovered (this script runs in every mode).
        context_script = header + "cd " + quote(self.working_dir + "/.dagon") + "\n"

        if "dynostore" in self.workflow.cfg:

            # Check if python is available
            header += "if command -v python &>/dev/null; then\n"
            header += "PYTHON=python\n"
            header += "elif command -v python3 &>/dev/null; then\n"
            header += "PYTHON=python3\n"
            header += "else\n"
            header += " echo \"Python is not available, please install Python to use DynoStore\"\n"
            header += " exit 1\n"
            header += "fi\n"

            header += "if $PYTHON -c \"import dynostore\" &>/dev/null; then\n"
            header += " echo \"DynoStore is installed\"\n"
            header += "else\n"
            header += " echo \"DynoStore is not installed, installing...\"\n"
            header += "pip install git+https://github.com/dynostore/dynostore-client\n"
            header += " fi\n"

        header += "echo \n echo \"************************************\"\n echo \n"

        context_script += header + self.get_how_im_script() + "\n\n"

        # execute context script
        result = self.on_execute(context_script, "context.sh")
        if result['code']:
            raise Exception(result['message'])

        # Step 1: Unescape the backslashes
        unescaped_output = result['output'].encode(
            'utf-8').decode('unicode_escape')

        # Optional: remove trailing newline if needed
        unescaped_output = unescaped_output.strip()

        # Get only the JSON part of the output
        parts_output = unescaped_output.split(
            "************************************")
        if len(parts_output) > 1:
            json_output = parts_output[1].strip()
        else:
            raise ValueError("Output does not contain expected JSON format")

        info = loads(json_output)

        if "dynostore" in self.workflow.cfg:
            info['dynostore'] = self.workflow.cfg['dynostore']

        # ToDO: Check if dynostore is available
        self.set_info(info)

        return header

    def build_stage_plan(self, command: str, strict_staging: bool = False) -> Tuple[List[str], List[StageInput], str]:
        """
        Resolve the ``workflow://`` references of *command* into a stage-in plan

        :param command: command to be executed by the task
        :param strict_staging: generate failure-propagating, space-safe transfer
            loops (scheduler-aware pre-staging); ``False`` keeps the legacy text
        :return: the stage-in shell blocks (one per reference), the resolved
            input manifest, and the command with references rewritten to the
            staged paths
        """
        stager = dagon.stager.base.Stager(
            self.data_mover, self.stager_mover, self.workflow.cfg)
        blocks: List[str] = []
        inputs: List[StageInput] = []

        # Create the body
        body = command

        # Index of the starting position
        pos = 0

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:

            # Get the position of the next dagon.Workflow.SCHEcdMA
            pos1 = command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(command)

            # Extract the parameter string
            arg = command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Get the rest of the string as local path
            local_path = "/" + "/".join(elements[2:])

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object
            # task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            if task is None:  # if is None means that task is from another WF maybe in the dagon service
                if self.workflow.is_api_available:
                    workflow_id = self.workflow.api.get_workflow_by_name(
                        workflow_name)
                    response = self.workflow.api.get_task(workflow_id,
                                                          task_name)  # get the task from the external workflow
                    transversal_task = response['task']
                    host_ip = response['host']
                    # if the host is the same in this computer, the task is in the same computer
                    if host_ip == self.workflow.ftpAtt['host']:
                        # the same workingdir
                        task_path = transversal_task['working_dir']
                    else:
                        task_path = self.workflow.local_path + transversal_task[
                            'working_dir']  # if not, we add an extra path
                        ftp = FTP_API(host_ip)
                        task_folder = transversal_task['working_dir'].split(
                            "/")[-1]  # the last one is the task folder
                        ftp.downloadFiles(task_folder, task_path)
                        # we need to download the data from the ftp host

                    task = DagonTask(TaskType[transversal_task['type'].upper()], transversal_task['name'],
                                     transversal_task['command'],
                                     transversal_workflow=workflow_id, working_dir=task_path)

            # Check if the referenced task is consistent
            if task is not None:
                if strict_staging:
                    # Pre-staging runs these transfers on the submission host:
                    # refuse references that could leave the staging roots.
                    validate_reference_path(workflow_name, task_name, local_path)
                # Evaluate the destination path
                dst_path = self.working_dir + "/.dagon/inputs/" + workflow_name + "/" + task_name

                # Create the destination directory
                block = "\n\n# Create the destination directory\n"
                block = block + "mkdir -p " + quote(dst_path + "/" + path.dirname(local_path)) + "\n"
                block = block + "if [ $? -ne 0 ]; then code=1; fi\n\n"
                # Add the move data command
                block = block + \
                    stager.stage_in(self, task, dst_path, local_path, strict=strict_staging)
                blocks.append(block)
                # The source is readable where the stage-in script runs only
                # for same-host COPY and LINK transfers.
                mover = getattr(stager, "last_data_mover", None)
                integrity = (INTEGRITY_CONTENT if mover in (dagon.stager.base.DataMover.COPY,
                                                            dagon.stager.base.DataMover.LINK)
                             else INTEGRITY_EXISTENCE)
                inputs.append(StageInput(
                    reference=dagon.Workflow.SCHEMA + arg, workflow=workflow_name, task=task_name,
                    local_path=local_path, source=str(task.get_scratch_dir()) + "/" + local_path,
                    destination=dst_path + "/" + local_path, integrity=integrity))

                if self.mode == "parallel":
                    files = glob.glob(
                        task.get_scratch_dir() + "/" + local_path)
                    taskType = TaskType[type(self).__name__.upper()]

                    for file in files:
                        filename, _ = path.splitext(path.basename(file))
                        taskParallelName = "{}_{}".format(self.name, filename)
                        cmd = body.replace(
                            dagon.Workflow.SCHEMA + arg, " workflow:///" + self.name + "/" + path.basename(file))

                        if type(self) == dagon.batch.Batch:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd,
                                                      transversal_workflow=self.transversal_workflow)

                        if type(self) == dagon.batch.RemoteBatch:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, ssh_username=self.ssh_username,
                                                      keypath=self.keypath, ip=self.ip)

                        elif type(self) == dagon.batch.Slurm:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, partition=self.partition,
                                                      ntasks=self.ntasks, memory=self.memory)

                        elif type(self) == dagon.batch.RemoteSlurm:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, partition=self.partition,
                                                      ntasks=self.ntasks, memory=self.memory,
                                                      ssh_username=self.ssh_username, keypath=self.keypath, ip=self.ip)

                        elif type(self) == dagon.remote.CloudTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, provider=self.provider,
                                                      ssh_username=self.ssh_username, key_options=self.key_options,
                                                      instance_id=self.instance_id, instance_flavour=self.instance_flavour,
                                                      instance_name=self.instance_name, stop_instance=self.stop_instance)

                        elif type(self) == dagon.docker_task.DockerTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                      container_id=self.container_id, remove=self.remove,
                                                      volume=self.volume, transversal_workflow=self.transversal_workflow)

                        elif type(self) == dagon.docker_task.DockerRemoteTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                      container_id=self.container_id, ssh_username=self.ssh_username,
                                                      keypath=self.keypath, ip=self.ip,
                                                      remove=self.remove, volume=self.volume,
                                                      transversal_workflow=self.transversal_workflow)
                            
                        elif type(self) == dagon.kubernetes_task.KubernetesTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                      namespace=self.namespace, remove=self.remove,
                                                      transversal_workflow=self.transversal_workflow)
                                
                        elif type(self) == dagon.kubernetes_task.RemoteKubernetesTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                    namespace=self.namespace, remove=self.remove,
                                                    ssh_username=self.ssh_username, keypath=self.keypath, ip=self.ip,
                                                    transversal_workflow=self.transversal_workflow)
                        
                        elif type(self) == dagon.apptainer_task.ApptainerTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                    bind_paths=self.bind_paths, overlay_size=self.overlay_size,
                                                    remove=self.remove, tmp_dir=self.tmp_dir,
                                                    transversal_workflow=self.transversal_workflow)
                            
                        elif type(self) == dagon.apptainer_task.RemoteApptainerTask:
                            parallel_task = DagonTask(taskType, taskParallelName, cmd, image=self.image,
                                                    bind_paths=self.bind_paths, overlay_size=self.overlay_size,
                                                    remove=self.remove, tmp_dir=self.tmp_dir,
                                                    ssh_username=self.ssh_username, keypath=self.keypath, ip=self.ip,
                                                    transversal_workflow=self.transversal_workflow)

                        self.workflow.add_task(parallel_task)
                        self.new_tasks.append(parallel_task)

                    for next_task in self.nexts:
                        if self in next_task.prevs:
                            next_task.prevs.remove(self)

                        for new_task in self.new_tasks:
                            next_task.add_dependency_to(new_task)

                    self.workflow.make_dependencies()

                    body = "echo \"Starting parallel tasks...\"\n"
                    body += "ln -sf " + quote(dst_path + "/" + local_path) + " " + quote(self.get_scratch_dir())
                else:
                    # Change the body of the command
                    body = body.replace(
                        dagon.Workflow.SCHEMA + arg, dst_path + "/" + local_path)
            pos = pos2

        return blocks, inputs, body

    def prepare_task(self, command: str, strict_staging: bool = False) -> PreparedTask:
        """
        Prepare *command* for execution as a structured :class:`dagon.prestage.PreparedTask`

        The phases are kept separate: (1) context discovery, (2) reference
        resolution and mover planning, (3) stage-in shell generation, and (4)
        compute launcher generation.  The legacy combined launcher and the
        pre-staging scripts are rendered from the same plan.
        """
        header = self.discover_context()
        prologue = self.launcher_prologue()
        blocks, inputs, body = self.build_stage_plan(command, strict_staging=strict_staging)
        invoke = "\n\n# Invoke the command\n" + self.include_command(body) + "if [ $? -ne 0 ]; then code=1; fi"
        return PreparedTask(working_dir=self.working_dir, header=header, prologue=prologue,
                            stage_blocks=blocks, invoke=invoke, resolved_command=body, inputs=inputs)

    # Pre process command
    def pre_process_command(self, command):
        """
        Preprocess the command resolving the dependencies with other tasks

        Returns the legacy launcher, which stages inputs and then runs the
        command in the same script (inside the allocation for scheduler tasks).

        :param command:
        :type command: command to be executed by the task

        :return: command preprocessed
        :rtype: str
        """
        return self.prepare_task(command).legacy_launcher()

    def launcher_prologue(self) -> str:
        """Return launcher lines run after ``cd`` into the working directory.

        Backends override this to prepare execution-time resources (for
        example a BeeOND volume) before staging and the command run.
        """
        return ""

    def launcher_epilogue(self) -> str:
        """Return launcher lines run after the command and before post-processing."""
        return ""

    def portable_environment(self) -> Dict[str, str]:
        """Return extra environment variables for portable local emulation."""
        return {}

    # process the command to execute
    def include_command(self, body):
        """
        Include the command to execute in the script body
        :param body: Script body
        :return: Script body with the command
        """
        # A pipeline's status is the status of ``tee``: restore the status of the
        # command itself so the launcher's ``$?`` check sees command failures.
        return (body + " | tee " + quote(self.stdout_path()) + "\n"
                + "(exit \"${PIPESTATUS[0]}\")\n")

    def stdout_path(self) -> str:
        """Return the file that captures the command's standard output."""
        return self.working_dir + "/.dagon/stdout.txt"

    # Post process the command
    def post_process_command(self, command):
        """
        Add some post process commands after the task execution
        :param command: Command to be executed
        :return: Command post-processed
        """
        footer = command + "\n"
        footer = footer + self.launcher_epilogue() + "\n"
        footer = footer + "# Perform post process\n"

        # if dynostore, push the data to dynostore
        if "dynostore" in self.workflow.cfg:
            dyno_conf = self.workflow.cfg['dynostore']
            dyno_server = f"{dyno_conf.get('host')}:{dyno_conf.get('port')}"
            footer += f"echo \"Pushing data to DynoStore server {dyno_server}\"\n"
            footer += f"$PYTHON -m dynostore.cli --server {dyno_server} put {self.working_dir} --recursive --catalog={os.path.basename(self.working_dir)}\n"
            footer += "DYNO_EXIT_CODE=$?\n"
            footer += "echo \"DynoStore exited with code: $DYNO_EXIT_CODE\"\n"
            footer += "if [ $DYNO_EXIT_CODE -ne 0 ]; then echo 'DynoStore upload failed'; code=1; fi\n"
            # an sleep for sync
            footer += f"sleep 1\n"
        footer += "exit $code"
        return footer

    # Method to be overrided
    def on_execute(self, script, script_name):
        """
        Execute the task script

        :param script: script content
        :type script: str

        :param script_name: script name
        :type script_name: str

        :return: execution result
        :rtype: dict() with the execution output (str) and code (int)
        """
        # The launcher script name
        script_name = self.working_dir + "/.dagon/" + script_name
        # Create a temporary launcher script
        # Launchers are bash scripts: always write LF line endings, also on Windows.
        file = open(script_name, "w", newline="\n")
        file.write(script)
        file.flush()
        file.close()
        chmod(script_name, 0o744)

    # create path using mkdirs
    def mkdir_working_dir(self, path):
        """
        Make the working directory

        :param path: Path to the working directory
        :type path: str
        """
        makedirs(path, exist_ok=True)

    def create_working_dir(self):
        """
        Create the working directory
        """

        self.remove_scratch_dir = self.workflow.get_remove_dir_op()

        if self.working_dir is None:
            # Set a scratch directory as working directory
            self.working_dir = self.workflow.get_scratch_dir_base() + "/" + \
                self.get_scratch_name()

        # Create scratch directory
        self.mkdir_working_dir(self.working_dir + "/.dagon")
        self.workflow.logger.debug(
            "%s: Scratch directory: %s", self.name, self.working_dir)
        if self.workflow.is_api_available:  # change scratch directory on server
            try:
                self.workflow.api.update_task(
                    self.workflow.workflow_id, self.name, "working_dir", self.working_dir)
            except Exception as e:
                self.workflow.logger.error(
                    "%s: Error updating scratch directory on server %s", self.name, e)

    def remove_reference_workflow(self):
        """
        Remove the reference
        For each workflow:// in the command
        """
        # Remove the reference
        # For each workflow:// in the command

        # Index of the starting position
        pos = 0

        # Forever unless no anymore dagon.Workflow.SCHEMA are present
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # The task name is the first element
            task_name = elements[1]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                workflow_name = self.workflow.name

            # Extract the reference task object
            # task = self.workflow.find_task_by_name(workflow_name, task_name)
            if self.workflows is None:
                task = self.workflow.find_task_by_name(
                    workflow_name, task_name)
            else:
                for wf in self.workflows:
                    task = wf.find_task_by_name(workflow_name, task_name)
                    if task is not None:
                        break

            # Check if the refernced task is consistent
            if task is not None:
                # Remove the reference from the task
                task.decrement_reference_count()

            # Go to the next element
            pos = pos2

        if len(self.nexts) == 0 and self.remove_scratch_dir is True:
            self.on_garbage()

    # Method execute
    def execute(self):
        """
        Execute the task

        :raises Exception: a problem occurred during the task  execution
        """
        if self.workflow.is_portable_emulation() is True:
            return self.execute_portable()
        key = self.checkpoint_key()

        # Local checkpoint
        if self.reuse_checkpoint():
            self.workflow.logger.debug(
                "%s Already completed ---" % (self.name))
        else:
            # Resolve before creating scratch so configuration errors leave no
            # partial state behind.
            pre_stage = self.resolve_pre_stage()
            if pre_stage and self.workflow.dry is not False:
                # A dry run of a pre-staged task is side-effect free: no
                # scratch directory, checkpoint entry, context discovery,
                # remote command, transfer, or scheduler call.
                self.plan_pre_staged_dry_run()
            elif pre_stage:
                self.create_working_dir()
                self.initialize_checkpoint()
                self.execute_pre_staged(key)
            else:
                self.create_working_dir()
                self.initialize_checkpoint()
                if self.pre_stage_requested():
                    self.pre_stage_metrics = {"pre_stage_effective": False, "policy_version": PRE_STAGE_POLICY_VERSION}
                self.execute_legacy(key)

        # DAGonStar currently has no separate output-transfer phase.  These
        # hooks bracket the existing post-execution output/reference cleanup.
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self.remove_reference_workflow()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def execute_legacy(self, key: str) -> None:
        """Run the legacy lifecycle: one launcher stages inputs and runs the command."""
        # ``pre_process_command`` creates the staging-in portion of the
        # launcher.  The generated launcher performs that staging when it
        # is subsequently executed.
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            launcher_script = self.pre_process_command(self.command)
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        # Apply some command post processing
        launcher_script = self.post_process_command(launcher_script)

        # Execute only if not dry
        self.workflow._fire_event("on_task_execute_start", self)
        if self.workflow.dry is False:

            # Invoke the actual executor
            start_time = time()
            self.result = self.on_execute(launcher_script, "launcher.sh")
            self.completetion_time = time() - start_time
            self.workflow.logger.debug(
                "%s Completed in %s seconds ---" % (self.name, self.completetion_time))

            self.workflow.checkpoints[key]["code"] = self.result['code']

            # Check if the execution failed
            if self.result['code']:
                raise Exception(
                    'Executable raised a execption ' + self.result['message'])

    def run(self):
        """
        Runs the thread where the task will be executed
        """
        if self.workflow is not None:
            self.workflow._fire_event("on_task_start", self)
            try:
                # Change the status
                self.set_status(dagon.Status.WAITING)
                self.workflow._fire_event("on_task_wait", self)

                # Wait for each previous tasks
                for task in self.prevs:
                    # if its a process from other workflow
                    if self.workflow.find_task_by_name(self.workflow.name, task.name) is None:
                        while True:
                            if self.workflow.is_api_available and task.transversal_workflow is not None:  # when is an asynchronous execution
                                try:
                                    transversal_task = self.workflow.api.get_task(task.transversal_workflow, task.name)[
                                        'task']  # get the task from the external workflow using the api
                                    if transversal_task['status'] == dagon.Status.FINISHED.value or transversal_task[
                                            'status'] == dagon.Status.FAILED.value:
                                        break
                                    else:
                                        sleep(1)
                                except Exception as e:
                                    task.set_status(dagon.Status.FAILED)
                                    self.workflow.logger.warning(
                                        'Worflow dependence not found, Error: ' + str(e))
                                    break
                            # when is used the dag_tps structure
                            elif task.status == dagon.Status.FINISHED or task.status == dagon.Status.FAILED:
                                break
                            else:
                                sleep(.5)
                    else:
                        while True:
                            # if this happends, the workflow is probably a meta-workflow
                            if task.status == dagon.Status.WAITING or task.status == dagon.Status.READY:
                                sleep(.5)
                            else:
                                task.join()
                                break

                # Check if one of the previous tasks crashed
                for task in self.prevs:
                    if task.status == dagon.Status.FAILED:
                        self.set_status(dagon.Status.FAILED)
                        return

                # Change the status
                self.set_status(dagon.Status.RUNNING)
                # Execute the task Job
                self.workflow.logger.debug("%s: Executing...", self.name)
                # self.semaphore.acquire()
                self.execute()
                sleep(2)
                # Start all next task
                for task in self.nexts:
                    if task.status == dagon.Status.READY:
                        self.workflow.logger.debug(
                            "%s: Starting task: %s", self.name, task.name)
                        try:
                            task.start()
                        except RuntimeError:
                            self.workflow.logger.warning(
                                "%s: Task %s already started.", self.name, task.name)

                # Change the status
                # self.workflow.api.update_task(self.workflow.workflow_id, self.name, "working_dir", self.working_dir)
                self.set_status(dagon.Status.FINISHED)
                return
            except Exception as exc:
                self.workflow.logger.exception("%s: execution failed", self.name)
                self.set_status(dagon.Status.FAILED)
            finally:
                self.workflow._fire_event("on_task_end", self)

    def get_public_key(self):
        """
        Return the temporal public key to this machine

        :return: public key
        :rtype: str with the public key
        """
        pass

    def add_public_key(self, key):
        """
        Add a SSH public key on the remote machine

        :param key: Path to the public key
        :type key: str
        :return: result of the execution
        :rtype: dict() with the execution output (str) and code (int)
        """
        pass

    def remove_from_workflow(self):
        """
        Remove the reference to the workflow
        For each workflow:// in the command
        """
        # Remove the reference
        # For each workflow:// in the command

        # Index of the starting position
        pos = 0
        temp = self.command
        while True:
            # Get the position of the next dagon.Workflow.SCHEMA
            pos1 = self.command.find(dagon.Workflow.SCHEMA, pos)

            # Check if there is no dagon.Workflow.SCHEMA
            if pos1 == -1:
                # Exit the forever cycle
                break

            # Find the first occurrent of a whitespace (or if no occurrence means the end of the string)
            pos2 = self.command.find(" ", pos1)

            # Check if this is the last referenced argument
            if pos2 == -1:
                pos2 = len(self.command)

            # Extract the parameter string
            arg = self.command[pos1:pos2]

            # Remove the dagon.Workflow.SCHEMA label
            arg = arg.replace(dagon.Workflow.SCHEMA, "")

            # Split each argument in elements by the slash
            elements = arg.split("/")

            # Extract the referenced task's workflow name
            workflow_name = elements[0]

            # Set the default workflow name if needed
            if workflow_name is None or workflow_name == "":
                pass
            else:
                temp = temp.replace(workflow_name, "")

            # Go to the next element
            pos = pos2
        return temp

    def get_how_im_script(self):
        """
        Create the script to get the context where the task will be executed

        :return: Context script
        :rtype: str
        """

        return r"""
# Initialize
machine_type="none"
public_id="none"
user="none"
status_sshd="none"
status_ftpd="none"
status_skycds="none"
#get http communication protocol
curl_or_wget=$(if hash curl 2>/dev/null; then echo "curl"; elif hash wget 2>/dev/null; then echo "wget"; fi);


if [ $curl_or_wget = "wget" ]; then
  public_ip=`wget -q -O- https://ipinfo.io/ip`
else
  public_ip=`curl -s https://ipinfo.io/ip`
fi



# If no public ip is available, then it is a cluster node
machine_type="cluster-node"
private_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|head -n 1`

if [ "$private_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  private_ip=`ifconfig 2>/dev/null| grep "inet "| grep -v "127.0.0.1"| awk '{print $2}'|grep -v "192.168."|grep -v "172.16."|grep -v "10."|head -n 1`
fi

#net-tools is not installed, try with ip -o route

if [ "$private_ip" == "" ]
then
  # The machine is a cluster frontend (or a single machine)
  machine_type="cluster-frontend"
  private_ip=`ip -o route get to 8.8.8.8 | sed -n 's/.*src \([0-9.]\+\).*/\\1/p'`
fi

# Check if either sshd.service or ssh.service is available and active
status_sshd=$(systemctl status sshd 2>/dev/null | grep 'Active' | awk '{print $2}')

# If sshd is not found or inactive, try ssh
if [ -z "$status_sshd" ]; then
  status_sshd=$(systemctl status ssh 2>/dev/null | grep 'Active' | awk '{print $2}')
fi

# If neither is found, set to "none"
if [ -z "$status_sshd" ]; then
  status_sshd="none"
fi

# Check if the ftp is available
status_ftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_ftpd" == "" ]
then
  status_ftpd="none"
fi

# Check if the grid ftp is available
status_gsiftpd=`systemctl status globus-gridftp-server 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "" ]
then
  status_gsiftpd="none"
fi

#check if skycds container is running
status_docker=`systemctl status docker 2>/dev/null|grep "Active"| awk '{print $2}'`
if [ "$status_gsiftpd" == "active" ]
then
    if [ "$(docker ps -aq -f status=running -f name=client)" ]; then
    # cleanup
        status_skycds="active"
    fi
fi


# Get the user
user=$USER

echo "no" | ssh-keygen  -b 2048 -t rsa -f ssh_key -q -N ""  >/dev/null

# Construct the json
json="{\\\"type\\\":\\\"$machine_type\\\",\\\"public_ip\\\":\\\"$public_ip\\\",\\\"ip\\\":\\\"$private_ip\\\",\\\"user\\\":\\\"$user\\\",\\\"SCP\\\":\\\"$status_sshd\\\",\\\"FTP\\\":\\\"$status_ftpd\\\",\\\"GRIDFTP\\\":\\\"$status_gsiftpd\\\",\\\"SKYCDS\\\":\\\"$status_skycds\\\"}"
echo $json
"""
