# LLM Tasks

`TaskType.LLM` invokes an OpenAI-compatible Chat Completions API as a workflow task. It is intended for JSON request construction, local workflow data inputs, and response capture; it does not require the OpenAI Python package.

## Provider configuration

Each provider has an INI section named `llm.<provider-name>`. Any number of these sections may be configured. `endpoint` is the provider base URL (or a full `/chat/completions` URL), `model` is the default model, and credentials come from either `api_key_env` or `api_key`. Prefer the environment form:

```ini
[llm.research]
endpoint=https://api.example.org
api_key_env=DAGON_RESEARCH_LLM_KEY
model=research-chat
```

Do not commit real API keys. The endpoint receives `POST /v1/chat/completions` unless its configured URL already ends in `/chat/completions`.

## Creating a task

The prompt is a JSON-compatible Chat Completions request. `params` supplies named values for `{placeholder}` strings anywhere in that JSON. The `model` in the request overrides the provider default.

```python
ask = DagonTask(
    TaskType.LLM,
    "summarize",
    {"messages": [{"role": "user", "content": "Summarize {subject}."}], "temperature": 0.2},
    provider="research",
    params={"subject": "the experiment"},
)
```

The prompt can instead be a JSON string, which is useful when a script assembles the request dynamically with `json.dumps`.

When a workflow is serialized, LLM tasks use `"type": "llm"` and retain the provider, parameters, input-file mapping, and output filename. Loading that JSON requires the named provider to be configured locally.

## Workflow input files

Use `input_files` to attach UTF-8 text produced by another task. Keys become prompt parameters, and values use the normal `workflow://` form:

```python
input_files={"report": "workflow:///prepare/output/report.txt"}
```

This creates the `prepare -> review` dependency. Before the request, the file is copied under `.dagon/inputs/<workflow>/<task>/...` in the LLM task directory and its UTF-8 content replaces `{report}`. Input paths must be relative to the producer task directory and cannot contain `..`. Binary files and remote-only producer files are not supported by this task type.

An explicit `workflow://` reference in any prompt string is also parsed, staged, and replaced by its UTF-8 content. Use `input_files` when a named placeholder makes the prompt easier to read.

The full response JSON is written to `response.json` in the LLM task working directory (or the relative `output_file` supplied to the task), so downstream tasks can consume it via `workflow://`.
