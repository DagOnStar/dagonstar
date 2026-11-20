# DAGonStar AgenticTask independent re-audit

Date: 2026-11-15  
Audited checkout: `/Users/raffaelemontella/PycharmProjects/dagonstar`  
Revision: `01968abd011c87f9a53170591f10df27d466fd44` (`development`)  
Overall verdict: **PASS**

Every mandatory acceptance requirement was assessed and passed. The full local suite, targeted Agentic and JSON adversarial tests, 46 credential-free examples, all 37 notebook code cells, CWL fixtures, clean-wheel checks, and the complete multi-platform CI run passed. The prior JSON reconstruction defect is corrected: explicit edges retain their identity and ordering through serialization, loading, repeated dependency discovery, and execution. Mock execution is credited only as contract evidence, never as proof of live infrastructure.

## Findings, ordered by severity

No unresolved material finding was identified.

### Historical finding H4 — Workflow JSON reconstruction silently dropped explicit dependencies

Status: **RESOLVED**.

References:

- `dagon/task.py:909-920` serializes explicit predecessor names separately from discovered predecessors.
- `dagon/__init__.py:385-419` restores explicit edges after all tasks exist, rejects unknown/self/cyclic edges, and preserves legacy same-workflow `prevs` documents.
- `dagon/__init__.py:860-914` invokes edge restoration through the actual workflow JSON loader.
- `tests/test_explicit_dependencies.py:96-220` covers stable round trips, execution order, discovered-edge separation, legacy JSON, invalid edges, and mixed task types.
- `tests/test_agentic_task.py:318-340` verifies an explicit Agentic edge through JSON reconstruction.

Reproduction:

```bash
python3 - <<'PY'
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config
w = Workflow('source', config=minimal_config())
a = DagonTask(TaskType.BATCH, 'a', 'true')
b = DagonTask(TaskType.BATCH, 'b', 'true')
w.add_task(a); w.add_task(b); b.add_dependency_to(a)
data = w.as_json()
r = Workflow('restored', config=minimal_config(), jsonload=data)
r.make_dependencies()
rb = next(t for t in r.tasks if t.name == 'b')
print(data['tasks']['b']['prevs'], [t.name for t in rb.prevs])
PY
```

Observed now: `serialized_prevs=['a']`, `serialized_explicit=['a']`, `restored_prevs=['a']`, and `restored_explicit=['a']`. The restored execution-order test also passed. Expected behavior is met. Recommended follow-up: retain the new round-trip, invalid-edge, legacy-document, mixed-type, and execution-order tests as release gates.

Classification: the former baseline defect is closed in the audited revision.

### Historical finding H1 — Timed-out policy components continued executing

Status: **RESOLVED**.

- `dagon/agentic/registry.py:30-41` requires importable process targets and permits inline execution only with `side_effect="none"`.
- `dagon/agentic/registry.py:63-112` defaults evaluators, guardrails, and adapters to process isolation.
- `dagon/agentic/sandbox.py:48-61` kills worker process groups; `dagon/agentic/sandbox.py:148-238` supervises adapter workers.
- `tests/test_agentic_containment.py:39-168` verifies timeout/cancellation cleanup and delayed descendant marker attempts.

Reproduction: `python3 -m unittest tests.test_agentic_containment -v`. Result: PASS; no delayed marker survived. Impact of the former defect was loss of a hard execution boundary. Recommended fix is complete; retain these tests as release gates.

### Historical finding H2 — Agentic profiles accepted persisted inline API keys

Status: **RESOLVED**.

- `dagon/agentic/config.py:204-213` rejects `api_key` and requires `api_key_env`.
- `dagon/agentic/config.py:220-235` resolves the environment value only at invocation.
- `tests/test_agentic_config.py:119-165` verifies refusal without secret echo and sample-config hygiene.

Reproduction: `python3 -m unittest tests.test_agentic_config -v`. Result: PASS. Recommended fix is complete; preserve the legacy LLMTask compatibility boundary without weakening Agentic profiles.

### Historical finding H3 — Synthetic task-type mutation lacked an automated test

Status: **RESOLVED**. `tests/test_tutorial_coverage.py:43-55` injects a newly registered synthetic type and requires validation to fail. Reproduction: `python3 -m unittest tests.test_tutorial_coverage -v`. Result: PASS.

## Acceptance-requirement ledger

| ID | Status | Evidence and rationale |
|---|---|---|
| A01 | PASS | `TaskType.AGENTIC`, factory, typed task contract, public import, wheel import, and console runner executed. |
| A02 | PASS | Specification validation rejected missing, empty, duplicate, unknown, non-finite, and unsafe values. |
| A03 | PASS | Named agent/provider/LLM resolution passed; inline keys were rejected; environment values were invocation-time and redacted. |
| A04 | PASS | No implicit tools; empty profiles/lists stayed tool-free; deterministic two-attempt revision passed. |
| A05 | PASS | Tasks narrowed but could not widen profile tools/budgets; guard union and pre-action blocking passed. |
| A06 | PASS | Step, token, tool, attempt, and deadline bounds passed; timed-out/cancelled process trees left no delayed effects. |
| A07 | PASS | Independent Decimal result was `5/6 = 0.833333…`; threshold .8 accepted, .9 rejected, equality inclusive; mandatory/hard/error/spoof cases passed. |
| A08 | PASS | Reports were machine-readable; publication was commit-last. Failure, rejection, cancellation, crash, validation failure, and tampering neither published acceptance nor released dependants. |
| A09 | PASS | Recursive `workflow://` traversal, nested/repeated/cross-workflow references, binary descriptors, local hashes/bytes, mixed graphs, reference counts, path escape, and symlink refusal passed. |
| A10 | PASS | Actual JSON reconstruction now preserves explicit-edge identity and order; invalid/legacy/mixed-type cases, deterministic CWL execution, FAIR, and portable emulation passed. |
| A11 | PASS | Contract/profile/version/input/output/report/commit mutations invalidated reuse; only reverified accepted runs reused checkpoints. |
| A12 | PASS | Dynamic inventory found 14 registered task types; every type has lessons, runnable evidence, and tests. |
| A13 | PASS | Inventory found 40 required features and 54 entries, zero unmatched; deletion, path, notebook, and synthetic-type negative mutations passed. |
| A14 | PASS | Tutorial checks, 33 lessons, 46 examples, notebook JSON, and all 37 executable cells passed. |
| A15 | PASS | sdist/wheel, strict Twine, dependency boundaries, outside-checkout install, runner, and installed mock task passed. |
| A16 | PASS | GitHub run `43740574115` for the audited revision passed all 16 required jobs: Ubuntu, macOS, Windows, Rocky Linux 9, Debian arm64, quality, Agentic/CWL, notebook, Slurm/BeeOND, and distribution build. Release/PyPI jobs were correctly skipped for the non-release push. |

## Task-type-to-lesson coverage matrix

| TaskType | Lesson(s) | Evidence | Assessment |
|---|---:|---|---|
| CHECKPOINT | 07 | local-executed | PASS |
| BATCH | 01, 02, 03 | local-executed | PASS |
| SLURM | 23 | mock plus CI Slurm | PASS; emulated site |
| CLOUD | 22 | mock-contract | PASS; no provisioning claim |
| DOCKER | 17 | mock-contract | PASS; no daemon claim |
| KUBERNETES | 19 | mock-contract | PASS; no cluster claim |
| APPTAINER | 18 | mock-contract | PASS; no runtime/image claim |
| NOMAD | 20 | mock-contract | PASS; no live agent claim |
| LLM | 11 | loopback mock | PASS; no model-quality claim |
| NATIVE | 09 | local-executed | PASS |
| WEB | 10 | loopback mock | PASS |
| FAAS | 12 | mock/loopback | PASS; live cloud adapters unverified |
| IOT | 13 | mock-contract | PASS; physical actuation unverified |
| AGENTIC | 14, 15, 16 | deterministic mock/loopback | PASS |

The complete 14×14 producer/consumer metadata matrix passed. It proves dependency and serialization contracts, not live transfer through every backend.

## Feature-to-lesson coverage matrix

| Feature | Lesson(s) | Evidence | Assessment/boundary |
|---|---:|---|---|
| graph.explicit-dependencies | 02 | local | PASS; ordering only |
| graph.workflow-references | 03 | local | PASS |
| graph.cycle-validation | 04 | local | PASS |
| execution.scratch-and-launchers | 05 | local | PASS; Windows needs POSIX bash |
| staging.copy-link | 06 | local | PASS; LINK assumes shared FS |
| execution.checkpoint-resume | 07 | local | PASS |
| execution.async-lifecycle | 08 | local | PASS |
| execution.dry-run | 14, 25 | local | PASS |
| execution.portable-emulation | 24, 32 | emulation | PASS; not backend proof |
| config.dagon-ini | 00, 14 | local | PASS |
| workflow.json-roundtrip | 31 | local | PASS; task contracts and explicit edges reconstruct, including legacy and mixed-type fixtures |
| agentic.profiles | 14 | local | PASS |
| agentic.tools | 15 | local | PASS; process isolation is not an OS sandbox |
| agentic.guardrails | 15 | local | PASS; process-default |
| agentic.evaluation | 16 | local | PASS; independent/process-default |
| agentic.publication | 16 | local | PASS; commit last |
| agentic.checkpoint-identity | 16 | local | PASS |
| agentic.mixed-dataflow | 30, 32 | local | PASS; remote-only limit explicit |
| agentic.openai-compatible-adapter | 14 | mock | PASS for protocol; no paid provider |
| agentic.cwl-runner | 29 | local | PASS with cwltool |
| faas.http-provider | 12 | mock | PASS; live TLS/auth unverified |
| faas.cloud-adapters | 12 | live-optional | PASS for contract; live invocation N/A |
| iot.actuation-safety | 13 | mock | PASS; physical interlocks external |
| iot.compute-placement | 30 | mock | PASS; recorded, not deployed |
| remote.ssh-ports-and-quoting | 21 | mock | PASS; no live SSH |
| slurm.beeond | 24 | emulation/CI | PASS; emulated site |
| slurm.scheduler-prestaging | 25 | mock/CI | PASS |
| movers.scp | 26 | mock | PASS; live transfer unverified |
| movers.gridftp-globus | 26 | live-optional | PASS for contract; live endpoints N/A |
| movers.skycds | 26 | live-optional | PASS for contract; live service N/A |
| movers.dynostore | 26 | live-optional | PASS for contract; live server N/A |
| movers.stager-modes | 25, 26 | mock | PASS; limits documented |
| fair.metadata-export | 27 | local | PASS; local export is not publication |
| fair.agentic-artifacts | 16, 27 | local | PASS; accepted outputs only |
| meta.dag-tps | 28 | local | PASS; cross-service recovery excluded |
| meta.dagon-service-api | 28, 31 | mock | PASS; service mocked |
| cwl.export | 29 | local | PASS; backend staging outside graph |
| operations.runtime-environment | 31 | local | PASS |
| operations.packaging-extras | 00, 31 | local | PASS; optional SDKs excluded |
| operations.continuous-integration | 31 | remote CI | PASS |

Four honest exclusions are not counted as supported: experimental `peer2peer.node`, live-construction `ftp_publisher.ftp_api`, partially tested `api.workflow_server`, and enumerated-but-unimplemented HTTP/FTP/SFTP movers.

## Commands executed and results

| Command/check | Result |
|---|---|
| Read `AGENTS.md`, audit plan, and implementation plan in full | PASS |
| `python3 -m unittest discover -s tests -v` | PASS: 383 tests in 319.144 s |
| Focused JSON/dependency/Agentic/workflow/all-type suite | PASS: 59 tests in 44.534 s |
| `python3 -m py_compile ...`; `python3 -m compileall -q dagon` | PASS |
| Exact CI ruff command | PASS |
| Exact CI mypy command | PASS: 22 files; local modern-mypy Python-3.8-config warning only |
| Tutorial and coverage validators | PASS: 33 lessons; 14 types; 40 required features; 54 entries; zero unmatched |
| Independent Decimal recomputation | PASS: `5/6 = 0.833333…` |
| Containment adversarial tests | PASS: no late evaluator/guard/adapter/descendant markers |
| Validation/publication adversarial tests | PASS: no accepted publication, dependant release, or reusable success on failure |
| `python3 tools/run_local_examples.py` | PASS: 46/46 |
| Notebook JSON and `tools/run_notebook_smoke.py` | PASS: 37 cells in 211.5 s |
| Agentic CWL fixtures and cwltool | PASS: producer→agent→consumer accepted |
| `python3 -m build`; strict Twine check | PASS: sdist and wheel |
| Clean venv/wheel outside checkout; worker import; runner; `tool_free.py` | PASS |
| Independent explicit-edge JSON round trip | PASS: serialized and restored predecessor/explicit lists all equal `['a']` |
| GitHub Actions run `43740574115` | PASS: all 16 required jobs; release and PyPI publication correctly skipped |

## Environment and audited revision

- macOS 26.6.2 arm64; CPython 3.12.10 at `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`.
- Revision `01968abd011c87f9a53170591f10df27d466fd44`, commit time 2026-11-15T11:20:39-06:00.
- Build 1.5.0, Twine 7.0.0, and cwltool were exercised.
- CI evidence: <https://github.com/DagOnStar/dagonstar/actions/runs/43740574115>.
- No paid provider, live model, deployment, publication, infrastructure provisioning, or external write was invoked. Loopback servers used `127.0.0.1`.
- No tracked implementation file was modified; this report alone was updated.

## Baseline defects, regressions, blocked checks, and evidence limits

Baseline defects: none newly demonstrated. Historical H4 was a baseline JSON-loader defect and is corrected in this revision.

Introduced regressions: none observed. Historical findings H1–H4 are closed with executable regression evidence.

Blocked mandatory checks: none. Live optional services were intentionally not invoked under the credential-free/no-provisioning constraint and are **NOT APPLICABLE to the mandatory path**, not passed as live integrations.

Evidence limitations:

- Mock/loopback evidence proves framework contracts, not provider availability, latency, quality, billing, deployment TLS/auth, or quotas.
- Slurm/BeeOND used real single-node Slurm with an emulated site, not a production multi-node cluster.
- Docker, Kubernetes, Apptainer, Nomad, SSH, cloud, Globus/GridFTP, SKYCDS, DynoStore, physical IoT, and paid LLM integrations were not exercised live.
- Local FAIR artifacts are not repository publication or remote validation.

## Conclusion

The audited revision satisfies every mandatory A01–A16 requirement. Agentic acceptance, failure gating, atomic publication, checkpoint integrity, bounded process containment, environment-only credentials, JSON reconstruction, CWL, FAIR, documentation coverage, packaging, platform CI, and release gates all have passing evidence. The overall verdict is **PASS**.
