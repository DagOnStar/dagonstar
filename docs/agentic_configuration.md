# Agentic task configuration

Agent and LLM providers are configured only in `dagon.ini`. A task names a
profile with `agent="<name>"`; the profile resolves in three steps:

```
[agent.<profile>]  ->  [agent_provider.<provider>]  ->  [llm.<llm_provider>]   (adapters that need an LLM)
```

`dagon.ini.sample` contains working examples: `quality-local` (mock adapter, no
key) and `quality-live` (OpenAI-compatible adapter that reads its key from an
environment variable). Configuration is read with the normal
`dagon.config.read_config` or passed as a dictionary; the runner CLI reads its
`--config` file with interpolation disabled.

## `[agent.<profile>]`

| Key | Required | Meaning |
|---|---|---|
| `provider` | yes | Name of an `[agent_provider.<name>]` section |
| `llm_provider` | for `builtin` | Name of an `[llm.<name>]` section |
| `strategy` | no | `bounded_iterative` (the only strategy) |
| `tools` | no | Comma-separated registered tool ids the profile permits |
| `guardrails` | no | Comma-separated registered guardrail ids always applied |
| `max_steps` | yes | Maximum adapter calls |
| `timeout_seconds` | yes | Wall-clock bound for the whole run |
| `max_attempts` | no | Maximum submitted candidates (default: `max_steps`) |
| `max_tool_calls` | no | Default 8 |
| `max_tokens` | no | Default 4096 |
| `max_tool_output_bytes` | no | Default 65536 |
| `max_trace_bytes` | no | Default 262144 |
| `temperature` | no | Finite, non-negative; passed to the builtin adapter |
| `description` | no | Free text |

Unknown keys are rejected. Budgets must be finite and positive.

## `[agent_provider.<name>]`

| Key | Meaning |
|---|---|
| `implementation` | A registered adapter: `mock` or `builtin` (OpenAI-compatible Chat Completions) |
| `scenario` | `mock` only: `cooperative` (default), `undeclared_tool`, `path_escape`, `workflow_uri`, `malformed`, `self_reported_score`, `drop_records`, `slow` |
| `description` | Free text |

The mock scenarios are deterministic adversarial fixtures used by the tests and
Lesson 15.

## `[llm.<name>]`

| Key | Meaning |
|---|---|
| `endpoint` | `http(s)` base URL; `/v1/chat/completions` is appended unless already present |
| `model` | Model name sent in the request |
| `api_key_env` | Required: name of the environment variable that holds the key |

An inline `api_key` is refused with `AgenticConfigurationError` when an agent
profile selects the section (the error does not repeat the value). LLM tasks
still accept `api_key` for compatibility, so keep any section that uses it out of
agent profiles and out of committed files.

The key is read from the environment only when the agent is invoked: the
supervisor checks that it is present and records it for redaction, and the
adapter's worker process reads the variable itself, so the key is never sent
over the worker pipe. It is sent to the endpoint as a bearer token,
redacted from every error message, and never written to the report, trace,
checkpoint, JSON export, FAIR metadata, or CWL file. The configuration digest
covers the endpoint and the *name* of the environment variable, not the key.

## Authority: profile versus task

The profile is the maximum authority:

- task `tools` must be a subset of the profile's tools (`tools=[]` disables
  them; omitting `tools` inherits the profile's);
- task `budgets` must not exceed the profile's;
- task `guardrails` are added to the profile's, never removed.

Violations raise `AgenticConfigurationError` before execution.

## Examples

Deterministic local profile:

```ini
[agent_provider.fixture]
implementation = mock

[agent.quality-local]
provider = fixture
tools = inspect_records, repair_records
guardrails = preserve_record_ids
max_steps = 8
timeout_seconds = 60
```

Live OpenAI-compatible profile (optional; not exercised by tests or CI):

```ini
[llm.local-model]
endpoint = http://127.0.0.1:8080
model = fixture-model
api_key_env = DAGON_LLM_LOCAL_API_KEY

[agent_provider.builtin]
implementation = builtin

[agent.quality-live]
provider = builtin
llm_provider = local-model
tools = inspect_records, repair_records
guardrails = preserve_record_ids
max_steps = 8
timeout_seconds = 60
```

```bash
export DAGON_LLM_LOCAL_API_KEY=...   # never commit this value
```

The tests exercise the builtin adapter only against a loopback server
(`tests/test_agentic_provider.py`).

## Registering extensions

```python
from dagon.agentic import ToolSpec, register_tool

register_tool(ToolSpec(
    id="station_summary", version="1.0.0", description="Summarise stations.",
    function="mypackage.tools:station_summary",          # importable by the worker process
    arguments_schema={"type": "object", "required": ["input"],
                      "properties": {"input": {"type": "string"}}, "additionalProperties": False},
    side_effect="read", timeout_seconds=10.0))
```

`register_evaluator`, `register_guardrail`, and `register_adapter` work the same
way. Re-registering an existing id requires `replace=True`, and registered
versions are part of the checkpoint identity.

### Isolation of registered code

Every registered component runs in a supervised worker process by default
(`isolation="process"`) and must then be an importable `"module:function"`
reference. An adapter's worker lives for the whole run and is built by calling
its factory with JSON options (`scenario` for the mock adapter, `endpoint`,
`model`, `temperature`, and `api_key_env` for the builtin adapter, and the
profile's public fields as `profile` for custom adapters). On a deadline,
cancellation, or protocol error the worker's whole process group is killed
(`taskkill /T` on Windows), so neither the component nor a process it started
can act after the task has failed or been cancelled. The adapter's worker is
started inside the run, so its start-up time counts against `timeout_seconds`;
on a slow (for example NFS-mounted) installation, allow for it. A run whose
deadline expires during start-up ends with `timeout_seconds_exhausted` and a
report whose `execution.determinism` is `adapter_not_started`.

`isolation="inline"` runs a component in a thread of the supervising process.
A thread cannot be stopped at its deadline, so registration refuses inline
execution unless the component is declared `side_effect="none"`. That
declaration is a statement by trusted registration code, not containment: an
inline component that does have side effects can still act after a timeout.
The built-in evaluators and guardrails that compute only over in-memory JSON
are registered inline; `reference_match`, which reads a file, and both built-in
adapters run in worker processes.

```python
from dagon.agentic import EvaluatorSpec, register_evaluator

register_evaluator(EvaluatorSpec(
    "station_count", "1.0.0", "Count stations.", "mypackage.evaluators:station_count",
    timeout_seconds=10.0))                       # process isolation (default)
```
