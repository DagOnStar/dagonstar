"""Validation helpers for JSON-serializable web task specifications."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable


def safe_output_path(value: str) -> str:
    item = Path(value)
    if not value or item.is_absolute() or ".." in item.parts:
        raise ValueError("Web output paths must be relative and stay inside scratch: %s" % value)
    return item.as_posix()


def validate(spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("Web task specification must be a dictionary")
    try:
        json.dumps(spec)
    except (TypeError, ValueError) as exc:
        raise ValueError("Web task specification must be JSON-serializable") from exc
    method = spec.get("method", "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise ValueError("Unsupported HTTP method: %s" % method)
    url = spec.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("Web task URL must use http:// or https://")
    for name in ("query", "headers", "data", "multipart", "outputs"):
        if spec.get(name) is not None and not isinstance(spec[name], dict):
            raise ValueError("Web task %s must be a dictionary" % name)
    if spec.get("retries", 0) < 0:
        raise ValueError("Web task retries must be non-negative")
    if spec.get("outputs"):
        for output in spec["outputs"].values():
            safe_output_path(output)
    auth = spec.get("auth")
    if auth is not None:
        if not isinstance(auth, dict) or auth.get("type", "none") not in {
                "none", "bearer", "basic", "api_key_header", "api_key_query"}:
            raise ValueError("Unsupported web authentication configuration")
        if any(key in auth for key in ("token", "password", "value", "secret")):
            raise ValueError("Web authentication secrets must be supplied through environment variables")
    result = dict(spec)
    result["method"] = method
    result.setdefault("retries", 0)
    result.setdefault("retry_backoff", 0.0)
    return result


def references(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield from re.findall(r"workflow://[^\s\"'\],}]+", value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)
