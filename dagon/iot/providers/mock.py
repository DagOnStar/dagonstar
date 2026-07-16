"""Deterministic credential-free normative IoT provider."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Set

from dagon.iot.model import IoTInvocation, IoTInvocationResult
from dagon.iot.providers.base import IoTProvider


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockIoTProvider(IoTProvider):
    name = "mock"
    supports_reattach = True
    _invocations: Dict[str, IoTInvocation] = {}

    def capabilities(self) -> Set[str]:
        return {"observe", "configure", "actuate", "compute", "reported_state", "placement"}

    def invoke(self, request: Dict[str, Any], context: Dict[str, Any]) -> IoTInvocation:
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:20]
        invocation = IoTInvocation("iot-" + digest)
        self._invocations[invocation.invocation_id] = invocation
        return invocation

    def reattach(self, checkpoint: Dict[str, Any], context: Dict[str, Any]) -> IoTInvocation:
        invocation_id = checkpoint["invocation_id"]
        return self._invocations.get(invocation_id, IoTInvocation(invocation_id, progress=checkpoint.get("progress", {})))

    def poll(self, invocation: IoTInvocation, context: Dict[str, Any]) -> IoTInvocationResult:
        spec = context["spec"]
        options = spec.get("providerOptions", {})
        payload = spec.get("request")
        if spec["operation"] == "observe":
            events = list((payload or {}).get("events", [])) if isinstance(payload, dict) else []
            mode = spec["completion"]["mode"]
            count = 1 if mode == "first_event" else spec["completion"].get("count", len(events))
            payload = {"events": events[:count]}
        elif spec["operation"] == "configure":
            payload = {"desired": payload, "reported": options.get("reported_state", payload)}
        elif spec["operation"] == "actuate":
            unknown = bool(options.get("unknown_outcome"))
            return self._result(invocation, spec, payload, "unknown" if unknown else "known")
        elif spec["operation"] == "compute":
            payload = options.get("result", {"runtime": spec.get("runtime"), "inputs": spec.get("inputs", {})})
        return self._result(invocation, spec, payload, "known")

    def _result(self, invocation: IoTInvocation, spec: Dict[str, Any], payload: Any,
                certainty: str) -> IoTInvocationResult:
        selected = spec.get("providerOptions", {}).get("selected_target", spec.get("target"))
        placement = dict(spec.get("placement") or {})
        if spec.get("providerOptions", {}).get("selected_tier"):
            placement["selectedTier"] = spec["providerOptions"]["selected_tier"]
        return IoTInvocationResult(invocation.invocation_id, "SUCCEEDED", _now(), _now(),
            spec["operation"], "mock", spec.get("target"), selected, payload,
            acknowledgements=[{"acknowledged": certainty == "known"}], placement=placement or None,
            migration_history=spec.get("providerOptions", {}).get("migration_history", []),
            protocol_metadata={"transport": "mock"}, outcome_certainty=certainty)
