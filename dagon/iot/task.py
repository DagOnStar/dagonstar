"""First-class bounded IoT and compute-continuum workflow task."""
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import dagon
from dagon.iot.references import references, replace_references
from dagon.iot.registry import get_provider, provider_exists
from dagon.iot.security import json_copy, redact
from dagon.task import Task, TaskType


class IoTError(Exception):
    pass


class IoTValidationError(IoTError, ValueError):
    pass


class IoTTimeoutError(IoTError):
    pass


class IoTUnknownOutcomeError(IoTError):
    pass


class IoTProviderUnavailableError(IoTError):
    pass


_OPERATIONS = {"observe", "configure", "actuate", "compute"}
_COMPLETION = {"first_event", "sample_count", "duration", "condition", "acknowledged", "reported_state", "job"}
_FIELDS = ("operation", "provider", "endpoint", "endpoint_ref", "target", "resource", "action", "request",
           "inputs", "outputs", "completion", "delivery", "placement", "runtime", "artifact", "timeout",
           "credential_ref", "provider_options")


def _safe_path(value: str) -> str:
    item = Path(value)
    if not value or item.is_absolute() or ".." in item.parts:
        raise IoTValidationError("IoT output paths must be relative and stay inside scratch: %s" % value)
    return item.as_posix()


class IoTTask(Task):
    """Execute one bounded observe, configure, actuate, or edge-compute operation."""
    task_type = TaskType.IOT

    def __init__(self, name: str, *, operation: str, provider: str = "mock", endpoint: Optional[str] = None,
                 endpoint_ref: Optional[str] = None, target: Any = None, resource: Optional[str] = None,
                 action: Optional[str] = None, request: Any = None, inputs: Optional[Mapping[str, Any]] = None,
                 outputs: Optional[Mapping[str, Any]] = None, completion: Optional[Mapping[str, Any]] = None,
                 delivery: Optional[Mapping[str, Any]] = None, placement: Optional[Mapping[str, Any]] = None,
                 runtime: Optional[str] = None, artifact: Optional[str] = None, timeout: Optional[float] = None,
                 credential_ref: Optional[str] = None, provider_options: Optional[Mapping[str, Any]] = None,
                 working_dir: Optional[str] = None, transversal_workflow: Optional[str] = None,
                 globusendpoint: Optional[str] = None) -> None:
        self.operation = str(operation).lower()
        self.provider = str(provider).lower()
        self.endpoint, self.endpoint_ref = endpoint, endpoint_ref
        self.target, self.resource, self.action = json_copy(target), resource, action
        self.request, self.inputs = json_copy(request), json_copy(dict(inputs or {}))
        self.outputs = {str(key): _safe_path(str(value)) for key, value in dict(outputs or {}).items()}
        self.completion = json_copy(dict(completion or {}))
        self.delivery, self.placement = json_copy(dict(delivery or {})), json_copy(dict(placement or {}))
        self.runtime, self.artifact, self.timeout = runtime, artifact, timeout
        self.credential_ref = credential_ref
        self.provider_options = json_copy(dict(provider_options or {}))
        self.resolved_iot_spec = None
        self.invocation_result = None
        self._validate()
        self.iot_spec = self._portable_spec()
        command = "python -m dagon.iot.runner run --spec .dagon/iot_request.json --workdir . --result outputs/result.json"
        super().__init__(name, command, working_dir=working_dir, transversal_workflow=transversal_workflow,
                         globusendpoint=globusendpoint)

    def _validate(self) -> None:
        if self.operation not in _OPERATIONS:
            raise IoTValidationError("IoT operation must be one of: %s" % ", ".join(sorted(_OPERATIONS)))
        if not provider_exists(self.provider):
            raise IoTValidationError("Unknown IoT provider: %s" % self.provider)
        mode = self.completion.get("mode")
        if mode not in _COMPLETION:
            raise IoTValidationError("IoT completion must select a supported bounded mode")
        if self.operation == "observe":
            if mode == "sample_count" and (not isinstance(self.completion.get("count"), int) or self.completion["count"] < 1):
                raise IoTValidationError("sample_count completion requires a positive count")
            if mode not in {"first_event", "sample_count", "duration"} and not self.completion.get("timeout_seconds"):
                raise IoTValidationError("IoT observation completion must be bounded by a timeout")
        if self.operation == "actuate":
            attempts = self.delivery.get("max_attempts", 1)
            if attempts != 1 and not self.delivery.get("idempotent"):
                raise IoTValidationError("Physical actuation retries require explicit idempotency")
            self.delivery.setdefault("max_attempts", 1)
        if self.operation == "compute" and not (self.artifact or self.action or self.provider_options.get("executable")):
            raise IoTValidationError("IoT compute requires an artifact, action, or provider executable reference")

    def _portable_spec(self) -> Dict[str, Any]:
        spec = {"schemaVersion": 1, "operation": self.operation, "provider": self.provider,
                "endpoint": self.endpoint, "endpointRef": self.endpoint_ref, "target": self.target,
                "resource": self.resource, "action": self.action, "request": self.request,
                "inputs": self.inputs, "outputs": self.outputs, "completion": self.completion,
                "delivery": self.delivery, "placement": self.placement, "runtime": self.runtime,
                "artifact": self.artifact, "timeout": self.timeout, "credentialRef": self.credential_ref,
                "providerOptions": self.provider_options}
        return redact({key: value for key, value in spec.items() if value is not None and value != {}})

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.update({"type": "iot", "command": None, "iot": self._portable_spec()})
        task.pop("working_dir", None)
        return task

    def _references(self) -> Iterable[str]:
        seen = set()
        for reference in references(self.iot_spec):
            if reference not in seen:
                seen.add(reference)
                yield reference

    @staticmethod
    def _parse_reference(reference: str) -> Tuple[str, str, str]:
        pieces = reference[len(dagon.Workflow.SCHEMA):].split("/")
        if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
            raise IoTValidationError("Invalid IoT workflow reference: %s" % reference)
        return pieces[0], pieces[1], _safe_path("/".join(pieces[2:]))

    def pre_run(self) -> None:
        producers = set()
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None:
                raise IoTValidationError("IoT input producer was not found: %s" % reference)
            key = (workflow_name, task_name)
            if key in producers:
                continue
            producers.add(key)
            if workflow_name == self.workflow.name:
                self.add_dependency_to(producer)
            else:
                self.add_transversal_point(producer)
            producer.increment_reference_count()

    def _resolve_and_stage(self) -> Dict[str, Any]:
        staged = {}
        def resolve(reference: str) -> str:
            if reference in staged:
                return staged[reference]
            workflow_name, task_name, relative = self._parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            producer = self.workflow.find_task_by_name(workflow_name, task_name)
            if producer is None or producer.working_dir is None:
                raise IoTValidationError("IoT input producer is unavailable: %s" % reference)
            source = Path(producer.working_dir, relative)
            if not source.is_file():
                raise FileNotFoundError("IoT input file does not exist: %s" % source)
            destination = Path(self.working_dir, ".dagon", "inputs", workflow_name, task_name, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
            staged[reference] = str(destination)
            return str(destination)
        return replace_references(self.iot_spec, resolve)

    def reuse_checkpoint(self) -> bool:
        checkpoint = self.workflow.checkpoints.get(self.checkpoint_key(), {})
        if checkpoint.get("task_type") != "iot" or checkpoint.get("schema_version") != 1 or checkpoint.get("code") != 0:
            return False
        working_dir = checkpoint.get("working_dir")
        if not isinstance(working_dir, str) or not Path(working_dir).is_dir():
            return False
        for descriptor in checkpoint.get("outputs", []):
            output = Path(working_dir, descriptor["path"])
            if not output.is_file() or descriptor.get("sha256") != hashlib.sha256(output.read_bytes()).hexdigest():
                return False
        self.working_dir, self.fair_checkpoint_reused = working_dir, True
        return True

    def _write_json(self, relative: str, value: Any) -> None:
        target = Path(self.working_dir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(redact(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(target))

    def _materialize(self, result: Dict[str, Any]) -> list:
        self._write_json("outputs/result.json", result)
        payload = result.get("payload")
        evidence = []
        for name, relative in self.outputs.items():
            value = payload
            if isinstance(payload, dict) and name in payload:
                value = payload[name]
            self._write_json(relative, value)
        for relative in sorted(set(self.outputs.values()) | {"outputs/result.json"}):
            target = Path(self.working_dir, relative)
            evidence.append({"name": next((key for key, value in self.outputs.items() if value == relative), "result"),
                             "path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        return evidence

    def execute(self) -> None:
        if self.reuse_checkpoint():
            self._release_references()
            return
        self.create_working_dir()
        key = self.checkpoint_key()
        previous = dict(self.workflow.checkpoints.get(key, {}))
        self._write_json(".dagon/iot_request.json", self.iot_spec)
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            self.resolved_iot_spec = self._resolve_and_stage()
            self._write_json(".dagon/iot_resolved.json", self.resolved_iot_spec)
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        provider = get_provider("mock" if self.workflow.is_portable_emulation() else self.provider)
        if self.operation not in provider.capabilities():
            raise IoTProviderUnavailableError("IoT provider %s does not support %s" % (self.provider, self.operation))
        context = {"task": self, "spec": self.resolved_iot_spec}
        provider.prepare(self.resolved_iot_spec, context)
        if previous.get("status") == "WAITING" and previous.get("invocation_id") and provider.supports_reattach:
            invocation = provider.reattach(previous, context)
        else:
            invocation = provider.invoke(self.resolved_iot_spec, context)
        checkpoint = {"schema_version": 1, "task_type": "iot", "workflow": self.workflow.name,
                      "name": self.name, "working_dir": self.working_dir, "status": "WAITING",
                      "provider": self.provider, "operation": self.operation,
                      "invocation_id": invocation.invocation_id, "progress": invocation.progress,
                      "delivery": redact(self.delivery), "outcome_certainty": "known", "outputs": []}
        self.workflow.checkpoints[key] = checkpoint
        result = provider.poll(invocation, context)
        self.invocation_result = result.as_dict()
        if self.operation == "actuate" and result.outcome_certainty == "unknown":
            checkpoint["outcome_certainty"] = "unknown"
            raise IoTUnknownOutcomeError("Physical actuation outcome is unknown; automatic replay is disabled")
        outputs = self._materialize(self.invocation_result)
        self._write_json(".dagon/iot_result.json", self.invocation_result)
        self._write_json(".dagon/iot_provenance.json", {key: self.invocation_result.get(key) for key in
            ("requested_target", "selected_target", "placement", "migration_history", "protocol_metadata", "outcome_certainty")})
        checkpoint.update({"status": "SUCCEEDED", "code": 0, "outputs": outputs,
                           "outcome_certainty": result.outcome_certainty})
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self._release_references()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def _release_references(self) -> None:
        released = set()
        for reference in self._references():
            workflow_name, task_name, _ = self._parse_reference(reference)
            key = (workflow_name or self.workflow.name, task_name)
            if key in released:
                continue
            released.add(key)
            producer = self.workflow.find_task_by_name(key[0], key[1])
            if producer:
                producer.decrement_reference_count()

    def get_execution_metadata(self) -> Dict[str, Any]:
        return redact(self.invocation_result or {"provider": self.provider, "operation": self.operation})
