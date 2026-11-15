"""Supervised worker process for process-isolated tools and evaluators.

Protocol: one JSON object on stdin ``{"function": "module:attr", "args": [...]}``;
one JSON object on stdout ``{"ok": true, "result": ...}`` or
``{"ok": false, "error": "..."}``.  The parent enforces the deadline, bounds
the output, and terminates the whole process group on timeout or cancellation.
"""
import importlib
import json
import sys


def main() -> int:
    request = json.loads(sys.stdin.read())
    module_name, _, attribute = request["function"].partition(":")
    try:
        function = getattr(importlib.import_module(module_name), attribute)
        result = function(*request.get("args", []))
        payload = {"ok": True, "result": result}
        text = json.dumps(payload, allow_nan=False)
    except Exception as exc:  # reported to the supervisor, never raised across the boundary
        text = json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    sys.stdout.write(text)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
