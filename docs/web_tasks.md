# Web Tasks

`TaskType.WEB` makes one declarative HTTP or HTTPS request a first-class
DAGonStar task. It is intended for service calls that form part of a workflow:
retrieving a dataset, submitting a job, updating a record, uploading an
artifact, or checking an endpoint. The request runs in the task scratch
directory, so its response can become an explicit input to downstream tasks.

This guide is a reference for the implementation in this repository. For a
self-contained local upload demonstration, see the
[Web task tutorial](tutorial/lesson_13_web_tasks.md).

## Quick start: an unauthenticated GET request

Create a web task with `DagonTask`. The request specification must be a
JSON-serializable dictionary and its URL must begin with `http://` or
`https://`.

```python
from dagon.task import DagonTask, TaskType

forecast = DagonTask(
    TaskType.WEB,
    "download-forecast",
    {
        "method": "GET",
        "url": "https://api.example.org/forecast",
        "query": {"station": "napoli", "format": "json"},
        "headers": {"Accept": "application/json"},
        "expected_status": [200],
        "outputs": {
            "body": "forecast.json",
            "headers": "response-headers.json",
            "metadata": "request-metadata.json",
        },
    },
)
```

The runner encodes `query` with standard URL encoding and appends it to the
URL. It writes the response body, unchanged, to
`outputs/forecast.json`. The filename is conventional only: DAGonStar does not
parse or validate response JSON. Header and metadata outputs are JSON files.

## Execution model and task constructor

The effective constructor is:

```python
DagonTask(
    TaskType.WEB,
    name,
    specification,
    executor="local",
    resources=None,
    python=sys.executable,
    working_dir=None,
    environment=None,
    globusendpoint=None,
)
```

`executor` is either `"local"` (the default) or `"slurm"`. With the local
executor, DAGonStar invokes the configured Python interpreter as
`python -m dagon.web.runner` in the web task directory. With `"slurm"`, it
creates and submits a Slurm launcher; `resources` accepts the scheduler options
used by the existing Slurm task support, such as `partition`, `ntasks`, and
`time`. The HTTP request is therefore made from the machine on which the task
executes. A URL reachable from a laptop may not be reachable from a compute
node.

`environment` adds or overrides environment variables for the task process.
It is useful when an enclosing launcher injects credentials, but avoid storing
secret values in workflow source, serialized task data, or version control.
Prefer setting credential variables in the job environment or a local ignored
configuration mechanism.

## Request specification

The following fields are supported.

| Field | Type | Meaning |
| --- | --- | --- |
| `method` | string | HTTP method; defaults to `GET`. Supported values are `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and `HEAD`. |
| `url` | string | Required HTTP/HTTPS endpoint. |
| `query` | object | URL query parameters. List values are encoded as repeated parameters. |
| `headers` | object | Request headers. Authentication headers supplied by `auth` take precedence over the same user-supplied header name. |
| `json` | JSON value | JSON request body. The runner sets `Content-Type: application/json` unless supplied in `headers`. |
| `data` | object | Form body encoded as `application/x-www-form-urlencoded`; list values become repeated fields. |
| `multipart` | object | `multipart/form-data` fields and uploads. |
| `auth` | object | Optional environment-backed authentication configuration. |
| `timeout` | number | Per-attempt timeout passed to Python's HTTP client, in seconds. |
| `expected_status` | integer or list | Accepted status code or codes. The default accepts every `2xx` status. |
| `retries` | integer | Number of retry attempts after the initial attempt; defaults to `0`. |
| `retry_backoff` | number | Seconds multiplied by the one-based retry attempt before retrying; defaults to `0.0`. |
| `retry_on` | list | Status codes eligible for retry; defaults to `429`, `500`, `502`, `503`, and `504`. |
| `retry_unsafe` | boolean | Allow retries for `POST` and `PATCH`; omitted or false means those methods are never retried. |
| `outputs` | object | Declared `body`, `headers`, and/or `metadata` output paths. |

Use one body encoding at a time. When `multipart` is present it is used before
`json`, and `json` is used before `data`; this precedence is implementation
behavior, not a recommendation to combine them.

Output paths must be relative, non-empty paths that stay below the task
directory. They are written below `outputs/`; absolute paths and paths
containing `..` are rejected.

## POST: submit a JSON document

This unauthenticated POST sends a JSON object and treats both a creation and an
already-existing response as successful.

```python
submit = DagonTask(
    TaskType.WEB,
    "submit-observation",
    {
        "method": "POST",
        "url": "https://api.example.org/observations",
        "headers": {"Accept": "application/json"},
        "json": {
            "station": "napoli",
            "temperature_c": 22.4,
            "observed_at": "2026-06-24T12:00:00Z",
        },
        "expected_status": [200, 201],
        "outputs": {"body": "submission.json", "metadata": "submission-meta.json"},
    },
)
```

For an HTML-style form, replace `json` with `data`:

```python
"data": {"station": "napoli", "tag": ["coastal", "daily"]}
```

The resulting body uses `application/x-www-form-urlencoded`, with two `tag`
fields. Specify a `Content-Type` header explicitly only when the target API
requires a different form encoding.

## Upload a workflow artifact with multipart POST

A `workflow://` reference makes the producer a dependency of the web task.
DAGonStar copies the referenced file into the web task's `inputs/` directory
before making the request, then resolves the multipart `file` value to that
staged path.

```python
upload = DagonTask(
    TaskType.WEB,
    "upload-dataset",
    {
        "method": "POST",
        "url": "https://api.example.org/datasets",
        "multipart": {
            "dataset": {
                "file": "workflow:///prepare/output/data.csv",
                "content_type": "text/csv",
            },
            "description": {"value": "Daily observations"},
            "settings": {
                "value": {"validate": True},
                "content_type": "application/json",
            },
        },
        "expected_status": 201,
        "outputs": {"body": "dataset.json"},
    },
)
```

A multipart item with `file` uploads its file content. An item with `value`
creates a text field; non-string values are JSON-encoded. `content_type`
defaults to `application/octet-stream` for files and `text/plain` for values.

References may also appear recursively in request values. In ordinary strings,
the reference is replaced with the staged relative path. Use the special forms
below to place a staged file's content in a JSON or form value:

```python
"json": {"notes": {"text": "workflow:///prepare/output/notes.txt"}}
"json": {"configuration": {"json_file": "workflow:///prepare/output/config.json"}}
```

`text` reads a UTF-8 file; `json_file` reads and parses a UTF-8 JSON file.
References must identify a relative producer output path and may not contain
`..`.

## PUT, PATCH, DELETE, and HEAD

Every supported method uses the same task form. Set `expected_status`
deliberately, especially for endpoints whose successful response is `204 No
Content`.

```python
replace = DagonTask(
    TaskType.WEB,
    "replace-station",
    {
        "method": "PUT",
        "url": "https://api.example.org/stations/napoli",
        "json": {"name": "Napoli", "active": True},
        "expected_status": [200, 204],
        "outputs": {"metadata": "put-meta.json"},
    },
)

patch = DagonTask(
    TaskType.WEB,
    "patch-station",
    {
        "method": "PATCH",
        "url": "https://api.example.org/stations/napoli",
        "headers": {"Content-Type": "application/merge-patch+json"},
        "json": {"active": False},
        "expected_status": 200,
        "outputs": {"body": "patched-station.json"},
    },
)

delete = DagonTask(
    TaskType.WEB,
    "delete-draft",
    {
        "method": "DELETE",
        "url": "https://api.example.org/drafts/42",
        "expected_status": 204,
        "outputs": {"metadata": "delete-meta.json"},
    },
)

check = DagonTask(
    TaskType.WEB,
    "check-export",
    {
        "method": "HEAD",
        "url": "https://api.example.org/exports/latest.csv",
        "expected_status": 200,
        "outputs": {"headers": "export-headers.json"},
    },
)
```

`GET`, `HEAD`, `PUT`, and `DELETE` can retry when `retries` is positive;
`POST` and `PATCH` require `retry_unsafe: True`. Retrying a request can repeat
its side effects, so enable it only when the API is idempotent or supports an
idempotency key.

## Authentication without embedded secrets

Authentication is declarative, but secret values are read only from environment
variables at request time. The specification must never contain `token`,
`password`, `value`, or `secret` fields. The supported forms are:

| Type | Required fields | Request effect |
| --- | --- | --- |
| `bearer` | `token_env` | `Authorization: Bearer <environment value>` |
| `basic` | `username_env`, `password_env` | HTTP Basic `Authorization` header |
| `api_key_header` | `header`, `value_env` | Adds the named header with the environment value |
| `api_key_query` | `parameter`, `value_env` | Adds the named query parameter with the environment value |

For example, arrange for `CATALOG_TOKEN` to be present in the process
environment, then define a bearer-authenticated GET without exposing the token:

```python
catalog = DagonTask(
    TaskType.WEB,
    "private-catalog",
    {
        "method": "GET",
        "url": "https://api.example.org/catalog",
        "auth": {"type": "bearer", "token_env": "CATALOG_TOKEN"},
        "outputs": {"body": "catalog.json", "metadata": "catalog-meta.json"},
    },
)
```

These examples show the remaining authentication modes with different HTTP
methods:

```python
update = DagonTask(
    TaskType.WEB,
    "authenticated-patch",
    {
        "method": "PATCH",
        "url": "https://api.example.org/records/42",
        "json": {"reviewed": True},
        "auth": {
            "type": "api_key_header",
            "header": "X-API-Key",
            "value_env": "RECORDS_API_KEY",
        },
        "expected_status": 200,
    },
)

remove = DagonTask(
    TaskType.WEB,
    "authenticated-delete",
    {
        "method": "DELETE",
        "url": "https://api.example.org/records/42",
        "auth": {
            "type": "basic",
            "username_env": "RECORDS_USER",
            "password_env": "RECORDS_PASSWORD",
        },
        "expected_status": 204,
    },
)

health = DagonTask(
    TaskType.WEB,
    "keyed-health-check",
    {
        "method": "HEAD",
        "url": "https://api.example.org/health",
        "auth": {
            "type": "api_key_query",
            "parameter": "api_key",
            "value_env": "HEALTH_API_KEY",
        },
        "expected_status": 200,
    },
)
```

The metadata records the authentication type and environment-variable name(s),
not their values. This is helpful for auditing configuration without publishing
the credential. It is still your responsibility to avoid secrets in ordinary
headers, URL literals, request payloads, logs, and response outputs: response
bodies are persisted verbatim and are not redacted.

## Results, failures, and inspection

For a task named `upload`, DAGonStar creates these relevant scratch files:

| Path | Contents |
| --- | --- |
| `.dagon/web_request.json` | Resolved request specification used by the runner. |
| `.dagon/resolved_spec.json` | Copy of the resolved request specification. |
| `.dagon/web_stdout.txt` / `.dagon/web_stderr.txt` | Captured local-runner output. |
| `.dagon/web_result.json` | Metadata: original URL, method, status code, elapsed time, response content type, SHA-256 body hash, output paths, and non-secret auth description. |
| `outputs/<body path>` | Raw response bytes, when `outputs.body` is declared. |
| `outputs/<headers path>` | Response headers as JSON, when `outputs.headers` is declared. |
| `outputs/<metadata path>` | The same metadata object as JSON, when `outputs.metadata` is declared. |

An HTTP response outside `expected_status` is still written to declared outputs
and metadata before the task fails with `Unexpected HTTP status <code>`. A
transport error fails the task after any eligible retries. This preserves server
error bodies for diagnosis while correctly preventing dependent tasks from
running as though the request succeeded.

## Practical checklist

- Use `https://` for external services whenever available.
- Declare response outputs that downstream tasks genuinely consume; use
  `workflow:///web-task/outputs/<name>` from a dependent task to reference one.
- Set `expected_status` for API operations where only some successful codes make
  sense to your workflow.
- Use `timeout` and conservative retries for network-bound work. Do not retry
  unsafe mutations without idempotency guarantees.
- Keep credentials in runtime environment variables and inspect generated
  scratch artifacts before sharing them.
- Test workflows against a local or test endpoint before pointing a mutating
  method at production.
