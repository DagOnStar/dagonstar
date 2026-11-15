"""Runtime invariants and custom guardrails, enforced outside the agent.

Runtime invariants always apply.  Custom guardrails (registered by ID) are
optional additions at four stages: ``input``, ``pre_action``, ``post_action``,
``result``.  A guard returns ``None`` or a violation with ``code``, ``reason``,
``evidence``, and ``retryable``.  Only guards registered as ``repairable`` may
return a retryable violation; every other violation, and every guard
exception or timeout, blocks the run (fail closed).
"""
import json
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, Dict, Iterable, List, Optional

from dagon.agentic.errors import AgenticCancelled, AgenticValidationError
from dagon.agentic.registry import Registry
from dagon.agentic.sandbox import call_in_process, call_inline
from dagon.agentic.schema import validate as validate_schema
from dagon.agentic.security import json_copy

MAX_RESULT_BYTES = 4 * 1024 * 1024
_URI = re.compile(r"workflow://[^\s\"'\],}]+")


@dataclass
class Violation:
    guard: str
    stage: str
    code: str
    reason: str
    evidence: Any = field(default_factory=dict)
    retryable: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _unsafe_path(value: str) -> bool:
    if "\x00" in value or "\\" in value and ".." in value:
        return True
    if value.startswith(("/", "~")) or value.startswith("//") or PureWindowsPath(value).drive:
        return True
    return ".." in PurePosixPath(value.replace("\\", "/")).parts


def check_action(tool: Any, arguments: Any, allowed: Iterable[str], registry: Registry) -> Optional[Violation]:
    """Runtime invariant for a proposed tool action (before any execution)."""
    if not isinstance(tool, str) or tool not in set(allowed) or tool not in registry.tools:
        return Violation("runtime", "pre_action", "undeclared_tool",
                         "tool %r is not permitted for this task" % (tool,), {"tool": str(tool)[:128]})
    if not isinstance(arguments, dict):
        return Violation("runtime", "pre_action", "invalid_arguments", "tool arguments must be an object",
                         {"tool": tool}, retryable=True)
    for text in _strings(arguments):
        if "workflow://" in text:
            return Violation("runtime", "pre_action", "workflow_uri_injection",
                             "actions cannot introduce workflow:// references", {"tool": tool})
        if _unsafe_path(text):
            return Violation("runtime", "pre_action", "path_escape",
                             "arguments must not contain absolute or parent-directory paths", {"tool": tool})
    errors = validate_schema(arguments, registry.tools[tool].arguments_schema)
    if errors:
        return Violation("runtime", "pre_action", "invalid_arguments", "arguments do not match the tool schema",
                         {"tool": tool, "errors": errors[:10]}, retryable=True)
    return None


def check_candidate(candidate: Any, output_schema: Optional[Dict[str, Any]],
                    declared_uris: Iterable[str]) -> Optional[Violation]:
    """Runtime invariant for a proposed result candidate."""
    try:
        json_copy(candidate, "candidate")
    except AgenticValidationError as exc:
        return Violation("runtime", "result", "non_json_candidate", str(exc), retryable=True)
    size = len(json.dumps(candidate).encode("utf-8"))
    if size > MAX_RESULT_BYTES:
        return Violation("runtime", "result", "result_too_large", "candidate exceeds %d bytes" % MAX_RESULT_BYTES,
                         {"bytes": size}, retryable=True)
    declared = set(declared_uris)
    for text in _strings(candidate):
        for uri in _URI.findall(text):
            if uri not in declared:
                return Violation("runtime", "result", "workflow_uri_injection",
                                 "a result cannot add workflow inputs or alter the workflow graph", {"uri": uri})
    if output_schema is not None:
        errors = validate_schema(candidate, output_schema)
        if errors:
            return Violation("runtime", "result", "output_schema", "candidate violates specification.output_schema",
                             {"errors": errors[:10]}, retryable=True)
    return None


def run_guards(stage: str, guard_ids: Iterable[str], subject: Any, context: Dict[str, Any], registry: Registry,
               timeout: float, cancel_event: Optional[threading.Event] = None) -> List[Violation]:
    """Run custom guards for ``stage``; exceptions and timeouts fail closed."""
    violations = []
    for guard_id in guard_ids:
        spec = registry.guardrails[guard_id]
        if spec.stage != stage:
            continue
        try:
            if spec.isolation == "process":
                outcome = call_in_process(str(spec.function), [subject, context], timeout, spec.max_output_bytes,
                                          cancel_event)
            else:
                outcome = call_inline(spec.function, [subject, context], timeout, cancel_event)
        except AgenticCancelled:
            raise
        except Exception as exc:
            violations.append(Violation(guard_id, stage, "guard_error", "guardrail failed closed: %s: %s"
                                        % (type(exc).__name__, str(exc)[:300])))
            continue
        if outcome is None:
            continue
        if not isinstance(outcome, dict) or not outcome.get("code") or not outcome.get("reason"):
            violations.append(Violation(guard_id, stage, "guard_error", "guardrail returned an invalid violation"))
            continue
        violations.append(Violation(guard_id, stage, str(outcome["code"]), str(outcome["reason"]),
                                    outcome.get("evidence", {}),
                                    retryable=bool(outcome.get("retryable")) and spec.repairable))
    return violations


GuardFunction = Callable[[Any, Dict[str, Any]], Optional[Dict[str, Any]]]
