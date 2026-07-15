"""Native Python-function workflow tasks."""

import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

import dagon
from dagon.batch import Slurm
from dagon.shell import join_command
from dagon.task import Task


class NativeTask(Task):
    """Execute an importable Python function in an isolated task scratch directory.

    ``inputs`` binds scalar JSON values or local/``workflow://`` files. ``outputs``
    maps function parameter names to relative output names; each is exposed below
    ``outputs/`` in the scratch directory.
    """

    def __init__(self, name: str, function: Union[str, Any], inputs: Optional[Mapping[str, Any]] = None,
                 outputs: Optional[Mapping[str, str]] = None, executor: str = "local",
                 resources: Optional[Mapping[str, Any]] = None, python: str = sys.executable,
                 working_dir: Optional[str] = None, environment: Optional[Mapping[str, str]] = None,
                 globusendpoint: Optional[str] = None, **_: Any) -> None:
        self.module, self.function_name, self.module_search_path = self._resolve_function(function)
        self.inputs = dict(inputs or {})
        self.outputs = dict(outputs or {})
        self.executor = executor.lower()
        self.resources = dict(resources or {})
        self.python = python
        self.environment = dict(environment or {})
        if self.executor not in ("local", "slurm"):
            raise ValueError("Native executor must be 'local' or 'slurm'")
        self._validate_bindings()
        # The serialized bindings provide a stable command field and dependency source.
        Task.__init__(self, name, json.dumps(self.inputs, sort_keys=True, default=str), working_dir,
                      globusendpoint=globusendpoint)

    @staticmethod
    def _resolve_function(function: Union[str, Any]) -> Tuple[str, str, Optional[str]]:
        if isinstance(function, str):
            if ":" not in function:
                raise ValueError("Native function must use 'module:function' notation")
            module, name = function.split(":", 1)
            if not module or not name:
                raise ValueError("Native function must use 'module:function' notation")
        else:
            module, name = getattr(function, "__module__", None), getattr(function, "__name__", None)
            if not module or not name or "<locals>" in getattr(function, "__qualname__", "") or name == "<lambda>":
                raise ValueError("Native functions must be importable module-level callables")
        try:
            target_module = importlib.import_module(module)
            target = getattr(target_module, name)
        except (ImportError, AttributeError) as exc:
            raise ValueError("Native function is not importable: %s:%s" % (module, name)) from exc
        if not callable(target):
            raise ValueError("Native function is not callable: %s:%s" % (module, name))
        source = inspect.getsourcefile(target)
        if source:
            module_root = Path(source).parent
            for _ in module.split(".")[:-1]:
                module_root = module_root.parent
            search_path = str(module_root)
        else:
            search_path = None
        return module, name, search_path

    @staticmethod
    def _relative(value: str, label: str) -> str:
        item = Path(value)
        if not value or item.is_absolute() or ".." in item.parts:
            raise ValueError("Native %s path must be relative and stay inside scratch: %s" % (label, value))
        return item.as_posix()

    def _validate_bindings(self) -> None:
        for value in self.outputs.values():
            self._relative(value, "output")
        signature = inspect.signature(getattr(importlib.import_module(self.module), self.function_name))
        names = set(self.inputs) | set(self.outputs)
        try:
            signature.bind(**{name: None for name in names})
        except TypeError as exc:
            raise ValueError("Native function bindings are incompatible: %s" % exc) from exc
        for name, value in self.inputs.items():
            if isinstance(value, str) and value.startswith(dagon.Workflow.SCHEMA):
                self._parse_reference(value)
            elif not (isinstance(value, str) and Path(value).is_file()):
                try:
                    json.dumps(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Native scalar input %r must be JSON-serializable" % name) from exc

    @staticmethod
    def _parse_reference(reference: str) -> Tuple[str, str, str]:
        value = reference[len(dagon.Workflow.SCHEMA):]
        pieces = value.split("/")
        if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
            raise ValueError("Invalid native workflow input reference: %s" % reference)
        return pieces[0], pieces[1], NativeTask._relative("/".join(pieces[2:]), "input")

    def _file_inputs(self) -> Iterable[Tuple[str, str, Optional[Tuple[str, str, str]]]]:
        for name, value in self.inputs.items():
            if isinstance(value, str) and value.startswith(dagon.Workflow.SCHEMA):
                yield name, value, self._parse_reference(value)
            elif isinstance(value, str) and Path(value).is_file():
                yield name, value, None

    def pre_run(self) -> None:
        for _, reference, parsed in self._file_inputs():
            if parsed is None:
                continue
            workflow_name, task_name, _ = parsed
            workflow_name = workflow_name or self.workflow.name
            task = self.workflow.find_task_by_name(workflow_name, task_name)
            if task is None:
                raise ValueError("Native input producer was not found: %s" % reference)
            if workflow_name == self.workflow.name:
                self.add_dependency_to(task)
            else:
                self.add_transversal_point(task)
            task.increment_reference_count()

    def as_json(self) -> Dict[str, Any]:
        """Return enough native-task metadata for workflow serialization."""
        task = super().as_json()
        task.update({"type": "native", "function": self.module + ":" + self.function_name,
                     "inputs": self.inputs, "outputs": self.outputs, "executor": self.executor,
                     "resources": self.resources, "python": self.python, "environment": self.environment})
        return task

    def _spec(self) -> Dict[str, Any]:
        bindings: Dict[str, Any] = {}
        for name, value, parsed in self._file_inputs():
            filename = Path(parsed[2] if parsed else value).name
            bindings[name] = {"kind": "file", "path": "inputs/%s/%s" % (name, filename)}
        for name, value in self.inputs.items():
            if name not in bindings:
                bindings[name] = {"kind": "value", "value": value}
        return {"module": self.module, "function": self.function_name, "module_search_path": self.module_search_path,
                "inputs": bindings,
                "outputs": {name: {"kind": "file", "path": "outputs/" + self._relative(value, "output")}
                            for name, value in self.outputs.items()}, "result_path": ".dagon/native_result.json"}

    def _stage_files(self, spec: Mapping[str, Any]) -> None:
        for name, value, parsed in self._file_inputs():
            if parsed:
                workflow_name, task_name, relative = parsed
                workflow_name = workflow_name or self.workflow.name
                producer = self.workflow.find_task_by_name(workflow_name, task_name)
                if producer is None or producer.working_dir is None:
                    raise ValueError("Native input producer is unavailable: %s" % value)
                source = Path(producer.working_dir, relative)
            else:
                source = Path(value)
            if not source.is_file():
                raise FileNotFoundError("Native input file does not exist: %s" % source)
            destination = Path(self.working_dir, spec["inputs"][name]["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))

    def generate_slurm_command(self, script_name: str) -> str:
        """Return the scheduler command used for a native Slurm task."""
        slurm = Slurm(self.name, "true", **self.resources)
        slurm.working_dir = self.working_dir
        return slurm.generate_command(script_name)

    def execute(self) -> None:
        if self.reuse_checkpoint():
            self._release_references()
            return
        self.create_working_dir()
        key = self.checkpoint_key()
        self.initialize_checkpoint()
        spec = self._spec()
        spec_path = Path(self.working_dir, ".dagon", "native_spec.json")
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            self._stage_files(spec)
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        self.workflow._fire_event("on_task_execute_start", self)
        if not self.workflow.dry:
            command = [self.python, "-m", "dagon.native_runner", ".dagon/native_spec.json"]
            env = dict(os.environ, **self.environment)
            if self.executor == "local" or self.workflow.is_portable_emulation() is True:
                completed = subprocess.run(command, cwd=self.working_dir, env=env, text=True, capture_output=True)
                Path(self.working_dir, ".dagon", "native_stdout.txt").write_text(completed.stdout, encoding="utf-8")
                Path(self.working_dir, ".dagon", "native_stderr.txt").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode:
                    raise RuntimeError("Native function failed: " + completed.stderr)
            else:
                launcher = "#! /bin/bash\ncd " + self.working_dir + "\n" + join_command(command) + "\n"
                Task.on_execute(self, launcher, "native_launcher.sh")
                completed = subprocess.run(self.generate_slurm_command("native_launcher.sh"), shell=True,
                                           text=True, capture_output=True)
                if completed.returncode:
                    raise RuntimeError("Native Slurm function failed: " + completed.stderr)
            self.workflow.checkpoints[key]["code"] = 0
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            for _, _, parsed in self._file_inputs():
                if parsed:
                    workflow_name, task_name, _ = parsed
                    producer = self.workflow.find_task_by_name(workflow_name or self.workflow.name, task_name)
                    if producer:
                        producer.decrement_reference_count()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def _release_references(self) -> None:
        for _, _, parsed in self._file_inputs():
            if parsed:
                workflow_name, task_name, _ = parsed
                producer = self.workflow.find_task_by_name(workflow_name or self.workflow.name, task_name)
                if producer:
                    producer.decrement_reference_count()
