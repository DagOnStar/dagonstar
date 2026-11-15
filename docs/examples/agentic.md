# Agentic task examples

Source: [`examples/agentic/`](../../examples/agentic/README.md).

## Purpose

The examples teach `TaskType.AGENTIC` on a synthetic observation table with a
duplicated record. A quality-control agent must return a complete,
duplicate-free table; downstream tasks run only when independent evaluators
accept the result.

## Mechanisms exercised

- Profile resolution from a temporary `dagon.ini` (`[agent.*]`,
  `[agent_provider.*]`), task-level narrowing of tools and budgets.
- A bounded, tool-free revision loop, and a tool-assisted repair with the
  built-in `inspect_records` and `repair_records` tools.
- Runtime action checks and the `preserve_record_ids` guardrail; an adversarial
  mock that proposes an undeclared tool.
- Weighted result fit, a failing mandatory gate, and no release of the consumer.
- Checkpoint reuse that requires the same contract, profile, versions, and input
  content.
- Mixed graphs with BATCH, NATIVE, IOT, and a second agent; CWL export with an
  executable `dagon-agent-runner` step.

## Prerequisites and execution

`python -m pip install -e .` from the repository root. No credentials,
services, or network. `cwl_local.py` executes the exported graph only when
`cwltool` and `dagon-agent-runner` are on `PATH`; otherwise it reports that the
execution was skipped.

## Verification

Every script asserts exact outputs, fits, or failures and exits non-zero on a
mismatch; see the table in the [examples README](../../examples/agentic/README.md).
The focused tests are `python -m unittest tests.test_agentic_task
tests.test_agentic_guardrails tests.test_agentic_evaluation
tests.test_agentic_checkpoint tests.test_agentic_cwl -v`.

## Limitations

The mock adapter is deterministic and is not a model. Live providers are
optional and unverified by these examples.
