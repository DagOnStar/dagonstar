"""Supervised worker process that hosts one agent adapter for one run.

Protocol (one JSON object per line):

* first request ``{"factory": "module:attr", "options": {...}}``; reply
  ``{"ok": true, "id": ..., "deterministic": ...}``;
* each later request ``{"state": ..., "max_tokens": n, "timeout": s}``; reply
  ``{"ok": true, "response": ..., "usage": ...}``;
* failures reply ``{"ok": false, "error": "...", "code": "..."}``.

End of input ends the worker.  The supervisor (``dagon.agentic.sandbox.
ProcessAdapter``) enforces every deadline and kills the worker's whole process
group on timeout or cancellation, so an adapter cannot act after the run has
stopped waiting for it.  Adapter output written to ``sys.stdout`` is diverted
to standard error so it cannot corrupt the protocol.
"""
import importlib
import json
import sys
from typing import Any, Dict


def _reply(stream: Any, payload: Dict[str, Any]) -> None:
    try:
        text = json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        text = json.dumps({"ok": False, "error": "adapter reply is not JSON: %s" % exc, "code": "provider_error"})
    stream.write(text + "\n")
    stream.flush()


def _failure(exc: BaseException) -> Dict[str, Any]:
    return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc), "code": getattr(exc, "code", "provider_error")}


def main() -> int:
    protocol = sys.stdout
    sys.stdout = sys.stderr
    adapter = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError as exc:
            _reply(protocol, _failure(exc))
            return 1
        if adapter is None:
            try:
                module_name, _, attribute = str(request["factory"]).partition(":")
                factory = getattr(importlib.import_module(module_name), attribute)
                adapter = factory(**request.get("options", {}))
                _reply(protocol, {"ok": True, "id": getattr(adapter, "id", "custom"),
                                  "deterministic": bool(getattr(adapter, "deterministic", False))})
            except Exception as exc:  # reported to the supervisor, never raised across the boundary
                _reply(protocol, _failure(exc))
                return 1
            continue
        try:
            response, usage = adapter.propose(request["state"], request["max_tokens"], request["timeout"])
            _reply(protocol, {"ok": True, "response": response, "usage": usage})
        except Exception as exc:
            _reply(protocol, _failure(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
