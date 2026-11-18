"""Common, opt-in lifecycle for ad-hoc file systems and data stores.

The providers intentionally remain external programs.  DAGonStar owns only
their invocation, readiness checks, shutdown, and the credential-free task
environment; it does not vendor or modify DAGonFS, BeeOND, Hercules, CAPIO, or
DynoStore.

Every bound task receives the provider-neutral variables

``DAGON_ADHOC_PROVIDER``, ``DAGON_ADHOC_NAME``, ``DAGON_ADHOC_PATH``,
``DAGON_ADHOC_ACCESS``

plus ``DAGON_ADHOC_<NAME>_PATH`` and ``DAGON_ADHOC_<NAME>_ACCESS`` so that a
task bound to several resources can address each one.  ``DAGON_ADHOC_ACCESS``
states how the path is used:

``posix``
    an ordinary mounted directory (DAGonFS FUSE3, BeeOND);
``preload``
    paths below ``DAGON_ADHOC_PATH`` are intercepted by a preloaded library
    (Hercules, CAPIO, DAGonFS preload); other paths are unaffected;
``client``
    the resource is reached through a client protocol (DAGonFS native socket);
``object``
    an object store addressed by keys within a catalog (DynoStore).
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import pickle
import pickletools
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from abc import ABC
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

LOGGER = logging.getLogger("dagon.adhoc")

ACCESS_MODES = ("posix", "preload", "client", "object")

# Object keys accepted by the DynoStore catalog service (pub_sub/.htaccess):
# other keys are stored by the gateway but rejected when catalogued.
DYNOSTORE_KEY = re.compile(r"[0-9A-Za-z-]{32,256}\Z")
_SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|PRIVATE)", re.I)
_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AdHocFileSystemError(RuntimeError):
    """An ad-hoc file-system lifecycle operation failed."""


def _argv(value: Sequence[str], option: str) -> List[str]:
    if isinstance(value, (str, bytes)):
        raise ValueError("%s must be a sequence of arguments, not a string" % option)
    result = [str(item) for item in value]
    if not result or any(not item for item in result):
        raise ValueError("%s must be a non-empty command" % option)
    return result


def _variable_suffix(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def preload_variable() -> str:
    """The dynamic-loader interposition variable of the submitting platform."""
    return "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"


def _wait(predicate: Callable[[], bool], timeout: float, alive: Callable[[], bool] = lambda: True,
          interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        if not alive():
            return predicate()
        time.sleep(interval)
    return predicate()


class AdHocFileSystem(ABC):
    """Provider-neutral workflow resource.

    Instances are created by :meth:`dagon.Workflow.create_adhoc_filesystem`
    and attached to tasks with :meth:`bind`.  Providers either own a workflow
    process (DAGonFS, CAPIO), run deployment commands (Hercules, a managed
    DynoStore), or delegate lifecycle to the scheduler (BeeOND).
    """

    provider = "generic"
    access = "posix"

    def __init__(self, workflow: Any, name: str = "default") -> None:
        if not name or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", str(name)):
            raise ValueError("ad-hoc file-system names may contain letters, digits, '.', '_' and '-'")
        if self.access not in ACCESS_MODES:
            raise ValueError("unknown access mode %r" % self.access)
        self.workflow = workflow
        self.name = str(name)
        self.tasks: List[Any] = []
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def task_path(self) -> str:
        """Location tasks use; providers override it."""
        return ""

    def bind(self, task: Any) -> Any:
        """Expose this resource to *task* and return the task for fluent use."""
        if task.workflow not in (None, self.workflow):
            raise ValueError("task belongs to a different workflow")
        resources = task.__dict__.setdefault("adhoc_filesystems", [])
        if self not in resources:
            resources.append(self)
        if task not in self.tasks:
            self.tasks.append(task)
        return task

    def start(self) -> None:
        self._started = True

    def stop(self) -> Optional[int]:
        self._started = False
        return None

    def is_ready(self) -> bool:
        """True when the resource can serve tasks; providers refine this."""
        return self.started

    # -- task environment ----------------------------------------------
    def common_environment(self, path: Optional[str] = None) -> Dict[str, str]:
        location = self.task_path if path is None else path
        suffix = _variable_suffix(self.name)
        return {"DAGON_ADHOC_PROVIDER": self.provider, "DAGON_ADHOC_NAME": self.name,
                "DAGON_ADHOC_PATH": location, "DAGON_ADHOC_ACCESS": self.access,
                "DAGON_ADHOC_%s_PATH" % suffix: location,
                "DAGON_ADHOC_%s_ACCESS" % suffix: self.access}

    def provider_environment(self, task: Any) -> Dict[str, str]:
        """Provider-specific variables; never credentials."""
        return {}

    def path_environment(self, task: Any) -> Dict[str, str]:
        """Path-list variables prepended to the task's existing value."""
        return {}

    def path_variables(self) -> Sequence[str]:
        """Provider variables that carry :attr:`task_path` (replaced in emulation)."""
        return ()

    def task_environment(self, task: Any) -> Dict[str, str]:
        environment = self.common_environment()
        environment.update(self.provider_environment(task))
        _check_environment(environment)
        return environment

    def emulated_path(self) -> str:
        """Local directory standing in for a POSIX or preload path in emulation."""
        return os.path.join(self.workflow.get_scratch_dir_base(), ".adhoc-emulated", self.name)

    def portable_environment(self, task: Any) -> Dict[str, str]:
        """Safe emulation environment.

        No provider runs and no library is preloaded.  POSIX and preload paths
        are redirected to a local directory so that commands writing below
        ``$DAGON_ADHOC_PATH`` still run; this is not evidence that the
        external file system ran.
        """
        environment = self.task_environment(task)
        for variable in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES"):
            environment.pop(variable, None)
        if self.access in ("posix", "preload"):
            emulated = self.emulated_path()
            os.makedirs(emulated, exist_ok=True)
            suffix = _variable_suffix(self.name)
            for variable in ("DAGON_ADHOC_PATH", "DAGON_ADHOC_%s_PATH" % suffix, *self.path_variables()):
                environment[variable] = emulated
        environment["DAGON_ADHOC_EMULATED"] = "1"
        return environment

    def metadata(self) -> Dict[str, Any]:
        return {"provider": self.provider, "name": self.name, "scope": "workflow",
                "access": self.access}


def _check_environment(environment: Mapping[str, str]) -> None:
    for key in environment:
        if not _VARIABLE.match(key):
            raise ValueError("invalid environment variable name %r" % key)
        if _SECRET_NAME.search(key):
            raise ValueError("ad-hoc resources must not export credential variables (%s)" % key)


class ProcessFileSystem(AdHocFileSystem):
    """Base for a workflow-scoped child process with readiness and bounded shutdown."""

    def __init__(self, workflow: Any, name: str, start_command: Sequence[str],
                 stop_command: Optional[Sequence[str]] = None,
                 environment: Optional[Mapping[str, str]] = None,
                 cwd: Optional[str] = None, startup_delay: float = 0.0,
                 startup_timeout: float = 30.0, log: Optional[str] = None) -> None:
        super().__init__(workflow, name)
        self.start_command = _argv(start_command, "start_command")
        self.stop_command = _argv(stop_command, "stop_command") if stop_command else None
        self.environment = {str(key): str(value) for key, value in (environment or {}).items()}
        self.cwd = str(cwd) if cwd is not None else None
        self.startup_delay = float(startup_delay)
        if self.startup_delay < 0:
            raise ValueError("startup_delay must not be negative")
        self.startup_timeout = float(startup_timeout)
        if self.startup_timeout <= 0:
            raise ValueError("startup_timeout must be positive")
        self.log_path = log
        self._process: Optional[subprocess.Popen] = None
        self._log = None

    def default_log_path(self) -> str:
        return os.path.join(self.workflow.get_scratch_dir_base(),
                            ".adhoc-%s-%s.log" % (self.provider, self.name))

    def _environment(self) -> Dict[str, str]:
        environment = os.environ.copy()
        environment.update(self.environment)
        return environment

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def is_ready(self) -> bool:
        return self.running

    def prepare(self) -> None:
        """Create directories needed before the process starts."""

    def start(self) -> None:
        if self.started or self.workflow.portable_emulation:
            return
        self.prepare()
        log_path = self.log_path or self.default_log_path()
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        self._log = open(log_path, "w", encoding="utf-8")
        try:
            self._process = subprocess.Popen(self.start_command, cwd=self.cwd, env=self._environment(),
                                             text=True, stdout=self._log, stderr=subprocess.STDOUT)
        except OSError as exc:
            self._close_log()
            raise AdHocFileSystemError("%s could not be started: %s" % (self.provider, exc)) from exc
        if self.startup_delay:
            time.sleep(self.startup_delay)
        # From here on stop() must clean up whatever was started.
        self._started = True
        if not _wait(self.is_ready, self.startup_timeout, lambda: self.running) or not self.running:
            status = self._process.poll() if self._process is not None else None
            try:
                self.stop()
            except AdHocFileSystemError:
                pass
            detail = ("exited during startup with status %s" % status if status is not None
                      else "was not ready within %.1f seconds" % self.startup_timeout)
            raise AdHocFileSystemError("%s %s; see %s" % (self.provider, detail, log_path))

    def request_shutdown(self) -> None:
        """Provider-specific graceful shutdown before the process is terminated."""

    def stop(self) -> Optional[int]:
        if not self.started:
            return None
        result = 0
        try:
            if self.running:
                self.request_shutdown()
            if self.stop_command is not None:
                completed = subprocess.run(self.stop_command, cwd=self.cwd, env=self._environment(),
                                           check=False, stdout=self._log or subprocess.DEVNULL,
                                           stderr=subprocess.STDOUT)
                result = completed.returncode
            if self._process is not None:
                try:
                    self._process.wait(timeout=self.stop_grace())
                except subprocess.TimeoutExpired:
                    self._process.send_signal(signal.SIGTERM)
                    try:
                        self._process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait()
        finally:
            self._process = None
            self._started = False
            self._close_log()
        if result:
            raise AdHocFileSystemError("%s stop command failed with status %s" % (self.provider, result))
        return result

    def stop_grace(self) -> float:
        """Seconds the process may take to exit by itself after a shutdown request."""
        return 0.0 if self.stop_command is None else 10.0

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None


# -- DAGonFS -------------------------------------------------------------------

_NATIVE_REQUEST = struct.Struct("=IHHIIIiI4xqq")
_NATIVE_REPLY = struct.Struct("=IHHiIqQQIIIIqqq")
_NATIVE_MAGIC, _NATIVE_VERSION, _NATIVE_STAT, _NATIVE_SHUTDOWN = 0x44474653, 2, 6, 12


def dagonfs_native_request(socket_path: str, opcode: int, path: str = "", timeout: float = 5.0) -> int:
    """Send one DAGonFS native-protocol (version 2) request; return the reply's errno.

    Only the two requests DAGonStar needs (``STAT`` for readiness and
    ``SHUTDOWN``) are implemented; data access belongs to DAGonFS's own
    ``python -m dagonfs`` client.
    """
    encoded = path.encode()
    header = _NATIVE_REQUEST.pack(_NATIVE_MAGIC, _NATIVE_VERSION, opcode, len(encoded), 0, 0, 0, 0, 0, 0)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(socket_path)
        connection.sendall(header + encoded)
        reply = b""
        while len(reply) < _NATIVE_REPLY.size:
            chunk = connection.recv(_NATIVE_REPLY.size - len(reply))
            if not chunk:
                raise OSError(errno.EPROTO, "DAGonFS closed the connection")
            reply += chunk
    fields = _NATIVE_REPLY.unpack(reply)
    if fields[0] != _NATIVE_MAGIC or fields[1] != _NATIVE_VERSION:
        raise OSError(errno.EPROTO, "unexpected DAGonFS native reply")
    return fields[3]


class DAGonFS(ProcessFileSystem):
    """MPI DAGonFS volume through its FUSE3, native-socket, or preload frontend."""

    provider = "dagonfs"
    FRONTENDS = ("fuse3", "native", "preload")

    def __init__(self, workflow: Any, name: str = "default", mountpoint: Optional[str] = None,
                 model: str = "client-server", ranks: int = 2, executable: str = "dagonfs",
                 mpirun: str = "mpirun", mpirun_args: Iterable[str] = (),
                 frontend: str = "fuse3", preload_library: Optional[str] = None,
                 preload_root: str = "/dagonfs", python_path: Optional[str] = None,
                 config: Optional[str] = None, startup_delay: float = 0.0,
                 startup_timeout: float = 30.0, log: Optional[str] = None) -> None:
        if model not in ("client-server", "peer-to-peer"):
            raise ValueError("DAGonFS model must be 'client-server' or 'peer-to-peer'")
        if frontend not in self.FRONTENDS:
            raise ValueError("DAGonFS frontend must be one of %s" % ", ".join(self.FRONTENDS))
        if frontend != "fuse3" and model != "client-server":
            raise ValueError("the DAGonFS native and preload frontends serve only client-server volumes")
        if int(ranks) < 1:
            raise ValueError("DAGonFS ranks must be positive")
        if not str(preload_root).startswith("/"):
            raise ValueError("DAGonFS preload_root must be absolute")
        if frontend == "preload" and not preload_library:
            raise ValueError("the DAGonFS preload frontend needs preload_library")
        self.model = model
        self.ranks = int(ranks)
        self.frontend = frontend
        self.access = {"fuse3": "posix", "native": "client", "preload": "preload"}[frontend]
        default = ".dagonfs-%s" % name + ("" if frontend == "fuse3" else ".sock")
        root = mountpoint or os.path.join(workflow.get_scratch_dir_base(), default)
        if frontend != "fuse3" and len(os.fsencode(root)) >= 104:
            raise ValueError("DAGonFS socket path is too long for a Unix socket: %s" % root)
        self.mountpoint = str(Path(root))
        self.preload_library = preload_library
        self.preload_root = str(preload_root).rstrip("/") or "/"
        self.python_path = python_path
        self.config = config
        command = [mpirun, "-np", str(self.ranks), *list(mpirun_args), executable, "--model", model]
        if frontend != "fuse3":
            command += ["--frontend", frontend]
        if config:
            command += ["--config", config]
        command += ["-f", self.mountpoint]
        super().__init__(workflow, name, command, startup_delay=startup_delay,
                         startup_timeout=startup_timeout, log=log)

    @property
    def socket_path(self) -> Optional[str]:
        return None if self.frontend == "fuse3" else self.mountpoint

    @property
    def task_path(self) -> str:
        """FUSE mount of rank 0, the socket (native), or the intercepted prefix (preload)."""
        if self.frontend == "native":
            return self.mountpoint
        if self.frontend == "preload":
            return self.preload_root
        return self.mountpoint if self.model == "client-server" else os.path.join(self.mountpoint, "0")

    def prepare(self) -> None:
        if self.frontend == "fuse3":
            Path(self.mountpoint).mkdir(parents=True, exist_ok=True)
            if self.model == "peer-to-peer":
                for rank in range(self.ranks):
                    Path(self.mountpoint, str(rank)).mkdir(exist_ok=True)
        else:
            Path(self.mountpoint).parent.mkdir(parents=True, exist_ok=True)

    def is_ready(self) -> bool:
        if not self.running:
            return False
        if self.frontend == "fuse3":
            return os.path.ismount(self.task_path)
        if not os.path.exists(self.mountpoint):
            return False
        try:
            return dagonfs_native_request(self.mountpoint, _NATIVE_STAT, "/") == 0
        except OSError:
            return False

    def request_shutdown(self) -> None:
        if self.frontend == "fuse3":
            # Unmounting the frontend initiates DAGonFS's coordinated shutdown;
            # terminating MPI first can leave a stale FUSE mount behind.
            mounts = [self.task_path] if self.model == "client-server" else [
                os.path.join(self.mountpoint, str(rank)) for rank in range(self.ranks)]
            for mount in mounts:
                if os.path.ismount(mount):
                    subprocess.run(_unmount_command(mount), check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                dagonfs_native_request(self.mountpoint, _NATIVE_SHUTDOWN, timeout=30.0)
            except OSError as exc:
                LOGGER.warning("DAGonFS shutdown request failed: %s", exc)

    def stop_grace(self) -> float:
        return 30.0

    def stop(self) -> Optional[int]:
        try:
            return super().stop()
        finally:
            # A volume killed after the grace period leaves a stale mount behind.
            if self.frontend == "fuse3" and os.path.ismount(self.task_path):
                subprocess.run(_unmount_command(self.task_path), check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def provider_environment(self, task: Any) -> Dict[str, str]:
        environment = {"DAGONFS_FRONTEND": self.frontend}
        if self.frontend == "fuse3":
            environment["DAGONFS_MOUNTPOINT"] = self.task_path
        else:
            environment["DAGONFS_SOCKET"] = self.mountpoint
        if self.frontend == "preload":
            environment["DAGONFS_PRELOAD_ROOT"] = self.preload_root
            environment[preload_variable()] = str(self.preload_library)
        if self.python_path:
            environment["DAGONFS_PYTHON"] = str(self.python_path)
        return environment

    def path_variables(self) -> Sequence[str]:
        return ("DAGONFS_MOUNTPOINT", "DAGONFS_PRELOAD_ROOT")

    def portable_environment(self, task: Any) -> Dict[str, str]:
        environment = super().portable_environment(task)
        if self.frontend == "native":
            # Without a server, emulate the socket-backed namespace as a directory.
            emulated = self.emulated_path()
            os.makedirs(emulated, exist_ok=True)
            environment["DAGON_ADHOC_PATH"] = emulated
            environment["DAGON_ADHOC_%s_PATH" % _variable_suffix(self.name)] = emulated
            environment["DAGON_ADHOC_ACCESS"] = "posix"
            environment.pop("DAGONFS_SOCKET", None)
        return environment

    def metadata(self) -> Dict[str, Any]:
        return dict(super().metadata(), path=self.task_path, model=self.model, ranks=self.ranks,
                    frontend=self.frontend)


def _unmount_command(path: str) -> List[str]:
    if sys.platform == "darwin":
        return ["umount", path]
    return [shutil.which("fusermount3") or shutil.which("fusermount") or "fusermount3", "-u", path]


# -- CAPIO ---------------------------------------------------------------------

class Capio(ProcessFileSystem):
    """CAPIO server plus per-task POSIX interception environment.

    CAPIO intercepts paths below ``CAPIO_DIR``.  ``CAPIO_WORKFLOW_NAME`` must
    match the ``name`` of the CAPIO-CL configuration and ``CAPIO_APP_NAME`` the
    step names of its ``IO_Graph``; both are derived from the configuration
    when it is readable.  Without a configuration the server and the tasks
    share the DAGonStar workflow name.  The server is ready once its log shows
    ``ready_marker`` and is stopped with ``SIGTERM``.
    """

    provider = "capio"
    access = "preload"

    def __init__(self, workflow: Any, name: str = "default", directory: Optional[str] = None,
                 server: str = "capio_server", library: str = "libcapio_posix.so",
                 library_dir: Optional[str] = None, config: Optional[str] = None, server_args: Iterable[str] = (),
                 server_launcher: Sequence[str] = (), backend: Optional[str] = None, backend_options: Optional[str] = None,
                 mem_only: bool = False, workflow_name: Optional[str] = None,
                 app_names: Optional[Mapping[str, str]] = None,
                 environment: Optional[Mapping[str, str]] = None,
                 ready_marker: Optional[str] = "Server instance successfully started",
                 startup_delay: float = 0.2, startup_timeout: float = 30.0,
                 log: Optional[str] = None) -> None:
        self.ready_marker = ready_marker
        self.directory = str(directory or os.path.join(workflow.get_scratch_dir_base(), ".capio-" + name))
        self.library = library
        # libcapio_posix depends on libsyscall_intercept from the same installation.
        self.library_dir = library_dir
        self.config = config
        self.backend = backend
        self.app_names = dict(app_names or {})
        self.graph_steps = None
        declared = None
        if config and os.path.isfile(config):
            with open(config, encoding="utf-8") as stream:
                document = json.load(stream)
            declared = document.get("name")
            self.graph_steps = {step.get("name") for step in document.get("IO_Graph", [])
                                if isinstance(step, dict)}
        if workflow_name and declared and workflow_name != declared:
            raise ValueError("CAPIO workflow_name %r differs from the configuration name %r"
                             % (workflow_name, declared))
        self.capio_workflow_name = workflow_name or declared or workflow.name
        if isinstance(server_launcher, str):
            raise ValueError("server_launcher must be a sequence of arguments")
        # For example ["srun", "--ntasks-per-node=1"]: CAPIO needs one server per node.
        command = [*[str(item) for item in server_launcher], server,
                   *(["-c", config] if config else ["--no-config"])]
        if backend:
            command += ["--backend", backend]
        if backend_options:
            command += ["--backend-options", backend_options]
        if mem_only:
            command.append("--mem-only")
        command += list(server_args)
        server_environment = dict(environment or {})
        server_environment["CAPIO_DIR"] = self.directory
        # Without a configuration the server names its shared-memory channels
        # after CAPIO_WORKFLOW_NAME (default "CAPIO"); clients must use the same
        # name or they wait forever.
        server_environment["CAPIO_WORKFLOW_NAME"] = self.capio_workflow_name
        super().__init__(workflow, name, command, environment=server_environment,
                         startup_delay=startup_delay, startup_timeout=startup_timeout, log=log)

    @property
    def task_path(self) -> str:
        return self.directory

    def app_name(self, task: Any) -> str:
        return self.app_names.get(getattr(task, "name", ""), getattr(task, "name", "default_app"))

    def bind(self, task: Any) -> Any:
        if self.graph_steps is not None and self.app_name(task) not in self.graph_steps:
            LOGGER.warning("CAPIO app %r is not a step of the IO_Graph in %s",
                           self.app_name(task), self.config)
        return super().bind(task)

    def prepare(self) -> None:
        Path(self.directory).mkdir(parents=True, exist_ok=True)

    def is_ready(self) -> bool:
        """The server is running and, when a marker is set, has logged it."""
        if not self.running:
            return False
        if not self.ready_marker:
            return True
        if self._log is not None:
            self._log.flush()
        try:
            with open(self.log_path or self.default_log_path(), encoding="utf-8", errors="replace") as stream:
                return self.ready_marker in stream.read()
        except OSError:
            return False

    def provider_environment(self, task: Any) -> Dict[str, str]:
        library = self.library
        if self.library_dir and os.sep not in library:
            library = os.path.join(self.library_dir, library)
        return {"CAPIO_DIR": self.directory, "CAPIO_WORKFLOW_NAME": self.capio_workflow_name,
                "CAPIO_APP_NAME": self.app_name(task), "LD_PRELOAD": library}

    def path_environment(self, task: Any) -> Dict[str, str]:
        return {"LD_LIBRARY_PATH": self.library_dir} if self.library_dir else {}

    def path_variables(self) -> Sequence[str]:
        return ("CAPIO_DIR",)

    def metadata(self) -> Dict[str, Any]:
        return dict(super().metadata(), path=self.directory, configured=self.config is not None,
                    backend=self.backend or "default")


# -- Hercules ------------------------------------------------------------------

def read_hercules_config(path: str) -> Dict[str, str]:
    """Parse Hercules' ``KEY = value`` configuration (comments start with ``#``)."""
    values: Dict[str, str] = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


class Hercules(ProcessFileSystem):
    """Hercules deployment script plus POSIX interception environment.

    ``hercules start`` deploys the metadata and data servers and returns.
    Inside a Slurm allocation the script writes a per-job configuration
    ``<config>_<SLURM_JOB_ID>`` that clients must use; outside Slurm, pass
    ``meta_hostfile`` and ``data_hostfile`` (and optionally ``client_hostfile``).
    The intercepted prefix is the configuration's ``MOUNT_POINT`` (default
    ``/mnt/hercules``).  The deployment script can exit with status 0 after a
    failed deployment, so give ``ready_command`` (for example a listing of the
    mount point, run under the preload library) to confirm the servers answer.
    """

    provider = "hercules"
    access = "preload"

    def __init__(self, workflow: Any, config: str, name: str = "default",
                 launcher: str = "hercules", library: str = "libhercules_posix.so",
                 library_dir: Optional[str] = None, path: Optional[str] = None,
                 meta_hostfile: Optional[str] = None, data_hostfile: Optional[str] = None,
                 client_hostfile: Optional[str] = None, job_id: Optional[str] = None, ready_command: Optional[Sequence[str]] = None,
                 startup_delay: float = 0.0, startup_timeout: float = 120.0,
                 log: Optional[str] = None) -> None:
        if not config:
            raise ValueError("Hercules requires a configuration file")
        if bool(meta_hostfile) != bool(data_hostfile):
            raise ValueError("Hercules needs both meta_hostfile and data_hostfile, or neither")
        self.config = str(config)
        self.library = library
        self.library_dir = library_dir
        settings = read_hercules_config(self.config) if os.path.isfile(self.config) else {}
        mount = path or os.environ.get("HERCULES_MOUNT_POINT") or settings.get("MOUNT_POINT") or "/mnt/hercules"
        self.path = mount.rstrip("/") or "/"
        self.job_id = job_id
        self.ready_command = _argv(ready_command, "ready_command") if ready_command else None
        hosts = ["-m", str(meta_hostfile), "-d", str(data_hostfile)] if meta_hostfile else []
        if client_hostfile:
            hosts += ["-c", str(client_hostfile)]
        self._launcher = launcher
        self._hosts = hosts
        super().__init__(workflow, name, [launcher, "start", *hosts, "-f", self.config],
                         [launcher, "stop", *hosts, "-f", self.config],
                         environment={"HERCULES_CONF": self.config}, startup_delay=startup_delay,
                         startup_timeout=startup_timeout, log=log)

    @property
    def task_path(self) -> str:
        return self.path

    def client_config(self) -> str:
        """Configuration clients load: the per-job copy inside a Slurm allocation."""
        job = self.job_id or os.environ.get("SLURM_JOB_ID")
        if job:
            candidate = "%s_%s" % (self.config, job)
            if self.job_id or os.path.exists(candidate):
                return candidate
        return self.config

    def provider_environment(self, task: Any) -> Dict[str, str]:
        library = self.library
        if self.library_dir and os.sep not in library:
            library = os.path.join(self.library_dir, library)
        return {"HERCULES_CONF": self.client_config(), "HERCULES_MOUNT_POINT": self.path,
                "LD_PRELOAD": library}

    def path_environment(self, task: Any) -> Dict[str, str]:
        return {"LD_LIBRARY_PATH": self.library_dir} if self.library_dir else {}

    def path_variables(self) -> Sequence[str]:
        return ("HERCULES_MOUNT_POINT",)

    def is_ready(self) -> bool:
        if self.ready_command is None:
            return True
        environment = self._environment()
        environment.update(self.provider_environment(None))
        if self.library_dir:
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(
                item for item in (self.library_dir, environment.get("LD_LIBRARY_PATH")) if item)
        return subprocess.run(self.ready_command, env=environment, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    def start(self) -> None:
        """Run Hercules' deployment command, which exits after starting servers."""
        if self.started or self.workflow.portable_emulation:
            return
        log_path = self.log_path or self.default_log_path()
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        self._log = open(log_path, "w", encoding="utf-8")
        try:
            completed = subprocess.run(self.start_command, cwd=self.cwd, env=self._environment(),
                                       check=False, stdout=self._log, stderr=subprocess.STDOUT)
        except OSError as exc:
            self._close_log()
            raise AdHocFileSystemError("Hercules could not be started: %s" % exc) from exc
        if completed.returncode:
            self._close_log()
            raise AdHocFileSystemError("Hercules start command failed with status %s; see %s"
                                       % (completed.returncode, log_path))
        self._started = True
        if not _wait(self.is_ready, self.startup_timeout, interval=1.0):
            try:
                self.stop()
            except AdHocFileSystemError:
                pass
            raise AdHocFileSystemError("Hercules was not ready within %.1f seconds; see %s"
                                       % (self.startup_timeout, log_path))

    def stop(self) -> Optional[int]:
        # ``hercules stop`` ignores Slurm: inside an allocation it must be
        # given the per-job configuration that start wrote, which already names
        # the job's host files.  Host files are passed only without it, because
        # stopping removes hosts from the data host file it is given.
        configuration = self.client_config()
        if configuration != self.config:
            self.stop_command = [self._launcher, "stop", "-f", configuration]
        else:
            self.stop_command = [self._launcher, "stop", *self._hosts, "-f", self.config]
        return super().stop()

    def metadata(self) -> Dict[str, Any]:
        return dict(super().metadata(), path=self.path,
                    hostfiles="explicit" if "-m" in self.start_command else "scheduler")


# -- BeeOND --------------------------------------------------------------------

class BeeOND(AdHocFileSystem):
    """Bridge from the common interface to DAGonStar's Slurm BeeOND support."""

    provider = "beeond"
    access = "posix"

    def __init__(self, workflow: Any, name: str = "default", **options: Any) -> None:
        super().__init__(workflow, name)
        self.volume = workflow.create_beeond_volume(name, **options)

    @property
    def task_path(self) -> str:
        return self.volume.mount or ""

    def bind(self, task: Any) -> Any:
        from dagon.batch import Slurm
        if not isinstance(task, Slurm):
            raise TypeError("BeeOND can only be bound to Slurm tasks")
        task.beeond = self.volume
        task._beeond_resolved = self.volume
        task._beeond_is_resolved = True
        return super().bind(task)

    def task_environment(self, task: Any) -> Dict[str, str]:
        # The BeeOND prologue exports DAGON_BEEOND inside the allocation; the
        # common variables refer to it rather than to a submission-host path.
        return {"DAGON_ADHOC_PROVIDER": self.provider, "DAGON_ADHOC_NAME": self.name,
                "DAGON_ADHOC_ACCESS": self.access}

    def launcher_environment_lines(self) -> List[str]:
        suffix = _variable_suffix(self.name)
        return ['export DAGON_ADHOC_PATH="$DAGON_BEEOND"',
                'export DAGON_ADHOC_%s_PATH="$DAGON_BEEOND"' % suffix,
                'export DAGON_ADHOC_%s_ACCESS=posix' % suffix]

    def portable_environment(self, task: Any) -> Dict[str, str]:
        environment = self.task_environment(task)
        environment["DAGON_ADHOC_EMULATED"] = "1"
        return environment

    def metadata(self) -> Dict[str, Any]:
        return dict(self.volume.metadata(), **super().metadata())


# -- DynoStore -----------------------------------------------------------------

class DynoStore(AdHocFileSystem):
    """DynoStore object-store catalog used as a workflow data space.

    DynoStore has no POSIX mount: tasks address objects by key inside a
    catalog through the ``dynostore`` CLI or client, using ``DYNOSTORE_SERVER``
    and ``DYNOSTORE_CATALOG``.  DAGonStar can either attach to a running
    gateway or manage a Docker Compose deployment (``compose_file``) that it
    brings up before the tasks and down afterwards.

    The user token is a credential: DAGonStar reads it from the environment
    variable named by ``token_env`` only when :meth:`put`, :meth:`get`,
    :meth:`exists`, or :meth:`evict` is called, never exports it to tasks,
    and never records it.  Tasks using the ``dynostore`` CLI authenticate
    through the CLI's own token file.
    """

    provider = "dynostore"
    access = "object"

    def __init__(self, workflow: Any, name: str = "default", server: Optional[str] = None,
                 catalog: Optional[str] = None, token_env: str = "DYNOSTORE_TOKEN",
                 compose_file: Optional[str] = None, compose_project: Optional[str] = None,
                 setup_commands: Sequence[Sequence[str]] = (), docker: str = "docker",
                 startup_timeout: float = 120.0, request_timeout: float = 60.0,
                 resiliency: int = 1) -> None:
        super().__init__(workflow, name)
        if server is None:
            # Reuse the [dynostore] section of dagon.ini (the workflow-wide mover) when present.
            section = (getattr(workflow, "cfg", None) or {}).get("dynostore") or {}
            server = ("%s:%s" % (section["host"], section.get("port", 8095))
                      if section.get("host") else "127.0.0.1:8095")
        server = str(server)
        if "://" in server:
            parsed = urllib.parse.urlsplit(server)
            if parsed.scheme not in ("http", "https") or parsed.path not in ("", "/"):
                raise ValueError("DynoStore server must be host:port or an http(s) origin")
            self.base_url = "%s://%s" % (parsed.scheme, parsed.netloc)
            server = parsed.netloc
        else:
            self.base_url = "http://" + server
        if not server or "/" in server or "@" in server:
            raise ValueError("DynoStore server must be host:port without credentials")
        self.server = server
        self.catalog = str(catalog or workflow.name)
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", self.catalog):
            raise ValueError("DynoStore catalog names may contain letters, digits, '.', '_' and '-'")
        if not _VARIABLE.match(token_env):
            raise ValueError("token_env must be an environment variable name")
        self.token_env = token_env
        self.compose_file = compose_file
        self.compose_project = compose_project
        self.setup_commands = [_argv(command, "setup_commands") for command in setup_commands]
        self.docker = docker
        self.startup_timeout = float(startup_timeout)
        self.request_timeout = float(request_timeout)
        self.resiliency = int(resiliency)
        if self.resiliency < 1:
            raise ValueError("resiliency must be positive")

    @property
    def managed(self) -> bool:
        return self.compose_file is not None

    @property
    def task_path(self) -> str:
        return "dynostore://%s/%s" % (self.server, self.catalog)

    def compose_command(self, *arguments: str) -> List[str]:
        command = [self.docker, "compose", "-f", str(self.compose_file)]
        if self.compose_project:
            command += ["-p", self.compose_project]
        return command + list(arguments)

    def is_ready(self) -> bool:
        """True when the gateway answers HTTP (any status below 500)."""
        try:
            with urllib.request.urlopen(self.base_url + "/", timeout=5) as response:
                return response.status < 500
        except urllib.error.HTTPError as exc:
            return exc.code < 500
        except (OSError, ValueError):
            return False

    def start(self) -> None:
        if self.started or self.workflow.portable_emulation:
            return
        if self.managed:
            cwd = os.path.dirname(os.path.abspath(str(self.compose_file)))
            # Set before "up" so that a failure below still brings the stack down.
            self._started = True
            for command in [self.compose_command("up", "-d")] + self.setup_commands:
                completed = subprocess.run(command, cwd=cwd, check=False,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if completed.returncode:
                    self.stop(raise_errors=False)
                    raise AdHocFileSystemError("DynoStore command %r failed with status %s"
                                               % (" ".join(command[:4]), completed.returncode))
        self._started = True
        if not _wait(self.is_ready, self.startup_timeout, interval=1.0):
            self.stop(raise_errors=False)
            raise AdHocFileSystemError("DynoStore gateway %s did not answer within %.1f seconds"
                                       % (self.server, self.startup_timeout))

    def stop(self, raise_errors: bool = True) -> Optional[int]:
        if not self.started:
            return None
        self._started = False
        if not self.managed:
            return None
        cwd = os.path.dirname(os.path.abspath(str(self.compose_file)))
        completed = subprocess.run(self.compose_command("down"), cwd=cwd, check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if completed.returncode and raise_errors:
            raise AdHocFileSystemError("DynoStore compose down failed with status %s" % completed.returncode)
        return completed.returncode

    def provider_environment(self, task: Any) -> Dict[str, str]:
        # The variable *name* of the token is exported, never its value.
        # DYNOSTORE_SERVER is host:port, as the dynostore CLI's --server expects.
        return {"DYNOSTORE_SERVER": self.server, "DYNOSTORE_URL": self.base_url,
                "DYNOSTORE_CATALOG": self.catalog,
                "DYNOSTORE_AUTH_VARIABLE": self.token_env}

    def portable_environment(self, task: Any) -> Dict[str, str]:
        environment = super().portable_environment(task)
        emulated = self.emulated_path()
        os.makedirs(emulated, exist_ok=True)
        environment["DYNOSTORE_EMULATED_DIR"] = emulated
        return environment

    # -- data operations (REST routes used by the dynostore client) --------
    def client(self) -> "DynoStoreClient":
        return DynoStoreClient(self.base_url, self.catalog, self.token_env,
                               self.request_timeout, self.resiliency)

    def put(self, local: str, key: Optional[str] = None) -> str:
        """Upload *local* into the catalog and return its key."""
        with open(local, "rb") as stream:
            return self.client().put_bytes(stream.read(), key)

    def get(self, key: str, local: str) -> int:
        """Download object *key* to *local*; return its size."""
        data = self.client().get_bytes(key)
        with open(local, "wb") as stream:
            stream.write(data)
        return len(data)

    def exists(self, key: str) -> bool:
        return self.client().exists(key)

    def evict(self, key: str) -> None:
        self.client().evict(key)

    def metadata(self) -> Dict[str, Any]:
        return dict(super().metadata(), path=self.task_path, catalog=self.catalog,
                    managed=self.managed)


class DynoStoreClient:
    """Minimal, dependency-free client for the DynoStore gateway.

    It follows the REST routes and object format of ``dynostore-client``
    (unencrypted objects only).  The token is read from ``token_env`` on every
    request and is never logged: it is a URL path segment, so error messages
    omit URLs.
    """

    def __init__(self, base_url: str, catalog: str, token_env: str = "DYNOSTORE_TOKEN",
                 timeout: float = 60.0, resiliency: int = 1) -> None:
        self.base_url = base_url.rstrip("/")
        self.catalog = catalog
        self.token_env = token_env
        self.timeout = timeout
        self.resiliency = resiliency

    @classmethod
    def from_environment(cls) -> "DynoStoreClient":
        """Client for a task bound to a ``dynostore`` resource."""
        server = os.environ.get("DYNOSTORE_URL") or os.environ.get("DYNOSTORE_SERVER")
        catalog = os.environ.get("DYNOSTORE_CATALOG")
        if not server or not catalog:
            raise AdHocFileSystemError("DYNOSTORE_URL (or DYNOSTORE_SERVER) and DYNOSTORE_CATALOG are not set")
        base = server if "://" in server else "http://" + server
        return cls(base, catalog, os.environ.get("DYNOSTORE_AUTH_VARIABLE", "DYNOSTORE_TOKEN"))

    def _token(self) -> str:
        token = os.environ.get(self.token_env, "")
        if not token or "/" in token:
            raise AdHocFileSystemError("set %s to a DynoStore user token" % self.token_env)
        return urllib.parse.quote(token, safe="")

    def _request(self, method: str, route: str, body: Optional[bytes] = None,
                 content_type: Optional[str] = None, expected: Sequence[int] = (200,)) -> bytes:
        request = urllib.request.Request(self.base_url + route, data=body, method=method)
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status, payload = response.status, response.read()
                encrypted = str(response.headers.get("is_encrypted", "false")).lower() == "true"
        except urllib.error.HTTPError as exc:
            status, payload, encrypted = exc.code, b"", False
        except OSError as exc:
            # Never include the URL: the token is a path segment.
            raise AdHocFileSystemError("DynoStore %s request failed: %s" % (method, exc.__class__.__name__)) from None
        if status not in expected:
            raise AdHocFileSystemError("DynoStore %s request returned HTTP %s" % (method, status))
        if encrypted:
            raise AdHocFileSystemError("DynoStore object is encrypted; use the dynostore client")
        return payload

    def _route(self, *parts: str) -> str:
        return "/" + "/".join(urllib.parse.quote(part, safe="") for part in parts)

    def put_bytes(self, data: bytes, key: Optional[str] = None) -> str:
        """Store *data* in the catalog and return its key."""
        key = key or str(uuid.uuid4())
        if not DYNOSTORE_KEY.match(key):
            raise AdHocFileSystemError("DynoStore object keys are 32-256 letters, digits or hyphens "
                                       "(the catalog service rejects others)")
        token = self._token()
        stored = encode_dynostore_object(data)
        digest = hashlib.sha3_256(data).hexdigest()
        metadata = {"name": digest, "size": len(stored), "hash": digest, "key": key,
                    "is_encrypted": 0, "resiliency": self.resiliency, "nodes": []}
        self._request("POST", "/metadata/%s%s" % (token, self._route(key)), json.dumps(metadata).encode(),
                      "application/json", (200,))
        self._request("PUT", "/upload/%s%s" % (token, self._route(self.catalog, key)), stored,
                      "application/octet-stream", (201,))
        return key

    def get_bytes(self, key: str) -> bytes:
        return decode_dynostore_object(self._request("GET", "/storage/%s%s" % (self._token(), self._route(key))))

    def exists(self, key: str) -> bool:
        try:
            payload = self._request("GET", "/storage/%s%s/exists" % (self._token(), self._route(key)))
        except AdHocFileSystemError as exc:
            if "HTTP 404" in str(exc):
                return False
            raise
        # The metadata service answers 200 with {"exists": false} for a
        # missing or removed object; only an explicit true counts.
        try:
            answer = json.loads(payload.decode("utf-8")) if payload else None
        except (UnicodeDecodeError, ValueError):
            answer = None
        if isinstance(answer, dict) and "exists" in answer:
            return answer["exists"] is True
        return True

    def evict(self, key: str) -> None:
        self._request("DELETE", "/storage/%s%s" % (self._token(), self._route(key)))


def encode_dynostore_object(data: bytes) -> bytes:
    """Encode bytes as ``dynostore-client`` stores them: zlib(pickle(bytes))."""
    return zlib.compress(pickle.dumps(bytes(data), protocol=4), 9)


_PICKLE_BYTES_OPCODES = {"SHORT_BINBYTES", "BINBYTES", "BINBYTES8"}
_PICKLE_FRAMING_OPCODES = {"PROTO", "FRAME", "MEMOIZE", "BINPUT", "LONG_BINPUT", "STOP"}


def decode_dynostore_object(payload: bytes, limit: int = 1 << 34) -> bytes:
    """Decode a ``dynostore-client`` object without unpickling it.

    The pickle stream is walked with :mod:`pickletools`, which never executes
    it, and only a single bytes value is accepted, so a malicious server
    cannot run code here (``pickle.loads`` would allow that).
    """
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(payload, limit)
    except zlib.error as exc:
        raise AdHocFileSystemError("DynoStore object is not zlib-compressed") from exc
    if decompressor.unconsumed_tail:
        raise AdHocFileSystemError("DynoStore object exceeds the decoding limit")
    values = []
    try:
        for opcode, argument, _ in pickletools.genops(raw):
            if opcode.name in _PICKLE_BYTES_OPCODES:
                values.append(argument)
            elif opcode.name not in _PICKLE_FRAMING_OPCODES:
                raise AdHocFileSystemError("DynoStore object holds a %s pickle opcode, not plain bytes"
                                           % opcode.name)
    except (ValueError, EOFError) as exc:
        raise AdHocFileSystemError("DynoStore object is not a valid pickle stream") from exc
    if len(values) != 1:
        raise AdHocFileSystemError("DynoStore object does not hold exactly one bytes value")
    return bytes(values[0])


PROVIDERS = {"dagonfs": DAGonFS, "beeond": BeeOND, "hercules": Hercules, "capio": Capio,
             "dynostore": DynoStore}


def create(workflow: Any, provider: str, name: str = "default", **options: Any) -> AdHocFileSystem:
    """Create a provider by its stable, case-insensitive name."""
    key = str(provider).lower()
    try:
        implementation = PROVIDERS[key]
    except KeyError as exc:
        raise ValueError("unknown ad-hoc file-system provider %r; choose from %s" %
                         (provider, ", ".join(sorted(PROVIDERS)))) from exc
    return implementation(workflow, name=name, **options)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Task-side helper: ``python -m dagon.adhoc dynostore put|get|exists|evict``.

    Server and catalog come from the task environment of a bound ``dynostore``
    resource; the token from the variable it names (default
    ``DYNOSTORE_TOKEN``), which the task inherits from its own environment.
    """
    import argparse
    parser = argparse.ArgumentParser(prog="python -m dagon.adhoc")
    providers = parser.add_subparsers(dest="provider", required=True)
    dyno = providers.add_parser("dynostore").add_subparsers(dest="operation", required=True)
    put = dyno.add_parser("put")
    put.add_argument("local")
    put.add_argument("key", nargs="?")
    get = dyno.add_parser("get")
    get.add_argument("key")
    get.add_argument("local")
    dyno.add_parser("exists").add_argument("key")
    dyno.add_parser("evict").add_argument("key")
    options = parser.parse_args(argv)
    try:
        client = DynoStoreClient.from_environment()
        if options.operation == "put":
            with open(options.local, "rb") as stream:
                print(client.put_bytes(stream.read(), options.key))
        elif options.operation == "get":
            data = client.get_bytes(options.key)
            with open(options.local, "wb") as stream:
                stream.write(data)
        elif options.operation == "exists":
            return 0 if client.exists(options.key) else 1
        else:
            client.evict(options.key)
    except (AdHocFileSystemError, OSError) as exc:
        print("dagon.adhoc: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
