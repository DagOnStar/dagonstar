# Agentic tools and guardrails

Tools give an agent optional capabilities; guardrails decide, outside the
agent, whether each action and candidate is allowed. Agent output and tool
results are treated as untrusted data and never as instructions.

## Tools

A tool is a registered `ToolSpec`:

| Field | Meaning |
|---|---|
| `id`, `version`, `description` | Identity; the version is part of checkpoint identity |
| `function` | `"module:function"` reference, called as `function(arguments, context)` |
| `arguments_schema`, `result_schema` | JSON Schema subset checked before and after the call |
| `side_effect` | `none`, `read`, or `scratch_write`; `external_write` is rejected at registration |
| `timeout_seconds`, `max_output_bytes` | Per-call bounds |
| `isolation` | `process` (default) or `inline`, which is allowed only for `side_effect="none"` |

Guardrails, evaluators, and adapters follow the same rule: process isolation
by default, inline only for `side_effect="none"` components (see
[isolation of registered code](agentic_configuration.md#isolation-of-registered-code)).

Process isolation runs `python -m dagon.agentic.worker` in a new session or
process group, exchanges JSON on standard input and output, and kills the whole
group on timeout or cancellation (`taskkill /T` on Windows). This bounds time
and output size; it does not confine file-system or network access, so a
registered tool is trusted code.

Built-in tools: `inspect_records` (count, duplicate ids, fields, null values)
and `repair_records` (remove duplicate ids, sort by id). Both read a declared
input by name (`{"input": "source"}`) and return a bounded result.

## Runtime action checks

Before any guardrail, DAGonStar refuses an action when:

| Code | Condition | Retryable |
|---|---|---|
| `undeclared_tool` | Tool is not in the effective tool set | no |
| `invalid_arguments` | Arguments are not an object or fail the schema | yes |
| `workflow_uri_injection` | Arguments contain a `workflow://` reference | no |
| `path_escape` | A path argument is absolute, contains `..`, a drive, a UNC prefix, a backslash, or NUL | no |

Candidates are refused when they are not JSON (`non_json_candidate`), exceed
4 MiB (`result_too_large`), contain `workflow://` references that the task did
not declare (`workflow_uri_injection`), or fail the output schema
(`output_schema`, retryable).

## Registered guardrails

A `GuardrailSpec` has a `stage` (`input`, `pre_action`, `post_action`, or
`result`), a function `function(subject, context) -> None | violation`, a
`repairable` flag, and an `isolation` (`process` by default, with a
`"module:function"` reference and a `max_output_bytes` bound; `inline` only
with `side_effect="none"`). A guard that times out fails closed and, when
process-isolated, is killed with its descendants. Repairable violations are returned to the agent as feedback;
others stop the run with `guardrail_blocked`. A guard that raises fails closed
with code `guard_error`.

Built-in guardrails:

- `preserve_record_ids` (result, repairable): the candidate keeps exactly the
  record ids present in the JSON inputs.
- `non_empty_result` (result, repairable).
- `read_only_tools` (pre_action): only `none` or `read` tools may run.

## What the evidence shows

`tests/test_agentic_guardrails.py` and Lesson 15 show that an undeclared action
is refused before it runs, the staged inputs remain, no result is published,
and the trace records the refusal. They do not show that a guard can recognise
semantically harmful content; guards check structure, declarations, paths,
and references.
