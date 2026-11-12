"""BeeOND (BeeGFS On Demand) volumes for Slurm tasks.

Some Slurm sites create a job-private BeeGFS file system across the nodes of an
allocation when the job is submitted with a site-specific ``--comment`` (for
example ``--comment=beeond-fs``).  The file system is mounted on every node of
the allocation, typically at ``/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}``,
and is destroyed when the job ends.

This module lets DAGonStar use such volumes with two scopes:

``task``
    Every Slurm task submits its own BeeOND-enabled job.  The volume lives as
    long as that task's job.  Before the job ends, the launcher copies the
    volume contents to a persistent directory (by default ``<working_dir>/beeond``)
    so downstream tasks can reference them with ``workflow:///<task>/beeond/...``.

``workflow``
    A long-lived "holder" job allocates the nodes and the BeeOND volume once
    per workflow.  Slurm tasks attached to the volume run as job steps inside
    that allocation (``srun --jobid=<holder>``) and share the volume.  When the
    workflow ends, the holder job copies the volume contents to a persistent
    directory and exits, which releases the allocation.

Commands find the volume through the ``DAGON_BEEOND`` environment variable.
Data persistence is verified by comparing the persisted file list (or
checksums) with the volume contents.  This module is dependency-free, never
records credentials, and builds every shell value through :func:`dagon.shell.quote`.
"""

import re
import shlex
import subprocess
import threading
from dataclasses import asdict, dataclass, field, fields, replace
from os import makedirs, path
from time import monotonic, sleep
from typing import Any, Dict, List, Mapping, Optional, Union

from dagon.platform_support import launcher_environment
from dagon.shell import join_command, quote

#: Environment variable that holds the BeeOND mount point inside launchers.
BEEOND_ENV = "DAGON_BEEOND"

#: Default name of the per-workflow volume.
DEFAULT_VOLUME = "default"

SCOPES = ("task", "workflow")
PERSIST_TOOLS = ("auto", "rsync", "cp")
VERIFY_MODES = ("none", "list", "checksum")

_UNSAFE_TEMPLATE = re.compile(r'["`\\\n\r]|\$\(')
_VOLUME_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _as_bool(value: Any, option: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError("BeeOND option %r expects a boolean, got %r" % (option, value))


def _as_int(value: Any, option: str) -> Optional[int]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("BeeOND option %r expects an integer, got %r" % (option, value)) from exc
    if number < 0:
        raise ValueError("BeeOND option %r must not be negative" % option)
    return number


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return shlex.split(value)
    return [str(item) for item in value]


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class BeeONDConfig:
    """Configuration of a BeeOND volume.

    Values can come from the ``[beeond]`` section of ``dagon.ini`` and be
    overridden per task or per workflow volume.

    :ivar scope: ``"task"`` or ``"workflow"``
    :ivar volume: name of the workflow volume (workflow scope only)
    :ivar comment: Slurm ``--comment`` that asks the site to create the volume
    :ivar mount_template: mount point, expanded by bash on the compute node;
        ``$VAR``/``${VAR}`` references are allowed, command substitution is not
    :ivar mount_timeout: seconds to wait for the mount point to become writable
    :ivar persist: copy the volume to persistent storage before it is destroyed
    :ivar persist_dir: persistent destination; relative task-scope paths are
        relative to the task working directory, relative workflow-scope paths to
        the workflow scratch directory
    :ivar persist_on_failure: also persist when the task command failed
    :ivar persist_tool: ``"auto"`` (rsync when available, otherwise ``cp -a``),
        ``"rsync"`` or ``"cp"``
    :ivar verify: ``"none"``, ``"list"`` (every file exists) or ``"checksum"``
    :ivar signal_grace: seconds before the Slurm time limit at which the batch
        shell receives ``SIGUSR1`` so the volume is persisted before teardown
    :ivar persist_each_task: workflow scope: also persist after every task
    :ivar restore: workflow scope: copy an existing ``persist_dir`` back into a
        fresh volume when the holder starts (useful when resuming)
    :ivar nodes: workflow scope: ``--nodes`` of the holder allocation
    :ivar nodelist: workflow scope: ``--nodelist`` of the holder allocation
    :ivar partition: workflow scope: ``--partition`` of the holder allocation
    :ivar time: workflow scope: ``--time`` of the holder allocation
    :ivar ntasks_per_node: workflow scope: ``--ntasks-per-node`` of the holder
    :ivar sbatch_options: workflow scope: extra holder ``sbatch`` options
    :ivar step_options: workflow scope: options of the ``srun`` task steps
    :ivar state_dir: workflow scope: shared directory for holder control files
    :ivar start_timeout: workflow scope: seconds to wait for the holder volume
    :ivar stop_timeout: workflow scope: seconds to wait for final persistence
    :ivar poll_interval: workflow scope: seconds between holder state checks
    """

    scope: str = "task"
    volume: str = DEFAULT_VOLUME
    comment: str = "beeond-fs"
    mount_template: str = "/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}"
    mount_timeout: int = 120
    persist: bool = True
    persist_dir: Optional[str] = None
    persist_on_failure: bool = True
    persist_tool: str = "auto"
    verify: str = "list"
    signal_grace: Optional[int] = None
    persist_each_task: bool = False
    restore: bool = False
    nodes: Optional[int] = None
    nodelist: Optional[str] = None
    partition: Optional[str] = None
    time: Optional[str] = None
    ntasks_per_node: Optional[int] = None
    sbatch_options: List[str] = field(default_factory=list)
    step_options: List[str] = field(default_factory=lambda: ["--overlap", "--nodes=1", "--ntasks=1"])
    state_dir: Optional[str] = None
    start_timeout: int = 600
    stop_timeout: int = 3600
    poll_interval: float = 5.0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Raise :class:`ValueError` for an inconsistent configuration."""
        if self.scope not in SCOPES:
            raise ValueError("BeeOND scope must be one of %s, got %r" % (SCOPES, self.scope))
        if not _VOLUME_NAME.match(self.volume or ""):
            raise ValueError("BeeOND volume names may contain letters, digits, '.', '_' and '-' only")
        if not self.comment or not self.comment.strip():
            raise ValueError("BeeOND requires the Slurm comment that enables the volume")
        if not self.mount_template or _UNSAFE_TEMPLATE.search(self.mount_template):
            raise ValueError("BeeOND mount_template must be non-empty and may only use $VAR or ${VAR} "
                             "expansions (no quotes, backslashes, backticks or $(...))")
        if self.persist_tool not in PERSIST_TOOLS:
            raise ValueError("BeeOND persist_tool must be one of %s" % (PERSIST_TOOLS,))
        if self.verify not in VERIFY_MODES:
            raise ValueError("BeeOND verify must be one of %s" % (VERIFY_MODES,))
        if self.poll_interval < 0:
            raise ValueError("BeeOND poll_interval must not be negative")

    _BOOLEANS = ("persist", "persist_on_failure", "persist_each_task", "restore")
    _INTEGERS = ("mount_timeout", "signal_grace", "nodes", "ntasks_per_node", "start_timeout", "stop_timeout")
    _LISTS = ("sbatch_options", "step_options")
    _OPTIONAL_STRINGS = ("persist_dir", "nodelist", "partition", "time", "state_dir")

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]] = None,
                     base: Optional["BeeONDConfig"] = None) -> "BeeONDConfig":
        """Build a configuration from a mapping (for example a ``dagon.ini`` section).

        Unknown keys are rejected so typos do not silently disable persistence.
        """
        values = asdict(base) if base is not None else {}
        known = {item.name for item in fields(cls)}
        for key, value in dict(mapping or {}).items():
            name = str(key).strip().lower()
            if name not in known:
                raise ValueError("Unknown BeeOND option: %r" % key)
            if name in cls._BOOLEANS:
                value = _as_bool(value, name)
            elif name in cls._INTEGERS:
                value = _as_int(value, name)
                if value is None and name in ("mount_timeout", "start_timeout", "stop_timeout"):
                    continue
            elif name in cls._LISTS:
                value = _as_list(value)
            elif name in cls._OPTIONAL_STRINGS:
                value = _as_optional_str(value)
            elif name == "poll_interval":
                value = float(value)
            else:
                value = str(value).strip()
            values[name] = value
        return cls(**values)

    def with_options(self, **options: Any) -> "BeeONDConfig":
        """Return a copy with *options* applied through the same validation."""
        return BeeONDConfig.from_mapping(options, base=self)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable, credential-free representation."""
        return asdict(self)


def workflow_defaults(workflow: Any) -> BeeONDConfig:
    """Return the ``[beeond]`` defaults of *workflow*'s configuration."""
    cfg = getattr(workflow, "cfg", None) or {}
    section = cfg.get("beeond", {}) if hasattr(cfg, "get") else {}
    return BeeONDConfig.from_mapping(section or {})


# ---------------------------------------------------------------------------
# Launcher fragments
# ---------------------------------------------------------------------------

def mount_script(config: BeeONDConfig, on_timeout: str = "exit 1") -> str:
    """Return bash that resolves ``$DAGON_BEEOND`` and waits until it is writable."""
    timeout = int(config.mount_timeout)
    return (
        "# Resolve the BeeOND mount point of this Slurm job\n"
        "DAGON_BEEOND=\"" + config.mount_template + "\"\n"
        "dagon_beeond_waited=0\n"
        "while [ ! -d \"$DAGON_BEEOND\" ] || [ ! -w \"$DAGON_BEEOND\" ]; do\n"
        "  if [ \"$dagon_beeond_waited\" -ge " + str(timeout) + " ]; then\n"
        "    echo \"DAGonStar: BeeOND mount $DAGON_BEEOND is not available after "
        + str(timeout) + " s\" >&2\n"
        "    " + on_timeout + "\n"
        "  fi\n"
        "  sleep 1\n"
        "  dagon_beeond_waited=$((dagon_beeond_waited + 1))\n"
        "done\n"
        "export DAGON_BEEOND\n"
    )


def persist_function_script(config: BeeONDConfig, persist_dir: str, report_dir: str) -> str:
    """Return a bash function ``dagon_beeond_persist`` that copies the volume.

    The function is idempotent within one shell, copies ``$DAGON_BEEOND`` into
    *persist_dir*, verifies the copy according to ``config.verify``, and writes
    ``beeond_persist.status`` plus the file lists into *report_dir*.
    """
    dst = quote(persist_dir)
    report = quote(report_dir)
    if config.persist_tool == "cp":
        copy = "    cp -a \"$DAGON_BEEOND\"/. \"$dagon_dst\"/ || dagon_rc=1\n"
    elif config.persist_tool == "rsync":
        copy = "    rsync -a \"$DAGON_BEEOND\"/ \"$dagon_dst\"/ || dagon_rc=1\n"
    else:
        copy = (
            "    if command -v rsync >/dev/null 2>&1; then\n"
            "      rsync -a \"$DAGON_BEEOND\"/ \"$dagon_dst\"/ || dagon_rc=1\n"
            "    else\n"
            "      cp -a \"$DAGON_BEEOND\"/. \"$dagon_dst\"/ || dagon_rc=1\n"
            "    fi\n"
        )
    verify = ""
    if config.verify in ("list", "checksum"):
        verify += (
            "  if [ \"$dagon_rc\" -eq 0 ]; then\n"
            "    (cd \"$DAGON_BEEOND\" && find . -type f | LC_ALL=C sort) > \"$dagon_src_lst\" || dagon_rc=1\n"
            "    (cd \"$dagon_dst\" && find . -type f | LC_ALL=C sort) > \"$dagon_dst_lst\" || dagon_rc=1\n"
            "    if [ -n \"$(LC_ALL=C comm -23 \"$dagon_src_lst\" \"$dagon_dst_lst\")\" ]; then\n"
            "      echo \"DAGonStar: BeeOND persistence verification failed: missing files in $dagon_dst\" >&2\n"
            "      dagon_rc=1\n"
            "    fi\n"
            "  fi\n"
        )
    if config.verify == "checksum":
        verify += (
            "  if [ \"$dagon_rc\" -eq 0 ]; then\n"
            "    (cd \"$DAGON_BEEOND\" && while IFS= read -r f; do cksum \"$f\"; done < \"$dagon_src_lst\")"
            " > \"$dagon_report/beeond_source.cksum\" || dagon_rc=1\n"
            "    (cd \"$dagon_dst\" && while IFS= read -r f; do cksum \"$f\"; done < \"$dagon_src_lst\")"
            " > \"$dagon_report/beeond_persisted.cksum\" || dagon_rc=1\n"
            "    if ! cmp -s \"$dagon_report/beeond_source.cksum\" \"$dagon_report/beeond_persisted.cksum\"; then\n"
            "      echo \"DAGonStar: BeeOND persistence verification failed: checksum mismatch in $dagon_dst\" >&2\n"
            "      dagon_rc=1\n"
            "    fi\n"
            "  fi\n"
        )
    return (
        "# Copy the BeeOND volume to persistent storage before it is destroyed\n"
        "dagon_beeond_persist() {\n"
        "  if [ -n \"${DAGON_BEEOND_PERSIST_CODE:-}\" ]; then return \"$DAGON_BEEOND_PERSIST_CODE\"; fi\n"
        "  local dagon_dst=" + dst + "\n"
        "  local dagon_report=" + report + "\n"
        "  local dagon_rc=0\n"
        "  local dagon_src_lst=\"$dagon_report/beeond_source.lst\"\n"
        "  local dagon_dst_lst=\"$dagon_report/beeond_persisted.lst\"\n"
        "  mkdir -p \"$dagon_dst\" \"$dagon_report\" || dagon_rc=1\n"
        "  if [ \"$dagon_rc\" -eq 0 ]; then\n"
        + copy +
        "  fi\n"
        + verify +
        "  printf 'persist_code=%s\\npersist_dir=%s\\n' \"$dagon_rc\" \"$dagon_dst\""
        " > \"$dagon_report/beeond_persist.status\"\n"
        "  if [ \"$dagon_rc\" -eq 0 ]; then\n"
        "    echo \"DAGonStar: BeeOND volume $DAGON_BEEOND persisted to $dagon_dst\"\n"
        "  else\n"
        "    echo \"DAGonStar: BeeOND persistence to $dagon_dst failed\" >&2\n"
        "  fi\n"
        "  DAGON_BEEOND_PERSIST_CODE=$dagon_rc\n"
        "  return $dagon_rc\n"
        "}\n"
    )


def restore_script(persist_dir: str) -> str:
    """Return bash that copies an existing *persist_dir* into ``$DAGON_BEEOND``."""
    src = quote(persist_dir)
    return (
        "# Restore previously persisted data into the fresh BeeOND volume\n"
        "if [ -d " + src + " ]; then\n"
        "  if command -v rsync >/dev/null 2>&1; then\n"
        "    rsync -a " + src + "/ \"$DAGON_BEEOND\"/ || exit 1\n"
        "  else\n"
        "    cp -a " + src + "/. \"$DAGON_BEEOND\"/ || exit 1\n"
        "  fi\n"
        "fi\n"
    )


def task_prologue(config: BeeONDConfig, persist_dir: str, report_dir: str) -> str:
    """Launcher prologue of a task-scope volume (runs inside the BeeOND job)."""
    script = "\n# BeeOND on-demand file system (task scope)\n"
    script += "export DAGON_BEEOND_SCOPE=task\n"
    script += mount_script(config)
    if config.persist:
        script += "export DAGON_BEEOND_PERSIST_DIR=" + quote(persist_dir) + "\n"
        script += persist_function_script(config, persist_dir, report_dir)
        script += (
            "# Persist on Slurm time-limit warnings and termination requests\n"
            "dagon_beeond_on_signal() {\n"
            "  echo \"DAGonStar: termination signal received, persisting BeeOND data\" >&2\n"
            "  if [ -n \"${DAGON_COMMAND_PID:-}\" ]; then\n"
            "    # Stop the command (and its direct children) for a consistent snapshot.\n"
            "    pkill -TERM -P \"$DAGON_COMMAND_PID\" 2>/dev/null\n"
            "    kill -TERM \"$DAGON_COMMAND_PID\" 2>/dev/null\n"
            "    wait \"$DAGON_COMMAND_PID\" 2>/dev/null\n"
            "  fi\n"
            "  dagon_beeond_persist\n"
            "  exit 1\n"
            "}\n"
            "trap dagon_beeond_on_signal USR1 TERM\n"
        )
    return script + "\n"


def task_epilogue(config: BeeONDConfig) -> str:
    """Launcher epilogue of a task-scope volume."""
    if not config.persist:
        return ""
    condition = "true" if config.persist_on_failure else "[ \"$code\" -eq 0 ]"
    return (
        "\n# Persist the task-scope BeeOND volume before the job releases it\n"
        "trap - USR1 TERM\n"
        "if " + condition + "; then\n"
        "  dagon_beeond_persist || code=1\n"
        "fi\n"
    )


def background_command(command: str) -> str:
    """Run *command* in the background so signal traps fire while it runs."""
    return "{ " + command.rstrip("\n") + " ; } &\nDAGON_COMMAND_PID=$!\nwait \"$DAGON_COMMAND_PID\"\n"


# ---------------------------------------------------------------------------
# Hosts used by the workflow-scope holder
# ---------------------------------------------------------------------------

class LocalHost:
    """Run holder control commands on the machine executing DAGonStar."""

    def run(self, argv: List[str]) -> Dict[str, Any]:
        try:
            completed = subprocess.run(list(argv), text=True, capture_output=True,
                                       env=launcher_environment())
        except OSError as exc:
            return {"code": 127, "output": "", "message": str(exc)}
        return {"code": completed.returncode, "output": completed.stdout,
                "message": completed.stderr or (completed.stdout if completed.returncode else "")}

    def makedirs(self, directory: str) -> None:
        makedirs(directory, exist_ok=True)

    def write_file(self, filepath: str, content: str) -> None:
        directory = path.dirname(filepath)
        if directory:
            makedirs(directory, exist_ok=True)
        with open(filepath, "w", newline="\n") as stream:
            stream.write(content)

    def read_file(self, filepath: str) -> Optional[str]:
        try:
            with open(filepath) as stream:
                return stream.read()
        except OSError:
            return None


class SSHHost:
    """Run holder control commands through an existing SSH connection."""

    def __init__(self, ssh_connection: Any) -> None:
        self.ssh_connection = ssh_connection

    def run(self, argv: List[str]) -> Dict[str, Any]:
        return self.ssh_connection.execute_command(join_command(argv))

    def makedirs(self, directory: str) -> None:
        result = self.run(["mkdir", "-p", directory])
        if result.get("code"):
            raise IOError("Cannot create %s: %s" % (directory, result.get("message")))

    def write_file(self, filepath: str, content: str) -> None:
        self.ssh_connection.create_file(filepath, content)

    def read_file(self, filepath: str) -> Optional[str]:
        result = self.ssh_connection.execute_command(
            "if [ -f " + quote(filepath) + " ]; then cat " + quote(filepath) + "; else exit 3; fi")
        if result.get("code"):
            return None
        return result.get("output", "")


# ---------------------------------------------------------------------------
# Workflow-scope volume
# ---------------------------------------------------------------------------

class BeeONDVolume:
    """A BeeOND volume shared by the Slurm tasks of one workflow.

    The volume is started lazily by the first task that uses it and stopped by
    :meth:`dagon.Workflow.run` when the workflow ends.  Stopping asks the
    holder job to persist the volume and waits for the persistence status.
    """

    def __init__(self, workflow: Any, config: BeeONDConfig) -> None:
        if config.scope != "workflow":
            config = replace(config, scope="workflow")
        self.workflow = workflow
        self.config = config
        self.name = config.volume
        self.job_id: Optional[str] = None
        self.mount: Optional[str] = None
        self.host: Any = None
        self.state = "created"
        self.persist_code: Optional[int] = None
        self._lock = threading.RLock()

    # -- paths -----------------------------------------------------------

    def _base(self) -> str:
        return self.workflow.get_scratch_dir_base()

    def persist_dir(self) -> str:
        """Return the persistent destination of this volume."""
        configured = self.config.persist_dir
        default = "%s-beeond-%s" % (self.workflow.name, self.name)
        target = configured or default
        if path.isabs(target) or target.startswith("/"):
            return target
        return self._base().rstrip("/") + "/" + target

    def state_dir(self) -> str:
        """Return the shared directory holding the holder control files."""
        if self.config.state_dir:
            return self.config.state_dir
        return self._base().rstrip("/") + "/.dagon-beeond/%s-%s" % (self.workflow.name, self.name)

    def _file(self, name: str) -> str:
        return self.state_dir().rstrip("/") + "/" + name

    # -- holder job --------------------------------------------------------

    def holder_script(self) -> str:
        """Return the batch script of the holder job."""
        config = self.config
        state = quote(self.state_dir())
        ready = quote(self._file("ready"))
        script = "#!/bin/bash\n"
        script += "# DAGonStar BeeOND workflow volume holder\n"
        script += "DAGON_BEEOND_STATE=" + state + "\n"
        script += "mkdir -p \"$DAGON_BEEOND_STATE\" || exit 1\n"
        script += mount_script(config, on_timeout=(
            "echo mount-timeout > \"$DAGON_BEEOND_STATE/failed\"; exit 1"))
        if config.persist:
            script += persist_function_script(config, self.persist_dir(), self.state_dir())
            if config.restore:
                script += restore_script(self.persist_dir())
        script += (
            "printf '%s\\n%s\\n' \"$SLURM_JOB_ID\" \"$DAGON_BEEOND\" > \"$DAGON_BEEOND_STATE/ready.tmp\"\n"
            "mv \"$DAGON_BEEOND_STATE/ready.tmp\" " + ready + "\n"
            "dagon_beeond_stop=\n"
            "trap 'dagon_beeond_stop=signal' USR1 TERM\n"
            "while [ ! -f \"$DAGON_BEEOND_STATE/stop\" ] && [ -z \"$dagon_beeond_stop\" ]; do\n"
            "  sleep " + str(max(1, int(config.poll_interval))) + " &\n"
            "  wait $!\n"
            "done\n"
            "trap - USR1 TERM\n"
        )
        if config.persist:
            script += "dagon_beeond_persist\ndagon_rc=$?\n"
        else:
            script += "dagon_rc=0\n"
        script += (
            "printf '%s\\n' \"$dagon_rc\" > \"$DAGON_BEEOND_STATE/done.tmp\"\n"
            "mv \"$DAGON_BEEOND_STATE/done.tmp\" \"$DAGON_BEEOND_STATE/done\"\n"
            "exit \"$dagon_rc\"\n"
        )
        return script

    def submit_argv(self) -> List[str]:
        """Return the ``sbatch`` command line that submits the holder job."""
        config = self.config
        options = ["--parsable", "--comment=" + config.comment.strip()]
        if config.partition:
            options.append("--partition=" + config.partition)
        if config.nodes is not None:
            options.append("--nodes=" + str(config.nodes))
        if config.nodelist:
            options.append("--nodelist=" + config.nodelist)
        if config.ntasks_per_node is not None:
            options.append("--ntasks-per-node=" + str(config.ntasks_per_node))
        if config.time:
            options.append("--time=" + config.time)
        if config.signal_grace:
            options.append("--signal=B:USR1@" + str(config.signal_grace))
        options.extend(config.sbatch_options)
        return ["sbatch", *options, "-J", "dagon-beeond-%s-%s" % (self.workflow.name, self.name),
                "-D", self.state_dir(), "-o", self._file("holder-%j.out"), self._file("holder.sh")]

    def ensure_started(self, host: Any) -> None:
        """Submit the holder job once and wait until its volume is mounted."""
        with self._lock:
            if self.state == "running":
                return
            if self.state not in ("created",):
                raise RuntimeError("BeeOND volume %r cannot be reused after it is %s"
                                   % (self.name, self.state))
            self.host = host
            host.makedirs(self.state_dir())
            for stale in ("ready", "stop", "done", "failed"):
                host.run(["rm", "-f", self._file(stale)])
            host.write_file(self._file("holder.sh"), self.holder_script())
            result = host.run(self.submit_argv())
            if result.get("code"):
                self.state = "failed"
                raise RuntimeError("BeeOND holder submission failed: %s" % result.get("message"))
            self.job_id = (result.get("output") or "").strip().split(";")[0].strip()
            if not self.job_id:
                self.state = "failed"
                raise RuntimeError("BeeOND holder submission returned no job id")
            self.state = "starting"
            self._log("debug", "BeeOND volume %s: holder job %s submitted", self.name, self.job_id)

            deadline = monotonic() + self.config.start_timeout
            while True:
                ready = host.read_file(self._file("ready"))
                if ready:
                    lines = [line.strip() for line in ready.splitlines() if line.strip()]
                    if len(lines) >= 2:
                        self.mount = lines[1]
                        self.state = "running"
                        self._log("info", "BeeOND volume %s mounted at %s (job %s)",
                                  self.name, self.mount, self.job_id)
                        return
                failed = host.read_file(self._file("failed"))
                if failed is not None or not self._job_alive(host):
                    self.state = "failed"
                    self._cancel(host)
                    raise RuntimeError("BeeOND holder job %s ended before its volume was ready"
                                       % self.job_id)
                if monotonic() >= deadline:
                    self.state = "failed"
                    self._cancel(host)
                    raise RuntimeError("BeeOND volume %s was not ready within %s s"
                                       % (self.name, self.config.start_timeout))
                sleep(self.config.poll_interval)

    def _job_alive(self, host: Any) -> bool:
        result = host.run(["squeue", "-h", "-j", str(self.job_id), "-o", "%T"])
        if result.get("code"):
            # squeue errors for jobs that left the queue; also tolerate missing squeue.
            return "Invalid job id" not in (result.get("message") or "")
        return bool((result.get("output") or "").strip())

    def _cancel(self, host: Any) -> None:
        if self.job_id:
            host.run(["scancel", str(self.job_id)])

    def step_argv(self, task_name: str, working_dir: str, launcher: str, bash: str = "bash") -> List[str]:
        """Return the ``srun`` command that runs a task launcher inside the holder job."""
        if self.state != "running" or not self.job_id:
            raise RuntimeError("BeeOND volume %r is not running" % self.name)
        return ["srun", "--jobid=" + str(self.job_id), *self.config.step_options,
                "-J", task_name, "-D", working_dir, bash, launcher]

    def stop(self) -> Optional[int]:
        """Ask the holder to persist the volume and release the allocation.

        :return: the persistence exit code (0 on success), or ``None`` when the
            volume was never started
        :raises RuntimeError: when persistence failed or did not complete
        """
        with self._lock:
            if self.state in ("created", "stopped"):
                return self.persist_code
            host = self.host
            if self.state != "running" or host is None:
                self.state = "stopped"
                return self.persist_code
            self.state = "stopping"
            host.write_file(self._file("stop"), "stop\n")
            deadline = monotonic() + self.config.stop_timeout
            done = None
            while True:
                done = host.read_file(self._file("done"))
                if done is not None and done.strip():
                    break
                if not self._job_alive(host) or monotonic() >= deadline:
                    done = host.read_file(self._file("done"))
                    break
                sleep(self.config.poll_interval)
            self.state = "stopped"
            if done is None or not done.strip():
                self._cancel(host)
                self.persist_code = 1
                raise RuntimeError("BeeOND volume %s (job %s) ended without confirming persistence"
                                   % (self.name, self.job_id))
            try:
                self.persist_code = int(done.strip().splitlines()[0])
            except ValueError:
                self.persist_code = 1
            if self.persist_code:
                raise RuntimeError("BeeOND volume %s persistence failed with code %s; see %s"
                                   % (self.name, self.persist_code, self._file("beeond_persist.status")))
            self._log("info", "BeeOND volume %s persisted to %s", self.name, self.persist_dir())
            return self.persist_code

    def task_prologue(self) -> str:
        """Launcher prologue of a task that runs inside the holder allocation."""
        script = "\n# BeeOND on-demand file system (workflow scope, volume %s)\n" % self.name
        script += "export DAGON_BEEOND_SCOPE=workflow\n"
        script += "export DAGON_BEEOND_VOLUME=" + quote(self.name) + "\n"
        script += "DAGON_BEEOND=" + quote(self.mount or "") + "\nexport DAGON_BEEOND\n"
        script += ("if [ ! -d \"$DAGON_BEEOND\" ]; then\n"
                   "  echo \"DAGonStar: BeeOND mount $DAGON_BEEOND is not visible on $(hostname)\" >&2\n"
                   "  exit 1\nfi\n")
        if self.config.persist:
            script += "export DAGON_BEEOND_PERSIST_DIR=" + quote(self.persist_dir()) + "\n"
            if self.config.persist_each_task:
                script += persist_function_script(self.config, self.persist_dir(), self.state_dir())
        return script + "\n"

    def task_epilogue(self) -> str:
        if self.config.persist and self.config.persist_each_task:
            return ("\n# Persist the shared BeeOND volume after this task\n"
                    "dagon_beeond_persist || code=1\n")
        return ""

    def metadata(self) -> Dict[str, Any]:
        """Return credential-free provenance metadata."""
        return {"scope": "workflow", "volume": self.name, "comment": self.config.comment,
                "persist": self.config.persist, "persist_dir": self.persist_dir() if self.config.persist else None,
                "verify": self.config.verify, "job_id": self.job_id, "mount": self.mount}

    def _log(self, level: str, message: str, *args: Any) -> None:
        logger = getattr(self.workflow, "logger", None)
        if logger is not None:
            getattr(logger, level)(message, *args)


BeeONDSpec = Union[None, bool, str, Mapping[str, Any], BeeONDConfig, BeeONDVolume]


def resolve(spec: BeeONDSpec, workflow: Any) -> Union[None, BeeONDConfig, BeeONDVolume]:
    """Resolve a task ``beeond`` argument against *workflow*.

    Accepted values: ``None``/``False`` (disabled), ``True`` or ``"task"``,
    ``"workflow"`` or ``"workflow:<volume>"``, a mapping of
    :class:`BeeONDConfig` options, a :class:`BeeONDConfig`, or a
    :class:`BeeONDVolume`.  Task-scope results are :class:`BeeONDConfig`
    instances; workflow-scope results are the workflow's :class:`BeeONDVolume`.
    """
    if spec is None or spec is False:
        return None
    if isinstance(spec, BeeONDVolume):
        return spec
    defaults = workflow_defaults(workflow)
    if spec is True:
        config = replace(defaults, scope="task")
    elif isinstance(spec, str):
        text = spec.strip()
        if text == "task":
            config = replace(defaults, scope="task")
        elif text == "workflow" or text.startswith("workflow:"):
            name = text.split(":", 1)[1] if ":" in text else DEFAULT_VOLUME
            return workflow.get_beeond_volume(name or DEFAULT_VOLUME)
        else:
            raise ValueError("Unknown BeeOND specification: %r" % spec)
    elif isinstance(spec, BeeONDConfig):
        config = spec
    elif isinstance(spec, Mapping):
        options = dict(spec)
        config = defaults.with_options(**options)
        if config.scope == "workflow":
            existing = getattr(workflow, "beeond_volumes", {}).get(config.volume)
            if existing is not None:
                if set(options) - {"scope", "volume"}:
                    raise ValueError("BeeOND volume %r already exists; configure it once with "
                                     "Workflow.create_beeond_volume" % config.volume)
                return existing
    else:
        raise TypeError("Unsupported BeeOND specification: %r" % (spec,))
    if config.scope == "workflow":
        existing = getattr(workflow, "beeond_volumes", {}).get(config.volume)
        if existing is not None:
            return existing
        return workflow.add_beeond_volume(BeeONDVolume(workflow, config))
    return config
