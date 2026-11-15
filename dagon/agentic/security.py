"""Redaction, JSON hygiene, hashing, and path containment for agentic tasks.

These helpers implement *data* hygiene.  They are not an operating-system
sandbox: registered tools and evaluators are trusted application code.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Optional

from dagon.agentic.errors import AgenticValidationError

SECRET_KEYS = frozenset({
    "password", "passwd", "secret", "token", "access_token", "refresh_token", "authorization",
    "api_key", "apikey", "x-api-key", "private_key", "client_secret", "certificate", "signed_url",
    "cookie", "bearer",
})
REDACTED = "[REDACTED]"


def redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    """Return a deep copy with secret-named keys and known secret values masked."""
    known = [item for item in secrets if isinstance(item, str) and len(item) >= 4]

    def _walk(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: (REDACTED if str(key).lower() in SECRET_KEYS else _walk(child))
                    for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [_walk(child) for child in item]
        if isinstance(item, str):
            for secret in known:
                if secret in item:
                    item = item.replace(secret, REDACTED)
            return item
        return item

    return _walk(value)


def redact_text(text: str, secrets: Iterable[str] = (), limit: int = 2000) -> str:
    """Mask known secret values in free text and bound its length."""
    value = str(text)
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 4:
            value = value.replace(secret, REDACTED)
    return value if len(value) <= limit else value[:limit] + "...[truncated]"


def _check_json(value: Any, label: str, path: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise AgenticValidationError("%s contains a non-finite number at %s" % (label, path))
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AgenticValidationError("%s has a non-string key at %s" % (label, path))
            _check_json(child, label, path + "." + key)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_json(child, label, "%s[%d]" % (path, index))
        return
    raise AgenticValidationError("%s is not JSON-compatible at %s (%s)" % (label, path, type(value).__name__))


def json_copy(value: Any, label: str = "value") -> Any:
    """Return a JSON round-tripped copy; reject NaN, infinity, and non-JSON values."""
    _check_json(value, label, "$")
    return json.loads(json.dumps(value, allow_nan=False))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(os.fspath(path), "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_path(value: Any, label: str = "path") -> str:
    """Validate a relative POSIX path that must stay inside a task directory.

    Rejects empty values, absolute POSIX paths, Windows drive and UNC paths,
    backslashes, ``..`` components, and NUL bytes.  Returns the normalised
    POSIX form.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AgenticValidationError("%s must be a non-empty relative path" % label)
    if "\\" in value or value.startswith("//") or PureWindowsPath(value).drive or PureWindowsPath(value).root:
        raise AgenticValidationError("%s must not be a Windows drive, UNC, or backslash path: %s" % (label, value))
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts:
        raise AgenticValidationError("%s must be relative and stay inside its directory: %s" % (label, value))
    normalised = posix.as_posix()
    if normalised in ("", "."):
        raise AgenticValidationError("%s must name a file: %s" % (label, value))
    return normalised


def contained_path(root: Any, relative: str, label: str = "path", must_exist: bool = False) -> Path:
    """Resolve ``root/relative`` and refuse results (including symlinks) outside ``root``."""
    base = Path(os.fspath(root)).resolve()
    candidate = base.joinpath(*PurePosixPath(safe_relative_path(relative, label)).parts)
    resolved = candidate.resolve()
    if resolved != base and base not in resolved.parents:
        raise AgenticValidationError("%s escapes its directory through a symbolic link: %s" % (label, relative))
    if must_exist and not resolved.is_file():
        raise FileNotFoundError("%s does not exist: %s" % (label, relative))
    return candidate


def bounded_dumps(value: Any, limit: Optional[int]) -> str:
    text = json.dumps(value, sort_keys=True, allow_nan=False)
    if limit is not None and len(text.encode("utf-8")) > limit:
        raise ValueError("serialized size %d exceeds the %d-byte bound" % (len(text.encode("utf-8")), limit))
    return text


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` through a temporary sibling file and ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise AgenticValidationError("refusing to publish through a symbolic link: %s" % path.name)
    temporary = path.with_name("." + path.name + ".tmp")
    with open(str(temporary), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))
