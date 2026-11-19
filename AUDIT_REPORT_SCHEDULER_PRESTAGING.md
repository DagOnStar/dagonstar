# Independent audit: scheduler-aware pre-staging (sixth repeat audit)

## 1. Executive verdict

**Verdict: PASS. The post-audit correctness and performance changes introduce no open finding.**

This audit covers the substantial changes made after the prior PASS:

- D-001: a Slurm job cancelled while pending could be falsely treated as completed;
- D-002: creating the completion record only on the compute node could remain invisible through NFS negative caching;
- P-001: stage-in repeatedly read content-verified inputs;
- P-002: content listing launched one `cksum` process per file;
- P-003: the core-hour estimate ignored allocated time spent rechecking staged content;
- package version 2.9.4 and the accompanying deep-validation tooling and documentation.

All five changes are implemented conservatively and regression-covered. The completion record is created empty during stage-in, overwritten by an early compute-launcher `EXIT` trap, tied to the submitted job ID, and required to contain status zero before completion is accepted. Policy version 4 invalidates older checkpoints whose completion or listing guarantees differ. Content listings are generated once per side during stage-in, use batched `cksum` with deterministic C-locale ordering, and are independently recomputed for checkpoint and compute-start validation. The measured compute recheck is subtracted from the documented upper-bound resource estimate.

Independent verification passed:

- 92 focused scheduler/pre-staging tests;
- all 260 unit tests;
- all 18 self-contained local examples;
- compilation, tutorial validation, CI-targeted ruff, and focused mypy;
- exact-code CI run [43598110185](https://github.com/DagOnStar/dagonstar/actions/runs/43598110185) on `274515c`: all 14 build/test jobs passed;
- Windows/Python 3.10: 260 tests passed with 32 expected skips;
- emulated Slurm: 92 focused tests and 47/47 harness checks passed, including real pending cancellation;
- the Slurm example printed `Verification: ok`.

Current commit `6a57411d257c45e44625e71409c2f6e20875d905` changes only `IMPLEMENTATION_REPORT.md` to record the green performance-follow-up CI run. Its own CI run 43600397537 was still executing at cutoff, with eight jobs already green and no failure. This is non-blocking: the executable tree is identical to fully green `274515c`, and the documentation-only delta was independently checked.

## 2. Scope and repository state

- Audited branch and HEAD: `development` at `6a57411d257c45e44625e71409c2f6e20875d905`
- `origin/development`: same commit
- Remote feature branch: deleted; local stale tracking ref was confirmed prunable
- Original feature baseline: `d8da197badd71a426e7cd7cf70ba88b8cc1270a9`
- Effective diff from the original baseline: 40 files, 5,785 insertions, 113 deletions
- Runtime: Darwin 25.6.0 arm64; Python 3.12.10
- Working tree: tracked files clean; this audit report is the only untracked file
- Package version: 2.9.4 in `setup.cfg`; no release tag was created

New commits audited since the previous PASS:

| Commit | Purpose | Result |
|---|---|---|
| `534f0e5` | Completion record, cancellation handling, NFS-safe precreation, policy v3 | PASS |
| `70ef6bb` | Set version 2.9.4 | PASS |
| `ab4cf0d`, `d814ef7` | Report deep validation and its green CI | PASS |
| `c337e17` | Single-pass/batched content checks, measured recheck, policy v4 | PASS |
| `b12b43d` | Report performance follow-up | PASS |
| `274515c` | Python 3.8/3.9-compatible test file writing | PASS |
| `6a57411` | Record green performance-follow-up CI | PASS |

Only this audit report was modified by the auditor.

## 3. Acceptance gates

| Gate | Result | Evidence |
|---|---|---|
| A — API/compatibility | PASS | Opt-in defaults, overrides, positional API, JSON, RemoteSlurm MRO, CWL, legacy fixture, policy-version checkpoint invalidation, and supported Python versions pass. |
| B — ordering/resource safety | PASS | Stage-in gates submission; parsable ID and matching successful compute record are both mandatory; pending cancellation fails as execution. |
| C — integrity/storage | PASS | Content/existence levels, single-pass recording, allocation recheck, traversal, retries, locking, owner failure, NFS rewrite behavior, and checkpoint revalidation pass. |
| D — lifecycle/events/metrics | PASS | Typed phases, cancellation classification, completion confirmation, timing, recheck cost, revised estimate, dry-run, checkpoints, and FAIR sanitization pass. |
| E — docs/examples/tutorials | PASS | D/P findings, policy v4, completion record, metrics, limitations, examples, tutorial, version, and production evidence agree with implementation. |
| F — CI/CD | PASS | Exact executable commit `274515c` passed all 14 build/test jobs and the 47-check emulated-Slurm harness. |

## 4. T01-T18 traceability

| ID | Result | Evidence / limitation |
|---|---|---|
| T01 failed stage-in | PASS | Typed staging failure; no marker or submission. |
| T02 later transfer fails | PASS | Submission gated; partial retry rebuilds inputs. |
| T03 SSH drops | PASS (mock) | No submission; supplementary real-SSH success on one site. |
| T04 scheduler failure/cancellation | PASS | No-ID submission, nonzero execution, and pending cancellation are distinguished and cannot create reusable success. |
| T05 workflow true/task false | PASS | Explicit opt-out preserves legacy behavior. |
| T06 workflow false/task true | PASS | Explicit opt-in stages before submission. |
| T07 defaults absent | PASS | Legacy launcher remains byte-for-byte stable. |
| T08 node-local scratch | PASS | Missing marker/content and absent completion record fail before acceptance. |
| T09 BeeOND | PASS | Explicit reject, inherited fallback, unit tests, and combined CI job pass. |
| T10 changed input/checkpoint | PASS | Policy v4 and current source identity govern reuse. |
| T11 spaces/metacharacters | PASS | Quoting/non-execution and spaced-name single-pass tests pass. |
| T12 multiple/repeated refs | PASS | Manifest, globs, substitutions, repetition, 300-file and 5,000-file evidence. |
| T13 dry-run | PASS | No scratch, checkpoint, SSH, transfer, or scheduler side effect. |
| T14 no inputs | PASS | No-op staging and completion-record lifecycle tested. |
| T15 concurrent destination | PASS | Eligibility and token lock prevent replacement; owner failure is fail-atomic. |
| T16 prolonged queue | PASS within guarantee | Pending mutation fails at allocation start; pending cancellation is not accepted as success. |
| T17 CWL/FAIR | PASS | CWL independence and sanitized opt-in FAIR metadata preserved. |
| T18 RemoteSlurm MRO | PASS | Constructors, ports, ordering, checkpoint revalidation, completion record, cancellation, and cleanup covered. |

## 5. Findings

**No new findings.**

### Prior and post-audit finding status

| Finding | Final status |
|---|---|
| F-001–F-006 | RESOLVED |
| R-001–R-003 | RESOLVED |
| M-001 fail-atomic lock ownership | RESOLVED |
| L-001 stale harness inventory | RESOLVED |
| D-001 pending cancellation accepted | RESOLVED and independently audited |
| D-002 NFS visibility of completion record | RESOLVED and independently audited |
| P-001 repeated stage-in reads | RESOLVED |
| P-002 per-file checksum process overhead | RESOLVED |
| P-003 overstated metric | RESOLVED |
| Python 3.8/3.9 test portability regression | RESOLVED at `274515c`; CI confirmed |

## 6. Verification results

| Command/check | Result |
|---|---|
| Git refs/status/log/diff and remote-head/prune inspection | PASS; only report untracked, feature remote deleted, development published. |
| Source trace of D-001/D-002 and P-001–P-003 | PASS; failure phases, checkpoint code, policy v4, NFS rewrite, trap order, single-pass records, deterministic batching, and timing flow verified. |
| `python3 -m unittest -v tests.test_scheduler_prestaging tests.test_remote_scheduler_prestaging` | PASS: 92 tests in 178.382 s. |
| `python3 -m unittest discover -s tests -v` | PASS: 260 tests in 241.047 s. |
| `python3 tools/run_local_examples.py` | PASS: 18/18. |
| Required `py_compile` command | PASS. |
| Tutorial validator | PASS: 19 lessons and internal links. |
| Exact CI ruff targets, including deep tool | PASS. |
| Focused mypy targets | PASS; local installed mypy warns configured Python 3.8 is unsupported by that mypy version. |
| CI 43598110185 at exact executable commit `274515c` | PASS: all 14 build/test jobs. |
| Windows/Python 3.10 log | PASS: 260 tests, 32 skipped; cancellation and single-pass regressions pass. |
| Emulated-Slurm log | PASS: 92 focused tests; 47/47 harness checks; example verification passes. |
| Prior CI 43579136060 at D-001/D-002 commit `ab4cf0d` | PASS: all jobs, including cancellation scenario. |
| `git diff --check` from original baseline | Five intentional reports in the byte-preserving legacy fixture; no new whitespace defect. |

The implementation report records deeper manual evidence on one production Slurm 23.11.3/RHEL8-family cluster: pending cancellation, NFS visibility probes, 26/26 deep checks, two-node access, queue delay, contention, node-local failure, RemoteSlurm checkpoint revalidation, large-file and many-file runs, and comparative timings. The claims are internally consistent with the tool and CI, but this audit did not independently access the cluster or raw artifacts.

## 7. Residual risks and documented limitations

These remain disclosed operational limitations, not audit failures:

- The legacy non-pre-staged lifecycle can still misclassify a job cancelled before launch; changing it would violate the byte-preserved compatibility contract.
- A killed controller can leave a stale stage-in lock requiring verified manual removal.
- CRC-based listings detect accidental corruption, not hostile tampering.
- SCP, GridFTP, and SKYCDS sources retain existence-only integrity.
- The compute-start recheck consumes allocated time and can outweigh stage-in savings; the estimate is an upper bound and may be negative.
- Completion visibility and atomic `mkdir` remain dependent on site filesystem behavior.
- Other Slurm releases, site wrappers, production-scale transfers, busy queues, parallel filesystems, signals during stage-in, and real BeeOND/provider movers remain less exercised.
- Production measurements are from one cluster under uncontrolled load and are not benchmarks.

## 8. Final recommendation

**Accept the current scheduler-aware pre-staging implementation.** The newly discovered cancellation and NFS defects are fixed; the performance follow-up preserves integrity while reducing redundant work; local, portable, Windows, emulated-Slurm, and supplementary production evidence agree; documentation accurately limits the claims.

No implementation change is required by this audit.
