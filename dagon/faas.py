"""First-class provider-neutral Function-as-a-Service workflow tasks."""
import copy
import hashlib
import json
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import dagon
from dagon.faas_models import FaaSInvocation, RetryPolicy
from dagon.faas_providers import FaaSError, get_provider
from dagon.task import Task
from dagon.web.schema import references


_TOP_LEVEL = {"provider", "profile", "function", "inputs", "outputs", "invocation", "timeout", "retry",
              "completion", "input_policy", "output_policy", "provider_options", "annotations"}
_SECRET_KEYS = ("authorization", "api_key", "function_key", "token", "secret", "password", "credential")


def _safe_path(value: str) -> str:
    item = Path(value)
    if not value or item.is_absolute() or ".." in item.parts:
        raise ValueError("FaaS output paths must be relative and stay inside scratch: %s" % value)
    return item.as_posix()


def _json_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("FaaS %s must be JSON-serializable" % label) from exc


def _reject_secrets(value: Any, path: str = "provider_options") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in _SECRET_KEYS) and not lowered.endswith("_env"):
                raise ValueError("FaaS secrets must be referenced by environment-variable name, not stored in %s.%s" % (path, key))
            _reject_secrets(item, path + "." + str(key))
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item, path)


def _retry_policy(value: Optional[Mapping[str, Any]]) -> RetryPolicy:
    raw = dict(value or {})
    allowed = {"max_attempts", "backoff", "initial_delay_seconds", "max_delay_seconds", "retry_on"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("Unknown FaaS retry option(s): %s" % ", ".join(sorted(unknown)))
    policy = RetryPolicy(max_attempts=raw.get("max_attempts", 1), backoff=raw.get("backoff", "none"),
        initial_delay_seconds=raw.get("initial_delay_seconds", 0.0), max_delay_seconds=raw.get("max_delay_seconds"),
        retry_on=tuple(raw.get("retry_on", RetryPolicy().retry_on)))
    if not isinstance(policy.max_attempts, int) or policy.max_attempts < 1:
        raise ValueError("FaaS retry max_attempts must be a positive integer")
    if policy.backoff not in ("none", "fixed", "exponential") or policy.initial_delay_seconds < 0:
        raise ValueError("Invalid FaaS retry backoff policy")
    return policy


class FaaSTask(Task):
    """Invoke an already-deployed function through a provider adapter."""

    def __init__(self, name: str, specification: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> None:
        common = {key: kwargs.pop(key) for key in list(kwargs) if key in ("working_dir", "transversal_workflow", "globusendpoint")}
        spec = dict(specification or {})
        spec.update(kwargs)
        unknown = set(spec) - _TOP_LEVEL
        if unknown:
            raise ValueError("Unknown FaaS option(s): %s" % ", ".join(sorted(unknown)))
        if not isinstance(spec.get("provider"), str) or not spec["provider"]:
            raise ValueError("FaaS provider is required")
        if not isinstance(spec.get("function"), (str, dict)) or not spec["function"]:
            raise ValueError("FaaS function is required")
        self.provider = spec["provider"].lower()
        self.profile = spec.get("profile")
        self.function = _json_copy(spec["function"], "function")
        self.inputs = _json_copy(spec.get("inputs", {}), "inputs")
        if not isinstance(self.inputs, dict):
            raise ValueError("FaaS inputs must be a mapping")
        raw_outputs = _json_copy(spec.get("outputs", {}), "outputs")
        if not isinstance(raw_outputs, dict):
            raise ValueError("FaaS outputs must be a mapping")
        self.outputs = self._normalize_outputs(raw_outputs)
        self.invocation = spec.get("invocation", "sync")
        if self.invocation not in ("sync", "async"):
            raise ValueError("FaaS invocation must be 'sync' or 'async'")
        self.timeout = spec.get("timeout", 120)
        if self.timeout is not None and (not isinstance(self.timeout, int) or self.timeout <= 0):
            raise ValueError("FaaS timeout must be a positive integer")
        self.retry = _retry_policy(spec.get("retry"))
        self.completion = _json_copy(spec.get("completion", {}), "completion")
        self.input_policy = _json_copy(spec.get("input_policy", {"transfer": "auto"}), "input_policy")
        self.output_policy = _json_copy(spec.get("output_policy", {}), "output_policy")
        options = _json_copy(spec.get("provider_options", {}), "provider_options")
        if options and self.provider in options and isinstance(options[self.provider], dict):
            options = options[self.provider]
        _reject_secrets(options)
        self.provider_options = options
        self.annotations = _json_copy(spec.get("annotations", {}), "annotations")
        self.invocation_result = None
        self.sanitized_provider_metadata: Dict[str, Any] = {}
        self.attempt_records = []
        command = json.dumps(self._portable_spec(), sort_keys=True, separators=(",", ":"))
        Task.__init__(self, name, command, **common)
        if self.annotations:
            self.annotate(**self.annotations)

    @staticmethod
    def _normalize_outputs(outputs: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        result = {}
        for name, descriptor in outputs.items():
            if not isinstance(name, str) or not name:
                raise ValueError("FaaS output names must be non-empty strings")
            if isinstance(descriptor, str):
                descriptor = {"path": descriptor, "required": True}
            elif isinstance(descriptor, dict):
                descriptor = dict(descriptor)
            else:
                raise ValueError("FaaS output descriptors must be paths or mappings")
            unknown = set(descriptor) - {"path", "required", "media_type"}
            if unknown or "path" not in descriptor:
                raise ValueError("Invalid FaaS output descriptor for %s" % name)
            descriptor["path"] = _safe_path(descriptor["path"])
            descriptor.setdefault("required", True)
            result[name] = descriptor
        return result

    def _portable_spec(self) -> Dict[str, Any]:
        return {"provider": self.provider, "profile": self.profile, "function": self.function, "inputs": self.inputs,
            "outputs": self.outputs, "invocation": self.invocation, "timeout": self.timeout,
            "retry": {"max_attempts": self.retry.max_attempts, "backoff": self.retry.backoff,
                      "initial_delay_seconds": self.retry.initial_delay_seconds,
                      "max_delay_seconds": self.retry.max_delay_seconds, "retry_on": list(self.retry.retry_on)},
            "completion": self.completion, "input_policy": self.input_policy, "output_policy": self.output_policy,
            "provider_options": {self.provider: self.provider_options}, "annotations": self.annotations}

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.pop("working_dir", None)
        task.pop("command", None)
        task.update({"type": "faas"}, **self._portable_spec())
        return task

    def _references(self) -> Iterable[str]:
        seen = set()
        for reference in references(self.inputs):
            if reference not in seen:
                seen.add(reference)
                yield reference

    @staticmethod
    def _parse_reference(reference: str) -> Tuple[str, str, str]:
        pieces = reference[len(dagon.Workflow.SCHEMA):].split("/")
        if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
            raise ValueError("Invalid FaaS workflow input reference: %s" % reference)
        return pieces[0], pieces[1], _safe_path("/".join(pieces[2:]))

    def pre_run(self) -> None:
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None:
                raise ValueError("FaaS input producer was not found: %s" % reference)
            if workflow_name == self.workflow.name:
                self.add_dependency_to(producer)
            else:
                self.add_transversal_point(producer)
            producer.increment_reference_count()

    def _stage_inputs(self) -> Dict[str, Dict[str, Any]]:
        descriptors = {}
        for reference in self._references():
            workflow_name, task_name, relative = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None or producer.working_dir is None:
                raise ValueError("FaaS input producer is unavailable: %s" % reference)
            source = Path(producer.working_dir, relative)
            if not source.is_file():
                raise FileNotFoundError("FaaS input file does not exist: %s" % source)
            destination = Path(self.working_dir, "inputs", workflow_name, task_name, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            descriptors[reference] = {"kind": "artifact", "reference": reference,
                "path": destination.relative_to(self.working_dir).as_posix(),
                "media_type": mimetypes.guess_type(str(destination))[0], "size_bytes": destination.stat().st_size,
                "checksum": {"algorithm": "sha256", "value": digest},
                "transport": {"type": "local-file", "uri": destination.relative_to(self.working_dir).as_posix()}}
        return descriptors

    @staticmethod
    def _replace(value: Any, descriptors: Mapping[str, Any]) -> Any:
        if isinstance(value, str) and value in descriptors:
            return copy.deepcopy(descriptors[value])
        if isinstance(value, list):
            return [FaaSTask._replace(item, descriptors) for item in value]
        if isinstance(value, dict):
            return {key: FaaSTask._replace(item, descriptors) for key, item in value.items()}
        return value

    def _profile_options(self) -> Dict[str, Any]:
        options = dict(self.provider_options)
        if self.profile and self.workflow is not None:
            section = "faas.%s.%s" % (self.provider, self.profile)
            if section not in self.workflow.cfg:
                raise ValueError("FaaS profile is not configured: [%s]" % section)
            configured = dict(self.workflow.cfg[section])
            configured.update(options)
            options = configured
        _reject_secrets(options)
        return options

    def _envelope(self, inputs: Mapping[str, Any], attempt: int) -> Dict[str, Any]:
        identity = hashlib.sha256((self.workflow.name + "\0" + self.name + "\0" + self.command).encode()).hexdigest()
        return {"specversion": "1.0", "type": "org.dagonstar.task.invoke", "source": "workflow://" + self.workflow.name,
            "id": identity, "subject": self.name, "data": {"workflow": {"name": self.workflow.name},
            "task": {"name": self.name, "attempt": attempt}, "inputs": inputs, "outputs": self.outputs}}

    def _delay(self, attempt: int) -> float:
        delay = self.retry.initial_delay_seconds
        if self.retry.backoff == "exponential":
            delay *= 2 ** max(0, attempt - 1)
        if self.retry.max_delay_seconds is not None:
            delay = min(delay, self.retry.max_delay_seconds)
        return delay

    def _materialize_outputs(self, payload: Mapping[str, Any]) -> None:
        provided = payload.get("outputs", {}) if isinstance(payload, dict) else {}
        if not isinstance(provided, dict):
            raise FaaSError("FaaS response outputs must be a mapping", "invalid_response")
        for name, declared in self.outputs.items():
            value = provided.get(name)
            if value is None:
                if declared["required"]:
                    raise FaaSError("Required FaaS output is missing: %s" % name, "output_missing")
                continue
            destination = Path(self.working_dir, "outputs", declared["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".tmp")
            if isinstance(value, dict) and "path" in value:
                source = Path(self.working_dir, _safe_path(value["path"]))
                if not source.is_file():
                    raise FaaSError("FaaS output source is missing: %s" % name, "output_missing")
                shutil.copy2(str(source), str(temporary))
            else:
                temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if isinstance(value, dict) and value.get("sha256"):
                digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
                if digest != value["sha256"]:
                    temporary.unlink()
                    raise FaaSError("FaaS output checksum mismatch: %s" % name, "output_checksum_mismatch")
            os.replace(str(temporary), str(destination))

    def execute(self) -> None:
        key = self.workflow.name + "." + self.name
        checkpoint = self.workflow.checkpoints.get(key, {})
        if checkpoint.get("code") == 0 and checkpoint.get("spec_sha256") == hashlib.sha256(self.command.encode()).hexdigest() \
                and Path(checkpoint.get("working_dir", "")).is_dir():
            self.working_dir, self.fair_checkpoint_reused = checkpoint["working_dir"], True
            return
        self.create_working_dir()
        spec_hash = hashlib.sha256(self.command.encode()).hexdigest()
        self.workflow.checkpoints[key] = {"working_dir": self.working_dir, "workflow": self.workflow.name,
                                          "name": self.name, "spec_sha256": spec_hash}
        metadata_dir = Path(self.working_dir, ".dagon")
        metadata_dir.mkdir(parents=True, exist_ok=True)
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            descriptors = self._stage_inputs()
            resolved_inputs = self._replace(self.inputs, descriptors)
            metadata_dir.joinpath("faas_spec.json").write_text(json.dumps(self._portable_spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        self.workflow._fire_event("on_task_execute_start", self)
        if not self.workflow.dry:
            provider = get_provider("mock" if self.workflow.is_portable_emulation() is True else self.provider)
            capabilities = provider.capabilities()
            if self.invocation == "async" and not capabilities.supports_async:
                raise FaaSError("Provider does not support asynchronous invocation", "unsupported_capability")
            options = {} if self.workflow.is_portable_emulation() is True else self._profile_options()
            last_error = None
            for attempt in range(1, self.retry.max_attempts + 1):
                envelope = self._envelope(resolved_inputs, attempt)
                metadata_dir.joinpath("faas_request.json").write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                invocation = FaaSInvocation(self.provider, self.function, self.invocation, envelope, self.timeout,
                                            envelope["id"], attempt, options)
                try:
                    self.invocation_result = provider.invoke(invocation)
                    self.attempt_records.append({"attempt": attempt, "status": self.invocation_result.status,
                                                 "request_id": self.invocation_result.request_id})
                    break
                except FaaSError as exc:
                    last_error = exc
                    self.attempt_records.append({"attempt": attempt, "status": "failed", "error": exc.code})
                    if not exc.transient or exc.code not in self.retry.retry_on or attempt == self.retry.max_attempts:
                        raise
                    time.sleep(self._delay(attempt))
            if self.invocation_result is None:
                raise last_error or FaaSError("FaaS invocation failed")
            response = self.invocation_result.payload or {}
            safe_response = provider.sanitize_metadata(response)
            metadata_dir.joinpath("faas_response.json").write_text(json.dumps(safe_response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sanitized = provider.sanitize_metadata(self.invocation_result.metadata)
            self.sanitized_provider_metadata = dict(sanitized)
            metadata_dir.joinpath("faas_provider_metadata.json").write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if self.invocation == "sync":
                self._materialize_outputs(response)
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

    def get_execution_metadata(self) -> Dict[str, Any]:
        metadata = {"model": "faas", "provider": self.provider, "function": self.function,
            "invocation_mode": self.invocation, "timeout_seconds": self.timeout, "attempts": len(self.attempt_records),
            "attempt_records": list(self.attempt_records)}
        if self.invocation_result:
            metadata.update({"request_id": self.invocation_result.request_id, "status": self.invocation_result.status})
            metadata.update({key: value for key, value in self.sanitized_provider_metadata.items() if value is not None})
        return metadata
