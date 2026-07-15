# LLM Tasks

`TaskType.LLM` makes a large-language-model request a node in a DAGonStar
workflow. It sends a JSON request to an OpenAI-compatible **Chat Completions**
HTTP endpoint, can incorporate text produced by upstream tasks, and saves the
provider's JSON response for later workflow tasks. It uses Python's standard
library; installing the OpenAI Python package is neither required nor used.

This task type is best suited to a request/reply step whose inputs and output
belong in the workflow graph. It is not an agent runtime, a streaming client,
an upload mechanism, or a provider abstraction beyond the compatible HTTP
request described below.

## What happens when an LLM task runs

For a normal (non-dry) run, DAGonStar performs these operations in order:

1. Creates the task working directory and records a checkpoint entry.
2. Finds every declared or inline `workflow://` input, adds the corresponding
   task dependency, and waits for the producer through the ordinary workflow
   scheduler.
3. Copies each referenced producer file into the LLM task's `.dagon/inputs/`
   directory, reads it as UTF-8 text, and substitutes it into the request.
4. Renders named prompt placeholders, supplies a default model if needed, and
   posts the resulting JSON to the configured endpoint.
5. Writes the complete JSON response to the requested output file, which is
   `response.json` by default.

The saved response is deliberately the raw provider response, not only the
assistant message. A downstream task can therefore select the fields that its
provider actually returns.

## Quick start: run the local demonstration

The repository includes a complete, deterministic example. It starts a local
mock server, produces a report, sends it through an LLM task, and prints the
saved response. It makes no network request outside the machine and requires
no credentials.

```bash
python3 examples/llm/local_mock_llm.py
```

For a narrated version, see [Lesson 11: Execute an LLM task responsibly](tutorial/lesson_11_execute_an_llm_task_responsibly.md).

## Configure a provider

Provider settings live in an INI section named `[llm.<provider-name>]`. The
`provider` argument on the task selects the suffix after `llm.`. You may define
multiple sections and select a different one per task.

```ini
[llm.research]
endpoint=https://api.example.org
api_key_env=DAGON_RESEARCH_LLM_KEY
model=research-chat
```

Set the secret only in the execution environment (or another secret-management
mechanism) before running the workflow:

```bash
export DAGON_RESEARCH_LLM_KEY='...'
```

| Setting | Required | Meaning |
| --- | --- | --- |
| `endpoint` | Yes | Provider base URL, or a complete URL ending in `/chat/completions`. |
| `api_key_env` | One of this or `api_key` | Name of the environment variable containing the bearer token. When set, its value takes precedence. |
| `api_key` | One of this or `api_key_env` | Literal bearer token. Use only in a private, ignored local configuration file. |
| `model` | No | Default model. A request-level `model` overrides it. |

Never commit an API key, token, or private configuration. `dagon.ini.sample`
should contain only safe placeholders. If `endpoint` does not already end in
`/chat/completions`, DAGonStar appends `/v1/chat/completions`; for example,
`https://api.example.org` becomes
`https://api.example.org/v1/chat/completions`. The request is an HTTP `POST`
with `Content-Type: application/json` and `Authorization: Bearer <key>`.

The service must accept that endpoint shape and return a JSON document. The
task does not translate between provider-specific APIs, negotiate API versions,
or retry failed requests.

## Create a task

Construct LLM tasks through the standard `DagonTask` factory:

```python
from dagon.task import DagonTask, TaskType

ask = DagonTask(
    TaskType.LLM,
    "summarize",
    {
        "messages": [
            {"role": "system", "content": "Be concise and factual."},
            {"role": "user", "content": "Summarize {subject}."},
        ],
        "temperature": 0.2,
    },
    provider="research",
    params={"subject": "the experiment"},
)
```

The effective constructor is:

```python
DagonTask(
    TaskType.LLM, name, prompt, provider,
    params=None, input_files=None, working_dir=None,
    output_file="response.json", timeout=120,
)
```

`name` identifies the DAG node. `prompt` must be a JSON object or a JSON string
which decodes to an object. It must include a `messages` member before the
request is sent. Other JSON properties, such as `temperature`, are passed on
unchanged. If the object has no `model`, the provider configuration must have a
non-empty `model`; if it does have a `model`, that request value wins.

`timeout` is passed to the underlying HTTP request in seconds. `output_file`
must be a non-empty relative path inside the task directory; absolute paths and
paths containing `..` are rejected. For example, `outputs/review.json` is a
valid output location.

### Prompt parameters

Every string value in the request object is rendered using Python's
`str.format_map`. Use `{name}` for values supplied through `params`:

```python
prompt = {
    "messages": [{"role": "user", "content": "Classify: {text}"}],
    "metadata": {"run_label": "{label}"},
}
params = {"text": "A short observation", "label": "trial-17"}
```

All placeholders must be supplied. A missing name raises `ValueError` before
the HTTP request. Because this is Python format syntax, literal braces must be
escaped as `{{` and `}}`; this matters for prompts containing JSON examples.
Values are rendered as text by `str.format_map`, so use prompt JSON for
structured request fields and use parameters for textual interpolation. Prompt
object keys are not rendered.

## Use data from upstream tasks

`input_files` connects an LLM task to local UTF-8 text written by another task.
Its keys become prompt parameters and its values are `workflow://` references.

```python
summarize = DagonTask(
    TaskType.LLM,
    "review_report",
    {"messages": [{"role": "user", "content": "Review this report:\n{report}"}]},
    provider="research",
    input_files={"report": "workflow:///prepare_report/output/report.txt"},
)
```

In this example, the reference means:

| Part | Value | Meaning |
| --- | --- | --- |
| Scheme | `workflow://` | A file owned by a workflow task. |
| Workflow name | empty | The current workflow. |
| Producer task | `prepare_report` | The task that creates the file. |
| Relative path | `output/report.txt` | Path under that producer's working directory. |

The reference adds the `prepare_report -> review_report` dependency. At
execution time, its file is copied to a location such as:

```text
<review_report working directory>/.dagon/inputs/<workflow>/prepare_report/output/report.txt
```

The copied file is then read as UTF-8 and its text replaces `{report}`. The
copy makes the task input inspectable and avoids reading directly from a path
outside the task's staged input area.

You can name another workflow explicitly when it is available as a transversal
workflow:

```text
workflow://UpstreamWorkflow/prepare_report/output/report.txt
```

The producer and file must exist when the task executes. Referenced paths are
always relative to the producer task directory: absolute paths and `..` path
segments are rejected. Files must be UTF-8 decodable. Binary files, arbitrary
host files, remote-only outputs, and automatic document extraction are not
supported by this task type.

### Inline references

Instead of `input_files`, a prompt string may contain a `workflow://` reference
directly:

```python
{"messages": [{"role": "user", "content": "Read workflow:///prepare_report/output/report.txt"}]}
```

DAGonStar detects the reference, establishes the same dependency, stages the
file, and replaces the reference itself with its text. `input_files` is usually
clearer because it gives the inserted data a meaningful name; inline references
are useful for a one-off insertion. Keep references free of whitespace and
quote/closing punctuation characters, because they are recognized as a compact
URI-like token.

## Consume the response downstream

By default the LLM task writes `<task working directory>/response.json`. A
subsequent task can reference it like any other workflow-produced file:

```python
publish = DagonTask(
    TaskType.BATCH,
    "publish",
    "python3 publish.py workflow:///review_report/response.json",
)
```

For LLM-to-LLM flow, use `input_files` with that same reference. The next task
receives the response JSON as UTF-8 text; it does not automatically extract
`choices[0].message.content`. Add an explicit local processing task when you
need a stable, provider-independent text artifact.

## Workflow JSON and dry runs

When serialized, an LLM task has `"type": "llm"`. Its prompt is retained as
the task command, and `provider`, `params`, `input_files`, and `output_file`
are retained as LLM-specific fields. Reloading the workflow still requires the
matching `[llm.<provider>]` configuration on the machine where it runs; secrets
are not embedded by the task serializer.

In a dry run, DAGonStar prepares the task and input staging but does not send
the HTTP request or write a response file. Downstream steps that require
`response.json` therefore need a normal run (or a deliberately supplied test
artifact).

## Failure modes and diagnosis

| Symptom | Likely cause and action |
| --- | --- |
| `provider ... is not configured` | Add the matching `[llm.<provider>]` section to the runtime configuration. |
| `requires api_key or api_key_env` | Export the named environment variable, or use a private local `api_key`. |
| `prompt needs model` | Set `model` in the prompt or in the provider section. |
| `prompt must contain a messages array` | Supply a Chat Completions request with `messages`. |
| `Prompt parameter ... was not provided` | Add the missing `params` value or an `input_files` mapping with that name. |
| `input producer was not found` or `input file does not exist` | Check the workflow/task name, relative path, and that the producer writes the expected file. |
| `input files must be UTF-8 text` | Convert or preprocess the source into UTF-8 text in an upstream task. |
| `LLM provider returned HTTP ...` | Inspect the returned provider body in the error; validate endpoint, model, credentials, and request fields. |
| `Unable to contact LLM provider` | Check DNS/network reachability, the endpoint URL, and the configured timeout. |

Provider errors and connection failures are raised as `RuntimeError`; malformed
configuration, prompts, references, and inputs are raised as `ValueError` (or
`FileNotFoundError` for a missing producer file). Keep prompts and input files
free of credentials: the request body is sent to the configured external
provider, and the complete response is saved in the task working directory.

## Practical design guidance

- Start with the included local mock example before using a real provider.
- Make upstream tasks produce small, explicit UTF-8 text artifacts. Large
  files consume request context and may exceed provider limits; DAGonStar does
  not count, truncate, or chunk tokens.
- Treat prompt templates and response files as workflow data. Version the
  templates, avoid secrets, and validate provider JSON with a local downstream
  step when it affects scientific or operational decisions.
- Use a private ignored configuration or environment variables for credentials,
  never workflow JSON, examples, or `dagon.ini.sample`.
