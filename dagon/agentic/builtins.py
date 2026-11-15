"""Built-in, dependency-free tools, evaluators, guardrails, and adapters.

The default registry contains no shell, browser, network, or external-write
tool.  Built-in tools only read declared, staged JSON inputs and return data.
"""
import json
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from dagon.agentic.errors import AgenticEvaluationError, AgenticValidationError
from dagon.agentic.registry import (AdapterSpec, EvaluatorSpec, GuardrailSpec, Registry, ToolSpec)
from dagon.agentic.schema import check_schema, validate as validate_schema

DEFAULT_FIELD = "observations"
DEFAULT_KEY = "id"


# -- record helpers -----------------------------------------------------------

def extract_records(document: Any, field: Optional[str] = DEFAULT_FIELD) -> Optional[List[Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and field and isinstance(document.get(field), list):
        return document[field]
    return None


def record_ids(records: List[Any], key: str = DEFAULT_KEY) -> List[Any]:
    return [record.get(key) for record in records if isinstance(record, dict) and key in record]


def lookup(document: Any, path: Optional[str]) -> Tuple[bool, Any]:
    """Resolve a dot path (``a.b.0.c``); return ``(found, value)``."""
    if not path:
        return True, document
    value = document
    for part in str(path).split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return False, None
    return True, value


def _load_input(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    name = arguments.get("input")
    descriptor = context.get("inputs", {}).get(name)
    if descriptor is None:
        raise ValueError("unknown input %r; declared inputs: %s" % (name, ", ".join(sorted(context.get("inputs", {})))))
    if descriptor.get("binary"):
        raise ValueError("input %r is a binary artifact and cannot be parsed as records" % name)
    with open(descriptor["path"], encoding="utf-8") as stream:
        return json.load(stream)


# -- tools ----------------------------------------------------------------------

def inspect_records(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Summarise the records of a declared JSON input (read-only)."""
    field = arguments.get("field", DEFAULT_FIELD)
    key = arguments.get("key", DEFAULT_KEY)
    records = extract_records(_load_input(arguments, context), field) or []
    ids = record_ids(records, key)
    seen, duplicates = set(), []
    for item in ids:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    fields = sorted({name for record in records if isinstance(record, dict) for name in record})
    incomplete = sorted({str(record.get(key)) for record in records if isinstance(record, dict)
                         and any(record.get(name) is None for name in fields)})
    return {"input": arguments.get("input"), "count": len(records), "unique_count": len(seen),
            "duplicate_ids": duplicates, "fields": fields, "records_with_null_fields": incomplete}


def repair_records(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a declared JSON input with duplicate records removed and stable ordering."""
    field = arguments.get("field", DEFAULT_FIELD)
    key = arguments.get("key", DEFAULT_KEY)
    document = _load_input(arguments, context)
    records = extract_records(document, field)
    if records is None:
        raise ValueError("input %r has no record list" % arguments.get("input"))
    unique, seen = [], set()
    for record in records:
        identity = json.dumps(record.get(key), sort_keys=True) if isinstance(record, dict) else None
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(record)
    unique.sort(key=lambda record: json.dumps(record.get(key) if isinstance(record, dict) else record,
                                              sort_keys=True))
    repaired = dict(document) if isinstance(document, dict) else {}
    repaired[field] = unique
    return {"document": repaired, "removed_duplicates": len(records) - len(unique)}


_RECORD_ARGUMENTS = {
    "type": "object", "required": ["input"], "additionalProperties": False,
    "properties": {"input": {"type": "string", "minLength": 1, "maxLength": 128},
                   "field": {"type": "string", "minLength": 1, "maxLength": 128},
                   "key": {"type": "string", "minLength": 1, "maxLength": 128}},
}


# -- evaluators -----------------------------------------------------------------

def _result(passed: bool, score: Optional[float], observation: Any, evidence: Any = None) -> Dict[str, Any]:
    return {"status": "pass" if passed else "fail", "score": score, "observation": observation,
            "evidence": evidence or []}


def exact_match(candidate: Any, expected: Any, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    found, value = lookup(candidate, options.get("path"))
    passed = found and value == expected
    return _result(passed, 1.0 if passed else 0.0,
                   {"found": found, "matches": passed, "path": options.get("path") or "$"})


def record_coverage(candidate: Any, expected: Any, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    field = options.get("field", DEFAULT_FIELD)
    key = options.get("key", DEFAULT_KEY)
    records = extract_records(candidate, field)
    if records is None:
        return _result(False, 0.0, {"records": None, "reason": "no record list at %r" % field})
    unique = set(json.dumps(item, sort_keys=True) for item in record_ids(records, key))
    if "ids" in expected:
        wanted = set(json.dumps(item, sort_keys=True) for item in expected["ids"])
        matched = len(wanted & unique)
        denominator = max(len(wanted), len(records))
    else:
        matched = min(len(unique), int(expected["count"]))
        denominator = max(int(expected["count"]), len(records))
    score = matched / denominator if denominator else 1.0
    return _result(score == 1.0, score, {"records": len(records), "unique_ids": len(unique),
                                         "matched": matched, "denominator": denominator})


def _validate_coverage(expected: Any, options: Dict[str, Any]) -> None:
    if not isinstance(expected, dict) or not (("count" in expected) ^ ("ids" in expected)):
        raise AgenticValidationError("record_coverage expects exactly one of {'count': N} or {'ids': [...]}")
    if "count" in expected and (not isinstance(expected["count"], int) or isinstance(expected["count"], bool)
                                or expected["count"] < 0):
        raise AgenticValidationError("record_coverage count must be a non-negative integer")
    if "ids" in expected and not isinstance(expected["ids"], list):
        raise AgenticValidationError("record_coverage ids must be a list")


def numeric_error(candidate: Any, expected: Any, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Normalised absolute error ``s = max(0, 1 - |observed - expected| / scale)``.

    ``scale`` (required, > 0) is expressed in the units of the observed value.
    ``tolerance`` is a separate pass/fail gate; without it, pass means exact equality.
    """
    found, observed = lookup(candidate, options.get("path"))
    if not found or isinstance(observed, bool) or not isinstance(observed, (int, float)) \
            or not math.isfinite(observed):
        return _result(False, 0.0, {"found": found, "reason": "observed value is not a finite number"})
    error = abs(float(observed) - float(expected))
    score = max(0.0, 1.0 - error / float(options["scale"]))
    tolerance = options.get("tolerance")
    passed = error <= float(tolerance) if tolerance is not None else error == 0.0
    return _result(passed, score, {"observed": observed, "absolute_error": error, "scale": options["scale"],
                                   "units": options.get("units"), "tolerance": tolerance})


def _validate_numeric(expected: Any, options: Dict[str, Any]) -> None:
    if isinstance(expected, bool) or not isinstance(expected, (int, float)) or not math.isfinite(expected):
        raise AgenticValidationError("numeric_error expected value must be a finite number")
    scale = options.get("scale")
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
        raise AgenticValidationError("numeric_error requires options.scale > 0 (in the observed value's units)")
    tolerance = options.get("tolerance")
    if tolerance is not None and (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                                  or not math.isfinite(tolerance) or tolerance < 0):
        raise AgenticValidationError("numeric_error tolerance must be a finite, non-negative number")


def schema_conformance(candidate: Any, expected: Any, options: Dict[str, Any],
                       context: Dict[str, Any]) -> Dict[str, Any]:
    schema = expected if expected is not None else context.get("specification", {}).get("output_schema")
    if schema is None:
        raise AgenticEvaluationError("schema_conformance needs expected schema or specification.output_schema")
    errors = validate_schema(candidate, schema)
    return _result(not errors, 0.0 if errors else 1.0, {"violations": errors[:20]})


def _validate_schema(expected: Any, options: Dict[str, Any]) -> None:
    if expected is not None:
        check_schema(expected, "schema_conformance expected")


def reference_match(candidate: Any, expected: Any, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    path = context.get("reference_path")
    if not path:
        raise AgenticEvaluationError("reference_match requires a declared reference artifact")
    with open(path, encoding="utf-8") as stream:
        reference = json.load(stream)
    found_r, reference_value = lookup(reference, options.get("reference_path"))
    found_c, candidate_value = lookup(candidate, options.get("path"))
    passed = found_r and found_c and reference_value == candidate_value
    return _result(passed, 1.0 if passed else 0.0, {"matches": passed}, [context.get("reference_uri")])


# -- guardrails -------------------------------------------------------------------

def preserve_record_ids(candidate: Any, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Result guard: the candidate must keep exactly the record IDs present in the JSON inputs."""
    source: Set[str] = set()
    present = False
    for document in context.get("input_documents", {}).values():
        records = extract_records(document)
        if records is not None:
            present = True
            source.update(json.dumps(item, sort_keys=True) for item in record_ids(records))
    if not present:
        return None
    records = extract_records(candidate) or []
    produced = set(json.dumps(item, sort_keys=True) for item in record_ids(records))
    if produced == source:
        return None
    return {"code": "record_ids_changed", "reason": "the candidate added or removed record IDs",
            "evidence": {"missing": sorted(source - produced)[:20], "added": sorted(produced - source)[:20]},
            "retryable": True}


def non_empty_result(candidate: Any, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if candidate in (None, {}, [], ""):
        return {"code": "empty_result", "reason": "the candidate is empty", "evidence": {}, "retryable": True}
    return None


def read_only_tools(action: Any, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if action.get("side_effect") not in ("none", "read"):
        return {"code": "write_tool_blocked", "reason": "only read-only tools are permitted",
                "evidence": {"tool": action.get("tool")}, "retryable": False}
    return None


# -- adapters (lazy) ----------------------------------------------------------------

def _mock_factory(**options: Any) -> Any:
    from dagon.agentic.providers import MockAdapter
    return MockAdapter(**options)


def _builtin_factory(**options: Any) -> Any:
    """Build the OpenAI-compatible adapter inside its worker; the key comes only from ``api_key_env``."""
    import os

    from dagon.agentic.errors import AgenticConfigurationError
    from dagon.agentic.providers import OpenAICompatibleAdapter
    variable = options.pop("api_key_env", "")
    key = os.environ.get(variable, "") if variable else ""
    if not key:
        raise AgenticConfigurationError("the agent LLM credential is missing: set the environment variable "
                                        "named by api_key_env")
    return OpenAICompatibleAdapter(api_key=key, **options)


# Built-in evaluators and guardrails that only compute over in-memory JSON run inline.
_PURE: Dict[str, Any] = {"isolation": "inline", "side_effect": "none"}


def register_builtins(registry: Registry) -> None:
    registry.register_tool(ToolSpec(
        id="inspect_records", version="1.0.0",
        description="Summarise a declared JSON input's records: count, duplicate IDs, fields, null values.",
        function="dagon.agentic.builtins:inspect_records", arguments_schema=_RECORD_ARGUMENTS,
        result_schema={"type": "object", "required": ["count", "unique_count", "duplicate_ids"]},
        side_effect="read", timeout_seconds=20.0))
    registry.register_tool(ToolSpec(
        id="repair_records", version="1.0.0",
        description="Return a declared JSON input with duplicate record IDs removed and records sorted by ID.",
        function="dagon.agentic.builtins:repair_records", arguments_schema=_RECORD_ARGUMENTS,
        result_schema={"type": "object", "required": ["document", "removed_duplicates"]},
        side_effect="read", timeout_seconds=20.0))
    registry.register_evaluator(EvaluatorSpec(
        "exact_match", "1.0.0", "Value at options.path equals expected.", exact_match, **_PURE))
    registry.register_evaluator(EvaluatorSpec(
        "record_coverage", "1.0.0", "Unique records matched / max(expected, produced records).",
        record_coverage, validate_expected=_validate_coverage, **_PURE))
    registry.register_evaluator(EvaluatorSpec(
        "numeric_error", "1.0.0", "max(0, 1 - |observed - expected| / scale); tolerance is a separate gate.",
        numeric_error, validate_expected=_validate_numeric, **_PURE))
    registry.register_evaluator(EvaluatorSpec(
        "schema_conformance", "1.0.0", "Candidate conforms to the dependency-free JSON Schema subset.",
        schema_conformance, validate_expected=_validate_schema, **_PURE))
    registry.register_evaluator(EvaluatorSpec(
        "reference_match", "1.0.0", "Candidate value equals the value in a declared reference artifact.",
        "dagon.agentic.builtins:reference_match", side_effect="read"))
    registry.register_guardrail(GuardrailSpec(
        "preserve_record_ids", "1.0.0", "Candidate keeps exactly the input record IDs.", "result",
        preserve_record_ids, repairable=True, **_PURE))
    registry.register_guardrail(GuardrailSpec(
        "non_empty_result", "1.0.0", "Candidate is not empty.", "result", non_empty_result, repairable=True, **_PURE))
    registry.register_guardrail(GuardrailSpec(
        "read_only_tools", "1.0.0", "Only side-effect-free or read-only tools may run.", "pre_action",
        read_only_tools, **_PURE))
    # Adapters run in a supervised worker process for the whole run (killed on timeout or cancellation).
    registry.register_adapter(AdapterSpec("mock", "1.0.0", "dagon.agentic.builtins:_mock_factory",
                                          requires_llm=False, side_effect="read"))
    registry.register_adapter(AdapterSpec("builtin", "1.0.0", "dagon.agentic.builtins:_builtin_factory",
                                          requires_llm=True))
