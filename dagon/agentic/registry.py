"""Explicit registries for agent tools, evaluators, guardrails, and adapters.

Registration is trusted application setup performed by Python code before a
workflow runs.  Neither a task declaration, a ``dagon.ini`` value, nor a model
response can register or import code: configuration only *selects* registered
identifiers.  An allowlist is not an operating-system sandbox; register only
implementations you trust.

Every component with code (tools, evaluators, guardrails, adapters) runs in a
supervised process by default, so a timeout or cancellation kills it and its
descendants.  ``isolation="inline"`` (a thread that cannot be stopped) is
accepted only for components registered with ``side_effect="none"``.
"""
import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Union

from dagon.agentic.errors import AgenticConfigurationError, AgenticValidationError
from dagon.agentic.schema import check_schema

SIDE_EFFECTS = ("none", "read", "scratch_write")
ISOLATION = ("process", "inline")
GUARD_STAGES = ("input", "pre_action", "post_action", "result")
EVALUATOR_KINDS = ("deterministic", "model_judge")

FunctionRef = Union[str, Callable[..., Any]]


def _check_isolation(kind: str, isolation: str, side_effect: Optional[str], function: Any) -> None:
    """Process isolation needs an importable reference; inline needs a side-effect-free declaration."""
    if isolation not in ISOLATION:
        raise AgenticValidationError("%s isolation must be one of %s" % (kind, ", ".join(ISOLATION)))
    if side_effect is not None and side_effect not in SIDE_EFFECTS:
        raise AgenticValidationError("%s side_effect must be one of %s" % (kind, ", ".join(SIDE_EFFECTS)))
    if isolation == "inline" and side_effect != "none":
        raise AgenticValidationError("only %ss registered with side_effect='none' may run inline (a thread "
                                     "cannot be stopped at its deadline); use isolation='process'" % kind)
    if isolation == "process" and not (isinstance(function, str) and ":" in function):
        raise AgenticValidationError("process-isolated %ss need an importable 'module:function' reference" % kind)
    if isolation == "inline" and not (callable(function) or (isinstance(function, str) and ":" in function)):
        raise AgenticValidationError("%s function must be callable or a 'module:function' reference" % kind)


def _check_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or not all(ch.isalnum() or ch in "_-." for ch in value):
        raise AgenticValidationError("%s must be a non-empty identifier of letters, digits, '_', '-', '.'" % label)


@dataclass(frozen=True)
class ToolSpec:
    """A registered tool: ``function(arguments, context) -> JSON``."""

    id: str
    version: str
    description: str
    function: FunctionRef
    arguments_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    result_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    side_effect: str = "none"
    timeout_seconds: float = 10.0
    max_output_bytes: int = 65536
    isolation: str = "process"

    def public(self) -> Dict[str, Any]:
        return {"id": self.id, "version": self.version, "description": self.description,
                "arguments_schema": self.arguments_schema, "side_effect": self.side_effect}


@dataclass(frozen=True)
class EvaluatorSpec:
    """A registered evaluator: ``function(candidate, expected, options, context) -> dict``."""

    id: str
    version: str
    description: str
    function: FunctionRef
    kind: str = "deterministic"
    isolation: str = "process"
    timeout_seconds: float = 10.0
    validate_expected: Optional[Callable[[Any, Dict[str, Any]], None]] = None
    side_effect: Optional[str] = None


@dataclass(frozen=True)
class GuardrailSpec:
    """A registered guardrail: ``function(subject, context) -> None | violation dict``."""

    id: str
    version: str
    description: str
    stage: str
    function: FunctionRef
    repairable: bool = False
    isolation: str = "process"
    side_effect: Optional[str] = None
    max_output_bytes: int = 1024 * 1024


@dataclass(frozen=True)
class AdapterSpec:
    """A registered agent adapter (``implementation`` value in ``[agent_provider.*]``).

    With process isolation (the default) ``factory`` is an importable
    ``module:function`` called inside a supervised worker with JSON options.
    """

    id: str
    version: str
    factory: FunctionRef
    requires_llm: bool = False
    isolation: str = "process"
    side_effect: Optional[str] = None


class Registry:
    """A copyable set of named, versioned capabilities."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.tools: Dict[str, ToolSpec] = {}
        self.evaluators: Dict[str, EvaluatorSpec] = {}
        self.guardrails: Dict[str, GuardrailSpec] = {}
        self.adapters: Dict[str, AdapterSpec] = {}

    def copy(self) -> "Registry":
        clone = Registry()
        with self._lock:
            clone.tools = dict(self.tools)
            clone.evaluators = dict(self.evaluators)
            clone.guardrails = dict(self.guardrails)
            clone.adapters = dict(self.adapters)
        return clone

    @staticmethod
    def _store(table: Dict[str, Any], spec: Any, kind: str, replace: bool) -> None:
        _check_identifier(spec.id, kind + " id")
        if not isinstance(spec.version, str) or not spec.version:
            raise AgenticValidationError("%s %s needs a version string" % (kind, spec.id))
        if spec.id in table and not replace and table[spec.id] != spec:
            raise AgenticConfigurationError("%s %s is already registered (pass replace=True to override)"
                                            % (kind, spec.id))
        table[spec.id] = spec

    def register_tool(self, spec: ToolSpec, replace: bool = False) -> ToolSpec:
        if spec.side_effect not in SIDE_EFFECTS:
            raise AgenticValidationError("tool side_effect must be one of %s" % ", ".join(SIDE_EFFECTS))
        if spec.side_effect == "external_write":
            raise AgenticValidationError("external write tools are not supported in v1")
        if spec.isolation not in ISOLATION:
            raise AgenticValidationError("tool isolation must be one of %s" % ", ".join(ISOLATION))
        if spec.isolation == "inline" and spec.side_effect != "none":
            raise AgenticValidationError("only side-effect-free tools may run inline (thread deadlines cannot "
                                         "stop side effects); use isolation='process'")
        if spec.isolation == "process" and not (isinstance(spec.function, str) and ":" in spec.function):
            raise AgenticValidationError("process-isolated tools need an importable 'module:function' reference")
        if not (0 < float(spec.timeout_seconds) < float("inf")) or int(spec.max_output_bytes) <= 0:
            raise AgenticValidationError("tool timeout and output bound must be finite and positive")
        check_schema(spec.arguments_schema, "tool %s arguments_schema" % spec.id)
        check_schema(spec.result_schema, "tool %s result_schema" % spec.id)
        with self._lock:
            self._store(self.tools, spec, "tool", replace)
        return spec

    def register_evaluator(self, spec: EvaluatorSpec, replace: bool = False) -> EvaluatorSpec:
        if spec.kind not in EVALUATOR_KINDS:
            raise AgenticValidationError("evaluator kind must be one of %s" % ", ".join(EVALUATOR_KINDS))
        _check_isolation("evaluator", spec.isolation, spec.side_effect, spec.function)
        if not (0 < float(spec.timeout_seconds) < float("inf")):
            raise AgenticValidationError("evaluator timeout must be finite and positive")
        with self._lock:
            self._store(self.evaluators, spec, "evaluator", replace)
        return spec

    def register_guardrail(self, spec: GuardrailSpec, replace: bool = False) -> GuardrailSpec:
        if spec.stage not in GUARD_STAGES:
            raise AgenticValidationError("guardrail stage must be one of %s" % ", ".join(GUARD_STAGES))
        _check_isolation("guardrail", spec.isolation, spec.side_effect, spec.function)
        if int(spec.max_output_bytes) <= 0:
            raise AgenticValidationError("guardrail output bound must be positive")
        with self._lock:
            self._store(self.guardrails, spec, "guardrail", replace)
        return spec

    def register_adapter(self, spec: AdapterSpec, replace: bool = False) -> AdapterSpec:
        _check_isolation("adapter", spec.isolation, spec.side_effect, spec.factory)
        with self._lock:
            self._store(self.adapters, spec, "adapter", replace)
        return spec

    def versions(self, kind: str, ids: Any) -> Dict[str, str]:
        table = getattr(self, kind)
        return {item: table[item].version for item in sorted(set(ids)) if item in table}


_DEFAULT: Optional[Registry] = None
_DEFAULT_LOCK = threading.Lock()


def default_registry() -> Registry:
    """Return the process-wide registry, populated with the built-in capabilities."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            registry = Registry()
            from dagon.agentic import builtins
            builtins.register_builtins(registry)
            _DEFAULT = registry
        return _DEFAULT


def register_tool(spec: ToolSpec, replace: bool = False) -> ToolSpec:
    return default_registry().register_tool(spec, replace)


def register_evaluator(spec: EvaluatorSpec, replace: bool = False) -> EvaluatorSpec:
    return default_registry().register_evaluator(spec, replace)


def register_guardrail(spec: GuardrailSpec, replace: bool = False) -> GuardrailSpec:
    return default_registry().register_guardrail(spec, replace)


def register_adapter(spec: AdapterSpec, replace: bool = False) -> AdapterSpec:
    return default_registry().register_adapter(spec, replace)


def snapshot() -> Registry:
    """Return a copy of the default registry (used to keep tests isolated)."""
    return copy.copy(default_registry()).copy()
