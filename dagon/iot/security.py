"""Credential-safe JSON helpers shared by IoT artifacts and checkpoints."""
import json
from typing import Any


SECRET_KEYS = {"password", "passwd", "secret", "token", "access_token", "refresh_token",
               "authorization", "api_key", "apikey", "private_key", "client_secret",
               "certificate", "signed_url"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            lowered = str(key).lower()
            result[key] = "[REDACTED]" if lowered in SECRET_KEYS else redact(child)
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if isinstance(value, set):
            items = sorted(items, key=str)
        return [redact(item) for item in items]
    return value


def json_copy(value: Any, label: str = "IoT value") -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("%s must be JSON-serializable" % label) from exc
