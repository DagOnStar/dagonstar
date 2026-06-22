"""Scratch-directory HTTP request runner for :class:`dagon.web.WebTask`."""

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dagon.web.schema import safe_output_path, validate


def _auth(spec: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any], Dict[str, Any]]:
    auth = spec.get("auth") or {"type": "none"}
    kind = auth.get("type", "none")
    headers, query = {}, {}
    metadata = {"type": kind}
    if kind == "bearer":
        env = auth["token_env"]
        headers["Authorization"] = "Bearer " + os.environ[env]
        metadata["source"] = "env:" + env
    elif kind == "basic":
        import base64
        user_env, password_env = auth["username_env"], auth["password_env"]
        token = base64.b64encode((os.environ[user_env] + ":" + os.environ[password_env]).encode()).decode()
        headers["Authorization"] = "Basic " + token
        metadata["source"] = "env:%s,env:%s" % (user_env, password_env)
    elif kind == "api_key_header":
        env = auth["value_env"]
        headers[auth["header"]] = os.environ[env]
        metadata["source"] = "env:" + env
    elif kind == "api_key_query":
        env = auth["value_env"]
        query[auth["parameter"]] = os.environ[env]
        metadata["source"] = "env:" + env
    return headers, query, metadata


def _multipart(values: Dict[str, Any], root: Path) -> Tuple[bytes, str]:
    boundary = "----dagon-" + uuid.uuid4().hex
    chunks = []
    for name, binding in values.items():
        chunks.append(("--%s\r\n" % boundary).encode())
        if "file" in binding:
            file_path = root / binding["file"]
            chunks.append(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, file_path.name)).encode())
            chunks.append(("Content-Type: %s\r\n\r\n" % binding.get("content_type", "application/octet-stream")).encode())
            chunks.append(file_path.read_bytes())
        else:
            value = binding.get("value", "")
            if not isinstance(value, str):
                value = json.dumps(value)
            chunks.append(('Content-Disposition: form-data; name="%s"\r\n' % name).encode())
            chunks.append(("Content-Type: %s\r\n\r\n" % binding.get("content_type", "text/plain")).encode())
            chunks.append(value.encode())
        chunks.append(b"\r\n")
    chunks.append(("--%s--\r\n" % boundary).encode())
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def run(spec_path: str) -> Dict[str, Any]:
    spec_file = Path(spec_path).resolve()
    root = spec_file.parent.parent
    spec = validate(json.loads(spec_file.read_text(encoding="utf-8")))
    auth_headers, auth_query, auth_meta = _auth(spec)
    headers = dict(spec.get("headers") or {}, **auth_headers)
    query = dict(spec.get("query") or {}, **auth_query)
    url = spec["url"] + (("&" if "?" in spec["url"] else "?") + urlencode(query, doseq=True) if query else "")
    payload = None
    if spec.get("multipart"):
        payload, content_type = _multipart(spec["multipart"], root)
        headers.setdefault("Content-Type", content_type)
    elif "json" in spec:
        payload = json.dumps(spec["json"]).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif spec.get("data") is not None:
        payload = urlencode(spec["data"], doseq=True).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    retry_on = set(spec.get("retry_on", [429, 500, 502, 503, 504]))
    retries = spec["retries"] if spec["method"] in {"GET", "HEAD", "PUT", "DELETE"} or spec.get("retry_unsafe") else 0
    started = time.monotonic()
    for attempt in range(retries + 1):
        try:
            with urlopen(Request(url, data=payload, headers=headers, method=spec["method"]), timeout=spec.get("timeout")) as response:
                status, body, response_headers = response.status, response.read(), dict(response.headers.items())
        except HTTPError as exc:
            status, body, response_headers = exc.code, exc.read(), dict(exc.headers.items())
        except URLError:
            if attempt >= retries:
                raise
            time.sleep(spec["retry_backoff"] * (attempt + 1))
            continue
        if status in retry_on and attempt < retries:
            time.sleep(spec["retry_backoff"] * (attempt + 1))
            continue
        break
    expected = spec.get("expected_status")
    accepted = set(expected if isinstance(expected, list) else [expected]) if expected is not None else set(range(200, 300))
    outputs = spec.get("outputs") or {}
    def write_output(key: str, value: Any, binary: bool = False) -> str:
        relative = "outputs/" + safe_output_path(outputs[key])
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value) if binary else target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return relative
    body_path = write_output("body", body, True) if "body" in outputs else None
    headers_path = write_output("headers", response_headers) if "headers" in outputs else None
    metadata = {"method": spec["method"], "url": spec["url"], "status_code": status,
                "elapsed_seconds": time.monotonic() - started, "content_type": response_headers.get("Content-Type"),
                "body_path": body_path, "headers_path": headers_path, "sha256": hashlib.sha256(body).hexdigest(), "auth": auth_meta}
    result_path = root / ".dagon/web_result.json"
    result_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if "metadata" in outputs:
        write_output("metadata", metadata)
    if status not in accepted:
        raise RuntimeError("Unexpected HTTP status %s" % status)
    return metadata


def main() -> int:
    run(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
