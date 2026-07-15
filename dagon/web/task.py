"""Declarative HTTP/HTTPS workflow task."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import dagon
from dagon.batch import Slurm
from dagon.shell import join_command
from dagon.task import Task
from dagon.web.schema import references, safe_output_path, validate


class WebTask(Task):
    """Run a JSON-serializable web request through a scratch-local runner."""

    def __init__(self, name: str, specification: Mapping[str, Any], executor: str = "local",
                 resources: Optional[Mapping[str, Any]] = None, python: str = sys.executable,
                 working_dir: Optional[str] = None, environment: Optional[Mapping[str, str]] = None,
                 globusendpoint: Optional[str] = None, **_: Any) -> None:
        self.specification = validate(dict(specification))
        self.executor = executor.lower()
        self.resources = dict(resources or {})
        self.python = python
        self.environment = dict(environment or {})
        if self.executor not in ("local", "slurm"):
            raise ValueError("Web executor must be 'local' or 'slurm'")
        Task.__init__(self, name, json.dumps(self.specification, sort_keys=True), working_dir,
                      globusendpoint=globusendpoint)

    @staticmethod
    def _parse_reference(reference: str) -> Tuple[str, str, str]:
        pieces = reference[len(dagon.Workflow.SCHEMA):].split("/")
        if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
            raise ValueError("Invalid web workflow input reference: %s" % reference)
        relative = safe_output_path("/".join(pieces[2:]))
        return pieces[0], pieces[1], relative

    def _references(self) -> Iterable[str]:
        seen = set()
        for reference in references(self.specification):
            if reference not in seen:
                seen.add(reference)
                yield reference

    def pre_run(self) -> None:
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            task = self.workflow.find_task_by_name(workflow_name, task_name)
            if task is None:
                raise ValueError("Web input producer was not found: %s" % reference)
            if workflow_name == self.workflow.name:
                self.add_dependency_to(task)
            else:
                self.add_transversal_point(task)
            task.increment_reference_count()

    def _staged_path(self, reference: str) -> str:
        workflow_name, task_name, relative = self._parse_reference(reference)
        return "inputs/%s/%s/%s" % (workflow_name or self.workflow.name, task_name, relative)

    def _stage_inputs(self) -> None:
        for reference in self._references():
            workflow_name, task_name, relative = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None or producer.working_dir is None:
                raise ValueError("Web input producer is unavailable: %s" % reference)
            source = Path(producer.working_dir, relative)
            if not source.is_file():
                raise FileNotFoundError("Web input file does not exist: %s" % source)
            destination = Path(self.working_dir, self._staged_path(reference))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            for reference in self._references():
                value = value.replace(reference, self._staged_path(reference))
            return value
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if not isinstance(value, dict):
            return value
        if set(value) == {"text"} and isinstance(value["text"], str) and value["text"].startswith("workflow://"):
            return Path(self.working_dir, self._staged_path(value["text"])).read_text(encoding="utf-8")
        if set(value) == {"json_file"} and isinstance(value["json_file"], str) and value["json_file"].startswith("workflow://"):
            return json.loads(Path(self.working_dir, self._staged_path(value["json_file"])).read_text(encoding="utf-8"))
        return {key: self._resolve(item) for key, item in value.items()}

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.update({"type": "web", "specification": self.specification, "executor": self.executor,
                     "resources": self.resources, "python": self.python, "environment": self.environment})
        return task

    def generate_slurm_command(self, script_name: str) -> str:
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
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            self._stage_inputs()
            resolved = self._resolve(self.specification)
            meta = Path(self.working_dir, ".dagon")
            meta.joinpath("web_request.json").write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            meta.joinpath("resolved_spec.json").write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        self.workflow._fire_event("on_task_execute_start", self)
        if not self.workflow.dry:
            command = [self.python, "-m", "dagon.web.runner", ".dagon/web_request.json"]
            environment = dict(os.environ, **self.environment)
            if self.executor == "local":
                completed = subprocess.run(command, cwd=self.working_dir, env=environment, text=True, capture_output=True)
                Path(self.working_dir, ".dagon/web_stdout.txt").write_text(completed.stdout, encoding="utf-8")
                Path(self.working_dir, ".dagon/web_stderr.txt").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode:
                    raise RuntimeError("Web request failed: " + completed.stderr)
            else:
                launcher = "#! /bin/bash\ncd " + self.working_dir + "\n" + join_command(command) + "\n"
                Task.on_execute(self, launcher, "web_launcher.sh")
                completed = subprocess.run(self.generate_slurm_command("web_launcher.sh"), shell=True, text=True, capture_output=True)
                if completed.returncode:
                    raise RuntimeError("Web Slurm request failed: " + completed.stderr)
            self.workflow.checkpoints[key]["code"] = 0
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            for reference in self._references():
                workflow_name, task_name, _ = self._parse_reference(reference)
                producer = self.workflow.find_task_by_name(workflow_name or self.workflow.name, task_name)
                if producer:
                    producer.decrement_reference_count()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def _release_references(self) -> None:
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            producer = self.workflow.find_task_by_name(workflow_name or self.workflow.name, task_name)
            if producer:
                producer.decrement_reference_count()
