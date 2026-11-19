"""Parsl adapter: run a Parsl program (a Python file) in its own interpreter.

Parsl workflows are Python programs, so the adapter supports both ways such a
program is usually written; neither requires changes to Parsl:

``mode="function"`` (default)
    ``workflow`` is a ``.py`` file defining ``entrypoint`` (default ``main``),
    a function that composes Parsl apps.  The bundled driver
    (``dagon/meta/parsl_driver.py``, run by path) loads a Parsl configuration, calls
    ``entrypoint(**inputs)`` (file inputs are absolute paths), waits for every
    returned future, writes the JSON result to ``.dagon/parsl-result.json``, and
    cleans Parsl up.  The module must not call ``parsl.load()`` at import time
    (the usual ``if __name__ == "__main__":`` guard is enough).

``mode="script"``
    ``workflow`` is a self-contained script that loads its own configuration.
    It runs as ``python <workflow> <arguments>``; the inputs are in the JSON
    document named by ``DAGON_META_PARAMETERS`` and ``arguments`` items may
    use the command adapter placeholders (``{inputs[name]}``, ``{run_dir}``...).

Engine options: ``mode``, ``entrypoint``, ``config`` (``"threads"`` (default),
``"htex_local"``, or ``"path/to/config.py:attribute"`` naming a
``parsl.config.Config`` - for example one with a Slurm provider),
``max_threads`` (threads executor), ``python`` (interpreter that has Parsl),
plus the common ``arguments``.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Optional, Mapping

from dagon.meta.adapters.base import MetaEngineAdapter, python_executable
from dagon.meta.models import (EngineInvocation, EngineResult, MetaRunContext, MetaValidationError,
                               NAME_PATTERN)

DRIVER = Path(__file__).resolve().parent.parent / "parsl_driver.py"


class ParslAdapter(MetaEngineAdapter):
    name = "parsl"
    executable = None
    options = ("mode", "entrypoint", "config", "max_threads", "python")

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        super().validate(workflow, engine_options)
        mode = engine_options.get("mode", "function")
        if mode not in ("function", "script"):
            raise MetaValidationError("parsl engine option 'mode' must be 'function' or 'script'")
        entrypoint = engine_options.get("entrypoint", "main")
        if not isinstance(entrypoint, str) or not NAME_PATTERN.match(entrypoint):
            raise MetaValidationError("parsl engine option 'entrypoint' must be a function name")
        config = engine_options.get("config", "threads")
        if not isinstance(config, str) or not (config in ("threads", "htex_local") or ":" in config):
            raise MetaValidationError("parsl engine option 'config' must be 'threads', 'htex_local', "
                                      "or 'path/to/config.py:attribute'")
        threads = engine_options.get("max_threads", 4)
        if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
            raise MetaValidationError("parsl engine option 'max_threads' must be a positive integer")
        if mode == "script" and ("entrypoint" in engine_options or "config" in engine_options):
            raise MetaValidationError("parsl script mode runs the program as is; 'entrypoint' and 'config' "
                                      "apply only to function mode")

    def unavailable_reason(self, context: MetaRunContext) -> Optional[str]:
        python = python_executable(context)
        try:
            completed = subprocess.run([python, "-c", "import parsl"], capture_output=True, text=True, timeout=120,
                                       stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "the Python interpreter %r for Parsl could not be started: %s" % (python, exc)
        if completed.returncode:
            return ("Parsl is not importable by %r; install it (pip install parsl) or set "
                    "engine_options['python']" % python)
        return None

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        python = python_executable(context)
        parameters = context.write_json("meta-parameters.json", context.parameters)
        if context.option("mode", "function") == "script":
            values = {"workflow": context.workflow, "parameters_file": str(parameters), "run_dir": str(context.run_dir),
                      "workdir": str(context.workdir), "python": python, "inputs": context.parameters}
            try:
                extra = [item.format(**values) for item in context.arguments()]
            except (KeyError, IndexError, ValueError) as exc:
                raise MetaValidationError("invalid placeholder in parsl script arguments: %s" % exc) from exc
            return EngineInvocation(argv=[python, context.workflow] + extra, cwd=context.run_dir,
                                    environment={"DAGON_META_PARAMETERS": str(parameters)},
                                    generated_files=[".dagon/meta-parameters.json"])
        job = context.write_json("parsl-job.json", {
            "workflow": context.workflow, "entrypoint": context.option("entrypoint", "main"),
            "config": context.option("config", "threads"), "max_threads": context.option("max_threads", 4),
            "parameters_file": str(parameters), "run_dir": str(context.run_dir / "runinfo"),
            "result_path": str(context.metadata_dir / "parsl-result.json")})
        # The driver is self-contained (it imports Parsl, never dagon), so it runs by path in an
        # interpreter that has Parsl but not DAGonStar's own dependencies.
        environment = {"DAGON_META_PARAMETERS": str(parameters)}
        return EngineInvocation(argv=[python, str(DRIVER), "--job", str(job)] + context.arguments(),
                                cwd=context.run_dir, environment=environment,
                                generated_files=[".dagon/meta-parameters.json", ".dagon/parsl-job.json",
                                                 ".dagon/parsl-result.json"])

    def execute(self, context: MetaRunContext, invocation: EngineInvocation) -> EngineResult:
        result = super().execute(context, invocation)
        report = context.metadata_dir / "parsl-result.json"
        if report.is_file():
            try:
                document = json.loads(report.read_text(encoding="utf-8"))
                result.metadata["parsl_version"] = document.get("parsl_version")
                result.metadata["apps"] = document.get("apps")
            except ValueError:
                pass
        return result

    def version(self, context: MetaRunContext) -> Optional[str]:
        try:
            completed = subprocess.run([python_executable(context), "-c", "import parsl; print(parsl.__version__)"],
                                       capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return completed.stdout.strip() or None if completed.returncode == 0 else None
