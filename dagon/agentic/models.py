"""Formal agentic-task contract ``A = (S, R, I, O, P, T, G, E, B)``.

``S`` specification, ``R`` requirements, ``I`` inputs, ``O`` outputs, ``P`` the
named agent profile (resolved from ``dagon.ini``), ``T`` optional tool
restrictions, ``G`` additional guardrails, ``E`` evaluation, ``B`` budget
restrictions.  :func:`normalize_contract` validates a declaration and returns a
JSON-compatible, deterministic contract that never contains endpoints, keys,
callables, or temporary paths.
"""
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dagon.agentic.errors import AgenticValidationError
from dagon.agentic.registry import Registry, default_registry
from dagon.agentic.schema import check_schema
from dagon.agentic.security import json_copy, safe_relative_path, sha256_json

SCHEMA_VERSION = 1
SPECIFICATION_FIELDS = {"schema_version", "objective", "context", "output_schema", "constraints"}
REQUIREMENT_FIELDS = {"id", "description", "evaluator", "expected", "weight", "mandatory", "minimum_score",
                      "hard", "options", "reference"}
EVALUATION_FIELDS = {"aggregation", "threshold"}
AGGREGATIONS = {"weighted_mean"}
OUTPUT_NAMES = {"result", "evaluation", "trace"}
DEFAULT_OUTPUTS = {"result": "outputs/result.json", "evaluation": "outputs/evaluation.json",
                   "trace": "outputs/trace.json"}
INPUT_FIELDS = {"uri", "media_type", "binary"}
BUDGET_KEYS = {"max_steps": int, "max_tool_calls": int, "max_attempts": int, "timeout_seconds": float,
               "max_tokens": int, "max_tool_output_bytes": int, "max_trace_bytes": int}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_REFERENCE = re.compile(r"workflow://[^\s\"'\],}]+")
_SINGLE_REFERENCE = re.compile(r"^workflow://[^\s\"'\],}]*$")


def _finite(value: Any, label: str, low: Optional[float] = None, high: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AgenticValidationError("%s must be a finite number" % label)
    if low is not None and value < low or high is not None and value > high:
        raise AgenticValidationError("%s must be within [%s, %s]" % (label, low, high))
    return float(value)


def _unknown(value: Dict[str, Any], allowed: Iterable[str], label: str) -> None:
    extra = sorted(set(value) - set(allowed))
    if extra:
        raise AgenticValidationError("%s has unknown field(s): %s" % (label, ", ".join(extra)))


def parse_reference(reference: str) -> Tuple[str, str, str]:
    """Split ``workflow://<wf>/<task>/<path>`` (``<wf>`` may be empty) and validate the path."""
    if not reference.startswith("workflow://"):
        raise AgenticValidationError("not a workflow reference: %s" % reference)
    pieces = reference[len("workflow://"):].split("/")
    if len(pieces) < 3 or not pieces[1] or not "/".join(pieces[2:]):
        raise AgenticValidationError("invalid workflow reference: %s" % reference)
    return pieces[0], pieces[1], safe_relative_path("/".join(pieces[2:]), "workflow reference path")


def contract_references(contract: Dict[str, Any]) -> List[str]:
    """Return every ``workflow://`` reference in the contract, deduplicated, in discovery order."""
    from dagon.iot.references import references
    seen: List[str] = []
    for part in ("inputs", "specification", "requirements", "evaluation"):
        for reference in references(contract.get(part)):
            if reference not in seen:
                seen.append(reference)
    return seen


def _normalize_inputs(inputs: Any) -> Dict[str, Dict[str, Any]]:
    if inputs is None:
        return {}
    if not isinstance(inputs, dict):
        raise AgenticValidationError("inputs must map names to workflow:// references")
    result = {}
    for name, value in inputs.items():
        if not isinstance(name, str) or not _IDENTIFIER.match(name):
            raise AgenticValidationError("input name must be an identifier: %r" % (name,))
        descriptor = {"uri": value} if isinstance(value, str) else value
        if not isinstance(descriptor, dict):
            raise AgenticValidationError("input %s must be a workflow:// string or a descriptor" % name)
        _unknown(descriptor, INPUT_FIELDS, "input %s" % name)
        uri = descriptor.get("uri")
        if not isinstance(uri, str) or not _SINGLE_REFERENCE.match(uri):
            raise AgenticValidationError("input %s must be exactly one workflow:// reference" % name)
        parse_reference(uri)
        binary = descriptor.get("binary", False)
        if not isinstance(binary, bool):
            raise AgenticValidationError("input %s binary must be a boolean" % name)
        media = descriptor.get("media_type", "application/octet-stream" if binary else "application/json")
        if not isinstance(media, str) or not media:
            raise AgenticValidationError("input %s media_type must be a string" % name)
        result[name] = {"uri": uri, "media_type": media, "binary": binary}
    return result


def _normalize_requirements(requirements: Any, registry: Registry) -> List[Dict[str, Any]]:
    if not isinstance(requirements, list) or not requirements:
        raise AgenticValidationError("requirements must be a non-empty list")
    result, ids = [], set()
    for index, item in enumerate(requirements):
        label = "requirement[%d]" % index
        if not isinstance(item, dict):
            raise AgenticValidationError(label + " must be an object")
        _unknown(item, REQUIREMENT_FIELDS, label)
        identifier = item.get("id")
        if not isinstance(identifier, str) or not _IDENTIFIER.match(identifier):
            raise AgenticValidationError(label + " needs an identifier 'id'")
        if identifier in ids:
            raise AgenticValidationError("duplicate requirement id: %s" % identifier)
        ids.add(identifier)
        label = "requirement %s" % identifier
        evaluator = item.get("evaluator")
        if evaluator not in registry.evaluators:
            raise AgenticValidationError("%s uses unsupported evaluator %r; registered: %s"
                                         % (label, evaluator, ", ".join(sorted(registry.evaluators))))
        mandatory = item.get("mandatory", False)
        hard = item.get("hard", False)
        if not isinstance(mandatory, bool) or not isinstance(hard, bool):
            raise AgenticValidationError(label + " mandatory/hard must be booleans")
        options = item.get("options", {})
        if not isinstance(options, dict):
            raise AgenticValidationError(label + " options must be an object")
        weight = _finite(item.get("weight", 1.0), label + " weight", 0.0)
        minimum = item.get("minimum_score")
        if minimum is not None:
            minimum = _finite(minimum, label + " minimum_score", 0.0, 1.0)
        elif mandatory:
            minimum = 1.0
        reference = item.get("reference")
        if reference is not None:
            if not isinstance(reference, str) or not _SINGLE_REFERENCE.match(reference):
                raise AgenticValidationError(label + " reference must be one workflow:// reference")
            parse_reference(reference)
        description = item.get("description", "")
        if not isinstance(description, str):
            raise AgenticValidationError(label + " description must be a string")
        normalized = {"id": identifier, "description": description, "evaluator": evaluator,
                      "expected": json_copy(item.get("expected"), label + " expected"), "weight": weight,
                      "mandatory": mandatory, "minimum_score": minimum, "hard": hard,
                      "options": json_copy(options, label + " options"), "reference": reference}
        spec = registry.evaluators[evaluator]
        if evaluator == "reference_match" and reference is None:
            raise AgenticValidationError(label + " uses reference_match and must declare a reference artifact")
        if spec.validate_expected is not None:
            spec.validate_expected(normalized["expected"], normalized["options"])
        result.append(normalized)
    if not any(item["weight"] > 0 for item in result):
        raise AgenticValidationError("at least one requirement must have a positive weight")
    return result


def _normalize_specification(specification: Any) -> Dict[str, Any]:
    if not isinstance(specification, dict):
        raise AgenticValidationError("specification must be an object")
    _unknown(specification, SPECIFICATION_FIELDS, "specification")
    version = specification.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise AgenticValidationError("unsupported specification schema_version %r (supported: 1)" % (version,))
    objective = specification.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise AgenticValidationError("specification.objective must be a non-empty string")
    if "context" in specification and not isinstance(specification["context"], str):
        raise AgenticValidationError("specification.context must be a string")
    constraints = specification.get("constraints", [])
    if not isinstance(constraints, list) or not all(isinstance(item, str) for item in constraints):
        raise AgenticValidationError("specification.constraints must be a list of strings")
    if specification.get("output_schema") is not None:
        check_schema(specification["output_schema"], "specification.output_schema")
    result = json_copy(specification, "specification")
    result["schema_version"] = SCHEMA_VERSION
    return result


def _normalize_outputs(outputs: Any) -> Dict[str, str]:
    values = dict(DEFAULT_OUTPUTS)
    if outputs is not None:
        if not isinstance(outputs, dict):
            raise AgenticValidationError("outputs must map result/evaluation/trace to relative paths")
        _unknown(outputs, OUTPUT_NAMES, "outputs")
        values.update(outputs)
    normalized = {}
    for name, value in values.items():
        path = safe_relative_path(value, "output %s" % name)
        if path == ".dagon" or path.startswith(".dagon/"):
            raise AgenticValidationError("output %s must not be inside the reserved .dagon directory" % name)
        normalized[name] = path
    paths = list(normalized.values())
    if len(set(paths)) != len(paths):
        raise AgenticValidationError("output paths must be unique; evaluation and trace paths are reserved")
    for name, path in normalized.items():
        for other_name, other in normalized.items():
            if name != other_name and other.startswith(path + "/"):
                raise AgenticValidationError("output %s cannot be a parent directory of %s" % (name, other_name))
    return normalized


def _normalize_ids(value: Any, label: str) -> Optional[List[str]]:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item for item in value):
        raise AgenticValidationError("%s must be a list of identifiers" % label)
    if len(set(value)) != len(value):
        raise AgenticValidationError("%s contains duplicates" % label)
    return list(value)


def normalize_budgets(budgets: Any, label: str = "budgets") -> Dict[str, Any]:
    if budgets is None:
        return {}
    if not isinstance(budgets, dict):
        raise AgenticValidationError("%s must be an object" % label)
    _unknown(budgets, BUDGET_KEYS, label)
    result: Dict[str, Any] = {}
    for key, value in budgets.items():
        number = _finite(value, "%s.%s" % (label, key))
        if number <= 0:
            raise AgenticValidationError("%s.%s must be positive" % (label, key))
        if BUDGET_KEYS[key] is int:
            if int(number) != number:
                raise AgenticValidationError("%s.%s must be an integer" % (label, key))
            result[key] = int(number)
        else:
            result[key] = number
    return result


def normalize_contract(agent: Any, specification: Any, requirements: Any, evaluation: Any = None,
                       inputs: Any = None, outputs: Any = None, tools: Any = None, guardrails: Any = None,
                       budgets: Any = None, registry: Optional[Registry] = None) -> Dict[str, Any]:
    """Validate a declaration and return its normalized, JSON-compatible contract."""
    registry = registry or default_registry()
    if not isinstance(agent, str) or not _IDENTIFIER.match(agent):
        raise AgenticValidationError("agent must name a [agent.<name>] profile in dagon.ini")
    evaluation = {} if evaluation is None else evaluation
    if not isinstance(evaluation, dict):
        raise AgenticValidationError("evaluation must be an object")
    _unknown(evaluation, EVALUATION_FIELDS, "evaluation")
    aggregation = evaluation.get("aggregation", "weighted_mean")
    if aggregation not in AGGREGATIONS:
        raise AgenticValidationError("unsupported aggregation %r (supported: weighted_mean)" % (aggregation,))
    threshold = _finite(evaluation.get("threshold", 1.0), "evaluation.threshold", 0.0, 1.0)
    tool_ids = _normalize_ids(tools, "tools")
    guard_ids = _normalize_ids(guardrails, "guardrails") or []
    for item in tool_ids or []:
        if item not in registry.tools:
            raise AgenticValidationError("unknown tool %r; registered: %s" % (item, ", ".join(sorted(registry.tools))))
    for item in guard_ids:
        if item not in registry.guardrails:
            raise AgenticValidationError("unknown guardrail %r; registered: %s"
                                         % (item, ", ".join(sorted(registry.guardrails))))
    contract = {
        "schema_version": SCHEMA_VERSION,
        "agent": agent,
        "specification": _normalize_specification(specification),
        "requirements": _normalize_requirements(requirements, registry),
        "evaluation": {"aggregation": aggregation, "threshold": threshold},
        "inputs": _normalize_inputs(inputs),
        "outputs": _normalize_outputs(outputs),
        "tools": tool_ids,
        "guardrails": sorted(guard_ids),
        "budgets": normalize_budgets(budgets),
    }
    for reference in contract_references(contract):
        parse_reference(reference)
    return contract


def contract_digest(contract: Dict[str, Any]) -> str:
    return sha256_json(contract)


def golden_fit(weights: List[float], scores: List[float]) -> float:
    """Documented helper: ``F = sum(w_i * s_i) / sum(w_i)``."""
    return sum(w * s for w, s in zip(weights, scores)) / sum(weights)
