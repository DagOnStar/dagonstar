"""A documented, dependency-free subset of JSON Schema.

This is *not* a full JSON Schema implementation.  Supported keywords are
listed in :data:`SUPPORTED_KEYWORDS`; any other keyword is rejected when the
schema is declared, so a schema can never be silently half-checked.
"""
import math
from typing import Any, Dict, List

from dagon.agentic.errors import AgenticValidationError

SUPPORTED_KEYWORDS = frozenset({
    "type", "required", "properties", "items", "enum", "const", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength", "maxLength",
    "additionalProperties", "uniqueItems", "title", "description",
})
_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def check_schema(schema: Any, label: str = "schema", path: str = "$") -> None:
    """Reject schemas that use keywords outside the supported subset."""
    if not isinstance(schema, dict):
        raise AgenticValidationError("%s must be an object at %s" % (label, path))
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS)
    if unknown:
        raise AgenticValidationError(
            "%s uses unsupported JSON Schema keyword(s) %s at %s; the dependency-free subset supports: %s"
            % (label, ", ".join(unknown), path, ", ".join(sorted(SUPPORTED_KEYWORDS))))
    types = schema.get("type")
    if types is not None:
        for item in (types if isinstance(types, list) else [types]):
            if item not in _TYPES:
                raise AgenticValidationError("%s has unknown type %r at %s" % (label, item, path))
    if "required" in schema and (not isinstance(schema["required"], list)
                                 or not all(isinstance(item, str) for item in schema["required"])):
        raise AgenticValidationError("%s 'required' must be a list of strings at %s" % (label, path))
    for key, child in (schema.get("properties") or {}).items():
        check_schema(child, label, "%s.properties.%s" % (path, key))
    if isinstance(schema.get("items"), dict):
        check_schema(schema["items"], label, path + ".items")
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        check_schema(additional, label, path + ".additionalProperties")
    elif additional is not None and not isinstance(additional, bool):
        raise AgenticValidationError("%s 'additionalProperties' must be a boolean or schema at %s" % (label, path))


def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    return isinstance(value, dict)


def validate(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Return a list of human-readable violations (empty when valid)."""
    errors: List[str] = []
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        if not any(_is_type(instance, name) for name in names):
            return ["%s: expected type %s" % (path, "/".join(names))]
    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected constant %r" % (path, schema["const"]))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: value is not in the enumeration" % path)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: below minimum %s" % (path, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: above maximum %s" % (path, schema["maximum"]))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append("%s: not above exclusive minimum %s" % (path, schema["exclusiveMinimum"]))
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append("%s: not below exclusive maximum %s" % (path, schema["exclusiveMaximum"]))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than %s" % (path, schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s: longer than %s" % (path, schema["maxLength"]))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than %s items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: more than %s items" % (path, schema["maxItems"]))
        if schema.get("uniqueItems"):
            seen = []
            for item in instance:
                if item in seen:
                    errors.append("%s: items are not unique" % path)
                    break
                seen.append(item)
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                errors.extend(validate(item, schema["items"], "%s[%d]" % (path, index)))
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required property %r" % (path, key))
        properties = schema.get("properties") or {}
        for key, child in properties.items():
            if key in instance:
                errors.extend(validate(instance[key], child, "%s.%s" % (path, key)))
        additional = schema.get("additionalProperties")
        extra = [key for key in instance if key not in properties]
        if additional is False and extra:
            errors.append("%s: unexpected properties %s" % (path, ", ".join(sorted(extra))))
        elif isinstance(additional, dict):
            for key in extra:
                errors.extend(validate(instance[key], additional, "%s.%s" % (path, key)))
    return errors
