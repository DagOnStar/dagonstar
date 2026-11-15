# Agentic task examples

Self-contained examples of `TaskType.AGENTIC`. Each script writes a temporary
`dagon.ini` (see [`agentic_common.py`](agentic_common.py)) that is read with the
normal `dagon.config.read_config`. The `quality-local` profile uses the
deterministic `mock` agent provider, so no model endpoint, key, or network
access is needed. Run them from the repository root:

```bash
python examples/agentic/tool_free.py
python examples/agentic/guarded_repair.py
python examples/agentic/evaluation_failure.py
python examples/agentic/checkpoint_identity.py
python examples/agentic/mixed_workflow.py
python examples/agentic/cwl_local.py
```

| Script | What it shows | Exact check |
|---|---|---|
| `tool_free.py` | Tool-free bounded revision after independent feedback | fits `[0.8, 1.0]`, zero tool calls, ids `[1, 2, 3, 4]` |
| `guarded_repair.py` | Tool-assisted repair, then an adversarial profile proposing an undeclared tool | tools `inspect_records`, `repair_records`; then `guardrail_blocked`, no result, inputs intact |
| `evaluation_failure.py` | A mandatory gate that no revision can satisfy | F = 2/3, `mandatory_failures == ["stations"]`, consumer never executes |
| `checkpoint_identity.py` | Verified checkpoint reuse | reused once; contract change and upstream content change both re-run |
| `mixed_workflow.py` | BATCH → AGENTIC → AGENTIC → NATIVE and IOT | every task finishes, NATIVE counts 4 records |
| `cwl_local.py` | Deterministic CWL v1.2 export with a `dagon-agent-runner` step | identical exports, `dagon_config` input; executed with `cwltool --no-container` when installed |

The negative examples (`evaluation_failure.py` and the second half of
`guarded_repair.py`) log the expected task failure and exit 0 only after
verifying it. All scripts are run by `python tools/run_local_examples.py`.

## Optional live provider

A live OpenAI-compatible model is never needed for these examples, the tests,
or CI. To try one, add a profile like `quality-live` from `dagon.ini.sample` to
a private, ignored `dagon.ini`, export the key in the variable named by
`api_key_env`, and select the profile with `agent="quality-live"`. A live run is
nondeterministic: the fits and attempt counts asserted above need not hold, and
the evaluation report records `nondeterministic_live_model`. Never commit the
key, and do not send private data to a provider without approved governance.

See [agentic tasks](../../docs/agentic_tasks.md),
[configuration](../../docs/agentic_configuration.md),
[guardrails](../../docs/agentic_guardrails.md),
[evaluation](../../docs/agentic_evaluation.md), and tutorial Lessons 14–16.
