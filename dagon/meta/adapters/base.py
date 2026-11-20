"""Adapter interface and registry that homogenise external workflow engines.

An adapter is the only engine-specific code a meta-task needs.  It never
modifies the engine: it translates the engine-neutral run context
(:class:`dagon.meta.models.MetaRunContext`) into the engine's *own* command
line and parameter files, and, when the engine reports them, maps the
engine's named outputs back to local paths.

Writing an adapter::

    from dagon.meta import MetaEngineAdapter, EngineInvocation, register_adapter

    class MyEngineAdapter(MetaEngineAdapter):
        name = "myengine"
        executable = "myengine"

        def prepare(self, context):
            params = context.write_json("myengine-params.json", context.parameters)
            return EngineInvocation(
                argv=[self.resolve_executable(context), "run", context.workflow, "--params", str(params)],
                cwd=context.run_dir)

    register_adapter("myengine", MyEngineAdapter)

Installed packages can also declare adapters in the ``dagon.meta_adapters``
entry-point group.  Built-in names are protected.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from importlib import import_module
from typing import Any, Dict, List, Mapping, Optional, Sequence, Type

from dagon.meta.models import (EngineCapabilities, EngineInvocation, EngineResult, MetaEngineFailedError,
                               MetaEngineUnavailableError, MetaRunContext, MetaTimeoutError, MetaValidationError)

LOGGER = logging.getLogger("dagon.meta")

ENTRY_POINT_GROUP = "dagon.meta_adapters"
_OUTPUT_TAIL = 4000


class MetaEngineAdapter(ABC):
    """Base class of every workflow-engine adapter.

    Subclasses set :attr:`name` and usually :attr:`executable`, and implement
    :meth:`prepare`.  Everything else has a working default:

    * :meth:`validate` - static checks of the specification (no engine call);
    * :meth:`unavailable_reason` - why the engine cannot run on this host;
    * :meth:`execute` - run the prepared argument vector (no shell) with the
      task timeout and capture its output;
    * :meth:`collect_outputs` - map engine-reported output names to paths;
    * :meth:`version` - best-effort engine version for provenance.
    """

    #: Registered, lower-case engine name used in ``MetaTask(engine=...)``.
    name = "adapter"
    #: Default executable looked up on ``PATH``; ``engine_options["executable"]``
    #: or the ``[meta.<engine>] executable`` configuration key override it.
    executable: Optional[str] = None
    #: Engine options this adapter understands (``executable``, ``arguments``
    #: and ``version_command`` are accepted by every adapter).
    options: Sequence[str] = ()
    #: Arguments appended to the executable to print its version.
    version_arguments: Sequence[str] = ("--version",)

    COMMON_OPTIONS = ("executable", "arguments")

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities()

    # -- static validation -------------------------------------------------

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        """Reject options this adapter does not understand.  Must not call the engine."""
        unknown = set(engine_options) - set(self.options) - set(self.COMMON_OPTIONS)
        if unknown:
            raise MetaValidationError("unknown %s engine option(s): %s" % (self.name, ", ".join(sorted(unknown))))
        arguments = engine_options.get("arguments", [])
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise MetaValidationError("meta-task engine option 'arguments' must be a list of strings")

    # -- runtime -----------------------------------------------------------

    def resolve_executable(self, context: MetaRunContext) -> str:
        """Return the absolute engine executable, or raise :class:`MetaEngineUnavailableError`."""
        configured = context.option("executable", self.executable)
        if not configured:
            raise MetaEngineUnavailableError("the %s adapter has no executable" % self.name)
        found = shutil.which(str(configured), path=context.environment.get("PATH", os.environ.get("PATH")))
        if found is None:
            raise MetaEngineUnavailableError(
                "the %s engine executable %r was not found; install the engine or set engine_options"
                "['executable'] (the engine itself is never modified by DAGonStar)" % (self.name, configured))
        return found

    def unavailable_reason(self, context: MetaRunContext) -> Optional[str]:
        """Return why the engine cannot run here, or ``None`` when it can."""
        if self.executable is None and "executable" not in context.engine_options:
            return None
        try:
            self.resolve_executable(context)
        except MetaEngineUnavailableError as exc:
            return str(exc)
        return None

    @abstractmethod
    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        """Write the engine-native parameter files and return the engine command."""

    def execute(self, context: MetaRunContext, invocation: EngineInvocation) -> EngineResult:
        """Run *invocation* without a shell; raise on timeout or non-zero status."""
        environment = dict(os.environ)
        environment.update(context.environment)
        environment.update(invocation.environment)
        started = time.time()
        try:
            completed = subprocess.run([str(item) for item in invocation.argv], cwd=str(invocation.cwd),
                                       env=environment, text=True, capture_output=True,
                                       timeout=context.timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            self._write_logs(context, _text(exc.stdout), _text(exc.stderr))
            raise MetaTimeoutError("the %s engine exceeded the %ss timeout" % (self.name, context.timeout)) from exc
        except OSError as exc:
            raise MetaEngineUnavailableError("the %s engine could not be started: %s" % (self.name, exc)) from exc
        result = EngineResult(completed.returncode, completed.stdout, completed.stderr, time.time() - started)
        self._write_logs(context, completed.stdout, completed.stderr)
        if completed.returncode:
            tail = (completed.stderr or completed.stdout or "")[-_OUTPUT_TAIL:]
            raise MetaEngineFailedError("the %s engine exited with status %s: %s"
                                        % (self.name, completed.returncode, tail.strip()), completed.returncode)
        return result

    def collect_outputs(self, context: MetaRunContext, result: EngineResult) -> Dict[str, str]:
        """Return output name -> local path for outputs the engine reported by name."""
        return {}

    def version(self, context: MetaRunContext) -> Optional[str]:
        """Return the engine version string, or ``None`` when it cannot be determined."""
        try:
            argv = [self.resolve_executable(context)] + list(self.version_arguments)
            completed = subprocess.run(argv, text=True, capture_output=True, timeout=60,
                                       stdin=subprocess.DEVNULL, cwd=str(context.workdir))
        except Exception:
            return None
        text = (completed.stdout or completed.stderr or "").strip()
        return _first_version(text)

    @staticmethod
    def _write_logs(context: MetaRunContext, stdout: str, stderr: str) -> None:
        context.metadata_dir.mkdir(parents=True, exist_ok=True)
        (context.metadata_dir / "engine_stdout.txt").write_text(stdout or "", encoding="utf-8")
        (context.metadata_dir / "engine_stderr.txt").write_text(stderr or "", encoding="utf-8")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _first_version(text: str) -> Optional[str]:
    # Skip digits glued to words or paths (``python3.12``, ``/lib/3.1``).
    match = re.search(r"(?<![\w./-])\d+(?:\.\d+)+(?:[-.+]?[A-Za-z0-9]+)*", text)
    return match.group(0) if match else (text.splitlines()[0][:120] if text else None)


def python_executable(context: MetaRunContext) -> str:
    """The Python interpreter used by Python-based engines (``engine_options['python']``)."""
    return str(context.option("python", context.python or sys.executable))


# -- registry ----------------------------------------------------------------

#: Built-in adapters, imported lazily so that engines stay optional.
BUILTIN_ADAPTERS: Dict[str, str] = {
    "mock": "dagon.meta.adapters.mock:MockAdapter",
    "command": "dagon.meta.adapters.command:CommandAdapter",
    "nextflow": "dagon.meta.adapters.nextflow:NextflowAdapter",
    "snakemake": "dagon.meta.adapters.snakemake:SnakemakeAdapter",
    "parsl": "dagon.meta.adapters.parsl:ParslAdapter",
    "streamflow": "dagon.meta.adapters.streamflow:StreamFlowAdapter",
    "cwl": "dagon.meta.adapters.cwl:CWLAdapter",
}

_REGISTERED: Dict[str, Type[MetaEngineAdapter]] = {}
_ENTRY_POINTS_LOADED = False


def register_adapter(name: str, implementation: Type[MetaEngineAdapter],
                     replace: bool = False) -> Type[MetaEngineAdapter]:
    """Register *implementation* under *name* (case-insensitive) and return it.

    This is the only step a new engine needs: neither DAGonStar nor the
    engine is modified.  Built-in names cannot be replaced.
    """
    key = str(name).lower()
    if not re.match(r"^[a-z0-9][a-z0-9._-]*$", key):
        raise ValueError("meta adapter names may contain letters, digits, '.', '_' and '-'")
    if not (isinstance(implementation, type) and issubclass(implementation, MetaEngineAdapter)):
        raise TypeError("meta adapters must subclass dagon.meta.MetaEngineAdapter")
    if key in BUILTIN_ADAPTERS:
        raise ValueError("the built-in meta adapter %r cannot be replaced" % key)
    if key in _REGISTERED and not replace and _REGISTERED[key] is not implementation:
        raise ValueError("a meta adapter named %r is already registered" % key)
    _REGISTERED[key] = implementation
    return implementation


def unregister_adapter(name: str) -> None:
    """Remove a non-built-in adapter (mainly for tests)."""
    _REGISTERED.pop(str(name).lower(), None)


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    try:
        from importlib.metadata import entry_points
        found = entry_points()
        group = (found.select(group=ENTRY_POINT_GROUP) if hasattr(found, "select")
                 else found.get(ENTRY_POINT_GROUP, ()))
    except Exception as exc:  # pragma: no cover - broken metadata must not break workflows
        LOGGER.warning("meta adapter entry points could not be listed: %s", exc)
        return
    for entry in group:
        key = entry.name.lower()
        if key in BUILTIN_ADAPTERS or key in _REGISTERED:
            continue
        try:
            register_adapter(key, entry.load())
        except Exception as exc:
            LOGGER.warning("meta adapter %s could not be loaded: %s", entry.name, exc)


def adapter_names() -> List[str]:
    _load_entry_points()
    return sorted(set(BUILTIN_ADAPTERS) | set(_REGISTERED))


def adapter_exists(name: str) -> bool:
    key = str(name).lower()
    if key in BUILTIN_ADAPTERS or key in _REGISTERED:
        return True
    _load_entry_points()
    return key in _REGISTERED


def get_adapter(name: str) -> MetaEngineAdapter:
    """Return a fresh adapter instance for engine *name*."""
    key = str(name).lower()
    if key in BUILTIN_ADAPTERS:
        module_name, class_name = BUILTIN_ADAPTERS[key].split(":")
        return getattr(import_module(module_name), class_name)()
    if key not in _REGISTERED:
        _load_entry_points()
    if key not in _REGISTERED:
        raise MetaValidationError("unknown meta-task engine %r; choose from %s" % (name, ", ".join(adapter_names())))
    return _REGISTERED[key]()
