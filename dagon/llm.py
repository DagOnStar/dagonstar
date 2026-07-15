"""OpenAI-compatible large-language-model workflow tasks."""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import dagon
from dagon.task import ExecutionResult, Task


JsonValue = Union[Dict[str, Any], list, str, int, float, bool, None]
_WORKFLOW_REFERENCE = re.compile(r"workflow://[^\s\"'\],}]+")


class _PromptValues(dict):
    """``str.format_map`` mapping that gives useful errors for missing values."""

    def __missing__(self, key: str) -> str:
        raise ValueError("Prompt parameter %r was not provided" % key)


class LLMTask(Task):
    """Invoke an OpenAI-compatible Chat Completions API.

    ``prompt`` is a JSON-compatible Chat Completions request.  String values in
    that object may use ``{parameter}`` placeholders supplied through ``params``.
    ``input_files`` maps a placeholder name to a ``workflow://`` file reference;
    the staged UTF-8 file content is made available to that placeholder.
    """

    def __init__(
            self,
            name: str,
            prompt: Union[str, Mapping[str, Any]],
            provider: str,
            params: Optional[Mapping[str, Any]] = None,
            input_files: Optional[Mapping[str, str]] = None,
            working_dir: Optional[str] = None,
            output_file: str = "response.json",
            timeout: int = 120,
            **_: Any) -> None:
        if isinstance(prompt, str):
            try:
                prompt_data = json.loads(prompt)
            except json.JSONDecodeError as exc:
                raise ValueError("LLM prompt must be a JSON object or JSON string") from exc
        else:
            prompt_data = dict(prompt)
        if not isinstance(prompt_data, dict):
            raise ValueError("LLM prompt must be a JSON object")
        if not provider:
            raise ValueError("An LLM provider name is required")
        if not output_file or Path(output_file).is_absolute() or ".." in Path(output_file).parts:
            raise ValueError("output_file must be a relative path inside the task directory")

        # The base class uses ``command`` for serialisation and workflow state.
        Task.__init__(self, name, json.dumps(prompt_data), working_dir)
        self.prompt = prompt_data
        self.provider = provider
        self.params = dict(params or {})
        self.input_files = dict(input_files or {})
        self.output_file = output_file
        self.timeout = timeout
        self.result: Optional[Dict[str, Any]] = None

    def as_json(self) -> Dict[str, Any]:
        """Return a workflow-schema representation that can recreate this task."""
        task = super().as_json()
        task.update({
            "type": "llm",
            "provider": self.provider,
            "params": self.params,
            "input_files": self.input_files,
            "output_file": self.output_file,
        })
        return task

    def _references(self) -> Iterable[str]:
        values = list(self.input_files.values()) + [json.dumps(self.prompt)]
        seen = set()
        for value in values:
            for reference in _WORKFLOW_REFERENCE.findall(value):
                if reference not in seen:
                    seen.add(reference)
                    yield reference

    @staticmethod
    def _parse_reference(reference: str) -> Tuple[str, str, str]:
        value = reference[len(dagon.Workflow.SCHEMA):]
        pieces = value.split("/")
        if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
            raise ValueError("Invalid workflow input reference: %s" % reference)
        relative_path = "/".join(pieces[2:])
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ValueError("LLM input reference must stay inside the producer directory: %s" % reference)
        return pieces[0], pieces[1], relative_path

    def pre_run(self) -> None:
        """Infer dependencies from declared LLM input-file references."""
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            task = self.workflow.find_task_by_name(workflow_name, task_name)
            if task is None:
                raise ValueError("LLM input producer was not found: %s" % reference)
            if workflow_name == self.workflow.name:
                self.add_dependency_to(task)
            else:
                self.add_transversal_point(task)
            task.increment_reference_count()

    def _stage_input_files(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Stage declared and inline references, returning parameter and text values."""
        values: Dict[str, str] = {}
        reference_values: Dict[str, str] = {}
        parameter_by_reference = {reference: parameter for parameter, reference in self.input_files.items()}
        for reference in self._references():
            workflow_name, task_name, relative_path = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None or producer.working_dir is None:
                raise ValueError("LLM input producer is unavailable: %s" % reference)
            source = Path(producer.working_dir, relative_path)
            if not source.is_file():
                raise FileNotFoundError("LLM input file does not exist: %s" % source)
            destination = Path(self.working_dir, ".dagon", "inputs", workflow_name, task_name, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
            try:
                content = destination.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("LLM input files must be UTF-8 text: %s" % reference) from exc
            reference_values[reference] = content
            parameter = parameter_by_reference.get(reference)
            if parameter is not None:
                values[parameter] = content
        return values, reference_values

    @staticmethod
    def _render(value: JsonValue, params: Mapping[str, Any], references: Mapping[str, str]) -> JsonValue:
        if isinstance(value, str):
            for reference, content in references.items():
                value = value.replace(reference, content)
            return value.format_map(_PromptValues(params))
        if isinstance(value, list):
            return [LLMTask._render(item, params, references) for item in value]
        if isinstance(value, dict):
            return {key: LLMTask._render(item, params, references) for key, item in value.items()}
        return value

    def _provider_config(self) -> Dict[str, str]:
        section = "llm." + self.provider
        try:
            config = self.workflow.cfg[section]
        except KeyError as exc:
            raise ValueError("LLM provider %r is not configured (expected [%s])" % (self.provider, section)) from exc
        endpoint = config.get("endpoint", "").rstrip("/")
        if not endpoint:
            raise ValueError("LLM provider %r requires an endpoint" % self.provider)
        api_key = config.get("api_key", "")
        api_key_env = config.get("api_key_env", "")
        if api_key_env:
            api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise ValueError("LLM provider %r requires api_key or api_key_env" % self.provider)
        return {"endpoint": endpoint, "api_key": api_key, "model": config.get("model", "")}

    def _request(self, payload: Dict[str, Any], config: Mapping[str, str]) -> Dict[str, Any]:
        endpoint = config["endpoint"]
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/v1/chat/completions"
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization": "Bearer " + config["api_key"],
            "Content-Type": "application/json",
        }, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("LLM provider returned HTTP %s: %s" % (exc.code, detail)) from exc
        except URLError as exc:
            raise RuntimeError("Unable to contact LLM provider %r: %s" % (self.provider, exc.reason)) from exc

    def execute(self) -> None:
        key = self.checkpoint_key()
        if not self.reuse_checkpoint():
            self.create_working_dir()
            self.initialize_checkpoint()
            input_values, reference_values = self._stage_input_files()
            payload = self._render(self.prompt, dict(self.params, **input_values), reference_values)
            if not isinstance(payload, dict):
                raise ValueError("LLM prompt must be a JSON object")
            config = self._provider_config()
            if "model" not in payload:
                if not config["model"]:
                    raise ValueError("LLM prompt needs model or provider configuration needs model")
                payload["model"] = config["model"]
            if "messages" not in payload:
                raise ValueError("LLM prompt must contain a messages array")
            self.workflow._fire_event("on_task_execute_start", self)
            if not self.workflow.dry:
                self.result = self._request(payload, config)
                output = Path(self.working_dir, self.output_file)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(self.result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                self.workflow.checkpoints[key]["code"] = 0
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self.remove_reference_workflow()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)
