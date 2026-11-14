# Implementation report: scheduler-aware pre-staging

- **Branch:** `feature/scheduler-aware-prestaging`, based on `development` at `d8da197`. Not pushed, not merged, no PR.
- **Inputs:** `DAGonStar_Claude_Code_Implementation_Plan.md` (the plan) and `AGENTS.md`. There is no `CLAUDE.md` in the repository. Prepared for review against `DAGonStar_Codex_Independent_Audit_Plan.md`.
- **Audit remediation:** the independent audit (`AUDIT_REPORT_SCHEDULER_PRESTAGING.md`, verdict FAIL at `2d0d69a`) reported six findings, F-001 to F-006. All six are addressed in this revision; see [section 2](#2-audit-remediation).
- **Environment:** macOS 26.6.2 (arm64), Python 3.12.10, GNU bash 3.2.57, ruff 0.17.3, mypy 2.4.1.
- **Real-cluster validation: none.** No production or multi-node Slurm cluster was used, and no real job was submitted from this workstation. The only real-`sbatch` evidence is designed to come from the CI `beeond-slurm` job (single node, emulated site). That job has not run yet, because the branch is not pushed.

## 1. Implementation summary

`pre_stage` is an opt-in mode for Slurm and RemoteSlurm tasks. It turns the legacy lifecycle

```text
create scratch -> launcher (stage-in + command) -> sbatch -W -> queue -> allocation -> stage-in -> compute
```

into

```text
create scratch -> checkpoint record -> context.sh -> stage plan -> stage_in.sh on the submission host
  -> verify inputs (content, where the source is readable) -> .dagon/stage-in-identity.txt
  -> .dagon/stage-in-complete.json -> compute-only launcher -> sbatch --parsable -W -> queue -> allocation
  -> verify inputs visible on the compute node -> compute
```

- **Configuration.** `Workflow(pre_stage=False)` sets the default. `Slurm/RemoteSlurm(pre_stage=None|True|False)` inherits or overrides it. Values must be strict booleans.
- **Gate.** No scheduler submission of any kind happens before stage-in has succeeded. In particular, `sbatch` is never called when stage-in fails or cannot be confirmed, and `StagerMover.SLURM`, which submits copy jobs, is ineligible.
- **Integrity.** For inputs whose source is readable on the submission host (same-host `COPY` and `LINK`), the staged tree is compared with the source file by file (names, POSIX `cksum` CRC, and size). Other movers are checked for existence only, and this is stated as such.
- **Checkpoints.** A completed pre-staged task is reused only after the content identity of its inputs has been recomputed from the producers' current outputs and found unchanged.
- **Typed failures.** Errors are `StageInFailedError`, `SchedulerSubmissionError`, `ScheduledExecutionError`, and `PreStageConfigurationError`, and `task.failure_phase` records the phase. Submission and execution failures are told apart by the job identifier printed by `sbatch --parsable`.
- **Ineligible tasks.** BeeOND, parallel-mode, and `StagerMover.SLURM` tasks are ineligible. An explicit request raises; an inherited workflow default falls back to the legacy lifecycle with a warning. Other task types keep their legacy behaviour.
- **Dry run.** A pre-staged dry run has no side effects: no scratch directory, checkpoint entry, script, SSH traffic, transfer, or scheduler call.
- **Reference safety.** In pre-staged mode, `workflow://` references with `..` components (or an empty or `..` task name) are refused before any transfer.
- **Legacy launcher.** It is byte-for-byte unchanged, guarded by a fixture captured before the refactor. Legacy submissions do not use `--parsable`.
- **Hardening found during the work.** The legacy `context.sh` ran `cd <scratch>/.dagon` unquoted, so shell syntax in a scratch path was executed in every lifecycle. It is now quoted. The new transfer loop is injection-safe.

## 2. Audit remediation

| ID | Severity | Finding | Resolution | Regression evidence |
|---|---|---|---|---|
| F-001 | Critical | `StagerMover.SLURM` submitted `sbatch` copy jobs from `stage_in.sh`, before stage-in was confirmed, and never checked their exit status | `Task.pre_stage_unsupported_reason()` refuses `StagerMover.SLURM` (task or inherited). An explicit `pre_stage=True` raises `PreStageConfigurationError` at `add_task`; an inherited default falls back to the legacy lifecycle with a warning. `NORMAL` and `PARALLEL` remain eligible | `test_scheduler_stager_mover_is_rejected`; CI harness scenario `stager` |
| F-002 | High | A successful checkpoint was reused without validating inputs or the marker | After a successful stage-in, `stage_in.sh` writes `.dagon/stage-in-identity.txt` (a `cksum` listing of every content-verified source). Its SHA-256 goes into the marker and the checkpoint, together with the input manifest (references, relative paths, integrity levels) and `policy_version` 2. `reuse_checkpoint()` calls `validate_pre_staged_checkpoint()`, which resolves the inputs against the producers' **current** scratch directories, recomputes the identity on the submission host (local bash, or SSH for RemoteSlurm, with no file written), and reuses the checkpoint only on a match. An existence-only input, a missing producer, or a record without an identity also forces a rerun | `test_changed_input_invalidates_a_successful_checkpoint`, `test_checkpoint_that_cannot_be_reverified_is_not_reused`, `test_checkpoint_without_identity_is_not_reused`, `test_changed_remote_input_invalidates_a_successful_checkpoint` (over SSH), `test_checkpoint_resume_neither_restages_nor_resubmits` (unchanged input still reused), `test_identity_changes_with_content_only`; CI scenario `checkpoint` |
| F-003 | High | Verification used only `test -e`, so wrong content was marked complete | Each `StageInput` has an integrity level. For `content` inputs (the stager chose same-host `COPY` or `LINK`), `stage_in.sh` compares source and staged trees with `dagon_compare_staged`, following links. A mismatch fails staging with "staged content differs from its source", and no marker or identity is written. `existence` inputs (`SCP`, `GRIDFTP`, `SKYCDS`) are documented as not content-verified. `stage_in.sh` also removes `.dagon/inputs` before transferring, so data from an earlier attempt is never trusted | `test_corrupted_transfer_is_not_marked_complete` (a mover that exits 0 with wrong bytes), `test_copy_link_and_corruption` (same-size change, partial tree, symlinked tree), marker assertions in `test_inputs_are_staged_before_submission`; CI scenario `order` |
| F-004 | High (pre-existing) | `workflow:///A/../../outside` escaped the producer and consumer staging roots | `validate_reference_path()` refuses `..` components, empty or `..` task names, `..` workflow names, backslashes in names, and references that name a whole scratch directory. It runs in pre-staged planning (strict mode) and in the dry-run planner, before any transfer. The legacy parser is unchanged, so legacy behaviour is preserved; this is documented as a remaining legacy weakness | `test_unsafe_references_are_rejected`, `test_traversal_reference_is_refused_before_any_transfer`, `test_dry_run_rejects_unsafe_references`; CI scenario `traversal` |
| F-005 | High | A dry run created scratch and checkpoint state and, for RemoteSlurm, ran commands over SSH | `Task.execute()` routes a pre-staged dry run to `plan_pre_staged_dry_run()` before `create_working_dir()`. It parses and validates references, builds a placeholder plan, logs the planned order, and fires the usual events, with no scratch directory, checkpoint entry, `context.sh`, transfer, SSH call, or scheduler call. The legacy dry run is unchanged | `test_dry_run_neither_stages_nor_submits` (local execution and `on_execute` patched to fail, no scratch, no checkpoint entry), `test_dry_run_never_contacts_the_remote_host` (zero loopback-SSH events); CI scenario `dry` |
| F-006 | Medium | Submission and execution failures were told apart by the English substring `Submitted batch job` | Pre-staged submissions add `--parsable` (`Slurm.generate_command` while `task.pre_stage_submission` is set). `parsable_job_id()` accepts only a numeric first line (`<id>`, `<id>_<n>`, `<id>;<cluster>`). An identifier means execution failure; no identifier means submission failure. The identifier is recorded as `scheduler_job_id`. The mock `sbatch` and the loopback double honour `--parsable` | `test_pre_staged_submission_uses_parsable_output`, `test_failure_phase_does_not_depend_on_display_text`, `test_parsable_job_id`, `test_remote_submission_uses_parsable_output`; CI scenario `order` |

The audit also flagged the report itself:

- **`git diff --check`.** The audit was right. `git diff --check development...HEAD` reports trailing whitespace in `tests/fixtures/legacy_slurm_launcher.sh`. That whitespace is intentional, because the fixture reproduces the legacy launcher byte for byte. The working tree's `git diff --check` is clean. The earlier "Clean" claim did not distinguish the two.
- **T10 coverage.** The audit was right that it was overstated: the earlier tests covered a retry after a failed partial stage and reuse without change, not invalidation after a change. The changed-input tests above now cover it.

## 3. Files

### Created

| File | Purpose |
|---|---|
| `dagon/prestage.py` | Policy validation, `PreparedTask`, `StageInput` (with integrity level), stage-in script and compute launcher renderers, content-comparison and identity helpers, reference validation, marker document, `TaskPhase`, error hierarchy, core-hour estimate |
| `docs/scheduler_prestaging.md` | Dedicated guide (motivation, 200-core example, lifecycles, inheritance table, eligibility, filesystem requirements, recipes, generated files, verification and integrity, failure table, retries/checkpoints, dry run, events/metrics, CWL, security, evidence, FAQ/migration) |
| `examples/dataflow/slurm/mock_scheduler.py` | Deterministic `sbatch -W` stand-in that logs submission-time observations and honours `--parsable` |
| `examples/dataflow/slurm/pre_stage_mock.py` | Scheduler-free coastal-forecast workflow, legacy vs pre-staged, with assertions (`Verification: ok`) |
| `examples/dataflow/slurm/pre_stage_local.py` | Same workflow on a real local Slurm installation, with ordering evidence |
| `examples/dataflow/slurm/pre_stage_remote.py` | Same workflow on RemoteSlurm over SSH; no embedded hosts or credentials |
| `tests/test_scheduler_prestaging.py` | 63 local tests (configuration, generation, lifecycle order, strict stager, content identity, mock-`sbatch` integration, checkpoints, dry run, examples) |
| `tests/test_remote_scheduler_prestaging.py` | 13 RemoteSlurm tests with a loopback SSH double |
| `tests/fixtures/legacy_slurm_launcher.sh` | Legacy launcher captured from the unmodified `development` code |
| `tools/ci_prestage_slurm.py` | Live-Slurm CI harness (scenarios order, legacy, gate, beeond, stager, checkpoint, traversal, dry) |
| `IMPLEMENTATION_REPORT.md` | This report |

### Modified

| File | Change |
|---|---|
| `dagon/task.py` | `pre_stage`/`pre_stage_capable` class attributes; resolution and validation, including the `StagerMover.SLURM` refusal; `discover_context`, `build_stage_plan` (integrity level per input; reference validation in strict mode), and `prepare_task` (refactor of `pre_process_command`, which now renders `legacy_launcher()`); `execute` split into `execute_legacy`, `execute_pre_staged`, and the side-effect-free `plan_pre_staged_dry_run`; identity recording and `validate_pre_staged_checkpoint` in `reuse_checkpoint`; `parsable_job_id` failure classification; metrics, phases, and typed failures; quoted `cd` in `context.sh` |
| `dagon/batch.py` | `Slurm`/`RemoteSlurm` accept `pre_stage` (last keyword); `pre_stage_capable = True`; `run_on_submission_host`, `run_stage_in`, `run_identity_check` (no file written), `write_stage_marker` (atomic: local `os.replace`, remote temporary file plus `mv`), `read_scratch_file`, `requested_cores`; `--parsable` for pre-staged submissions only; BeeOND ineligibility; `pre_stage` in JSON and execution metadata |
| `dagon/__init__.py` | `Workflow(pre_stage=False)`; `add_task` validates explicit overrides; JSON round trip (key emitted only when enabled) |
| `dagon/stager/base.py` | `strict` mode for `stage_in`/`generate_command`: failure propagation, IFS-newline space safety, single-quoted `eval` template. `Stager.last_data_mover` records the chosen mover. The legacy text is unchanged |
| `tests/helpers.py` | Canned context script (no network), scratch config, mock-scheduler loader |
| `.github/workflows/ci.yml` | Ruff and mypy targets; the `beeond-slurm` job runs the pre-staging unit tests, `tools/ci_prestage_slurm.py`, and `pre_stage_local.py`; failure log collection |
| `tools/run_local_examples.py` | Adds `pre_stage_mock.py` |
| `README.md` | Feature list, status assessment, examples list, docs index, troubleshooting |
| `AGENTS.md` | Important path, CI note, "Scheduler-aware pre-staging maintenance" rules (now also: no scheduler submission of any kind before stage-in, content verification, checkpoint re-verification, side-effect-free dry run, `..` refusal, `--parsable` classification) |
| `docs/README.md`, `architecture.md`, `reference_guide.md`, `user_guide.md`, `configuration.md`, `developer_guide.md`, `checkpoints.md`, `fair_principles.md`, `cwl_export.md`, `tasktype_interoperability.md`, `beeond.md`, `platform_support.md`, `examples/dataflow_slurm.md` | Lifecycle, API, configuration, extension points (`run_identity_check`), restart semantics, metrics, CWL boundary, backend matrix, BeeOND limitation, CI description |
| `docs/tutorial/lesson_14_submit_a_task_through_slurm.md`, `DAGonStar_tutorial.ipynb`, `resources/glossary.md`, `resources/troubleshooting.md` | Lesson 14 section, controlled experiment and diagnosis; notebook section, exercise and verification cells (still 19 lessons) |
| `examples/dataflow/slurm/README.md` | Demos 5 to 7 with prerequisites and commands |

## 4. Architectural decisions

1. **Structured plan instead of text splitting.** `Task.prepare_task()` returns a `PreparedTask` with the header, prologue, stage blocks (one per reference), invocation, manifest, and resolved command. All three scripts (legacy launcher, `stage_in.sh`, compute launcher) are rendered from it, so each input is staged exactly once in each mode.
2. **One planning pass per execution.** Some movers have side effects while DAGonStar plans staging: SCP key exchange, an immediate local-to-remote SCP, GridFTP, and SKYCDS. The plan is therefore built once, in strict mode when pre-staging. Those transfers keep their semantics and still finish before `sbatch`. They run on the submission host, never as scheduler jobs.
3. **Same nonallocated route as `context.sh`.** `stage_in.sh` runs through `run_on_submission_host`: local bash for `Slurm`, SSH `create_file` plus `bash` for `RemoteSlurm`.
4. **Capability-based eligibility.** Eligibility comes from `pre_stage_capable` and `pre_stage_unsupported_reason()`, never from the type name. Explicit unsupported requests raise, both at `add_task` and again before scratch creation. An inherited default on an ineligible task keeps the legacy lifecycle, so a mixed workflow can enable the default without failing its Docker, Native, and other tasks.
5. **No scheduler use before stage-in (F-001).** Rejecting `StagerMover.SLURM` was chosen over a redesign. A scheduler-assisted stage-in would be a different contract (copy jobs consume allocations and need job-exit tracking), so it stays out of scope rather than being presented as pre-staging.
6. **Strict mode inside the existing stager**, rather than a second staging implementation. The legacy loop does not report a failed `cp` through `$?`, because the trailing `if` resets it. This was kept for compatibility, and strict mode fixes it for pre-staging only.
7. **Integrity matched to what can be substantiated (F-003).** Content is compared only where both trees are readable by the stage-in script. POSIX `cksum` was chosen because it exists on Linux, macOS, and Git Bash, unlike `sha256sum` or `shasum`. Its CRC detects accidental corruption, not tampering, and the documentation says so. Existence-only inputs are labelled, not presented as verified.
8. **Content identity, not timestamps (F-002).** The identity is a hash of names, CRCs, and sizes, recomputed against the producers' current directories. A producer that reruns with identical content does not invalidate its consumers; any content change does. When re-verification is impossible, the safe default is to rerun.
9. **Marker written by Python after a verified exit 0** (atomic). `stage_in.sh` removes any old marker, identity record, and staged inputs first. The marker is provenance, never a skip token.
10. **Structured submission evidence (F-006).** `--parsable` is added only to pre-staged submissions, so the legacy submit command is unchanged.
11. **Compute-side visibility check.** A non-shared scratch cannot be detected before submission. The compute launcher therefore fails fast if the marker or an input is not visible, before the prologue and the command run.
12. **Public `Status` unchanged.** Internal `TaskPhase` (`PREPARING`, `STAGING`, `STAGED`, `SUBMITTED`, `COMPLETED`, `FAILED`) is separate, and `RUNNING` keeps its meaning.
13. **Events.** In pre-staged mode, `on_task_staging_in_start/end` bracket context discovery, planning, and the actual transfer. Legacy timing is unchanged and documented.

### Discrepancies between the plan and the code

| Plan assumption | Observed in source | Handling |
|---|---|---|
| Line numbers in `task.py`/`batch.py` | Close but shifted (for example `Workflow` at line 100, `pre_process_command` at line 636 before the change) | Rechecked before editing |
| The stager propagates transfer failures through `code=1` | The `if [ $? -ne 0 ]` after the loop sees the status of the preceding `if`, so a failed `cp` is lost | Strict mode for pre-staging; legacy unchanged and documented |
| Stage-in is always shell text in the launcher | Some movers transfer while DAGonStar plans staging | Documented; they still finish before `sbatch` |
| Every stager mover runs outside the scheduler | `StagerMover.SLURM` submits copy jobs | Ineligible for pre-staging (F-001) |
| Generated scripts are quote-safe | The legacy `cd` in the launcher and `context.sh` was unquoted, and the stager used `eval` on expanded paths | `context.sh` fixed (both modes); new scripts quoted; the legacy launcher is kept byte-identical by design |
| "Shell paths with spaces" fully supported | `workflow://` references end at a space and are substituted unquoted into the user command (legacy parser) | Stage-in supports spaces and metacharacters (tested). The user-command limitation is documented, with a workaround (`f=workflow:///A/x ; cat "$f"`) |
| BeeOND staging target | Inputs are staged into `<working_dir>/.dagon/inputs`, not into the BeeOND mount | BeeOND remains ineligible (conservative; the task- and workflow-scope lifecycles depend on an allocation); documented as future work |

## 5. API changes (all additive, positional order preserved)

- `Workflow(..., portable_emulation=False, pre_stage=False)`, plus the attribute `workflow.pre_stage`.
- `Slurm(..., beeond=None, pre_stage=None)` and `RemoteSlurm(..., ssh_port=22, pre_stage=None)`; also works through `DagonTask(TaskType.SLURM, ..., pre_stage=...)`.
- `Task` additions:
  - Methods: `resolve_pre_stage()`, `validate_pre_stage_declaration()`, `pre_stage_unsupported_reason()`, `prepare_task()`, `discover_context()`, `build_stage_plan()`, `execute_pre_staged()`, `plan_pre_staged_dry_run()`, `execute_legacy()`, `validate_pre_staged_checkpoint()`, `pre_stage_metadata()`.
  - Attributes: `pre_stage_phase`, `pre_stage_metrics`, `prepared_task`, `failure_phase`, `pre_stage_submission`.
  - Backend hooks: `run_stage_in`, `run_identity_check`, `write_stage_marker`, `read_scratch_file`, `requested_cores`.
- `dagon.task.parsable_job_id()`.
- `Stager.stage_in(..., strict=False)`, `Stager.generate_command(..., strict=False)`, and `Stager.last_data_mover`.
- New module `dagon.prestage`, including `validate_reference_path`, `identity_script`, `identity_digest`, `IDENTITY_NAME`, `INTEGRITY_CONTENT`, and `INTEGRITY_EXISTENCE`. `PRE_STAGE_POLICY_VERSION` is 2, and the marker schema is `dagonstar.stage-in-marker/2`.
- JSON: workflow `pre_stage` (only when `True`) and task `pre_stage` (only when not `None`). `get_execution_metadata()["pre_stage"]` and FAIR `execution.pre_stage` appear only when pre-staging is configured. They gain `inputs_content_verified`, `scheduler_job_id`, and `dry_run`, and remain path-free. CWL output is unchanged and independent of `pre_stage` (tested).
- `pre_process_command()` keeps its signature and output.

## 6. Test results

Commands were run on this workstation after the audit fixes; the results are below.

| Command | Result |
|---|---|
| Baseline before any change: `python3 -m unittest discover -s tests` | 168 tests, OK |
| `python3 -m unittest discover -s tests -v` | **244 tests, OK, 0 skipped** on macOS (168 existing + 76 pre-staging) |
| `python3 tools/run_local_examples.py` (with `PYTHONPATH=$PWD`) | 18/18 examples passed, including `pre_stage_mock.py` |
| `python3 tools/validate_tutorial.py`; notebook JSON load | Validated 19 canonical lessons and internal tutorial links; notebook is valid JSON |
| `python3 -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py dagon/stager/*.py` | OK |
| `ruff check` on the CI-targeted files | All checks passed |
| `mypy --follow-imports=skip` on the CI-typed modules, including `dagon/prestage.py` | No issues (local mypy 2.4 needed `--python-version 3.10`; CI pins mypy 1.13) |
| `ruff check --select F` on `dagon/task.py`, `dagon/batch.py`, `dagon/stager/base.py` (outside the CI targets) | 6 findings, all pre-existing in `development`; none introduced by this work |
| `git diff --check` (working tree) | Clean |
| `git diff --check development...HEAD` | Five trailing-whitespace lines, all in `tests/fixtures/legacy_slurm_launcher.sh`, intentional (byte-identical legacy launcher) |
| `tools/ci_prestage_slurm.py` against the mock `sbatch` (scratch script, not CI) | 34 passed, 0 failed (8 scenarios) |
| `tools/ci_prestage_slurm.py` and `pre_stage_local.py` with real `sbatch` | **Not run here** (no Slurm on this workstation); designed for the CI `beeond-slurm` job |

Expected skips on other platforms: `tests/test_remote_scheduler_prestaging.py` (the loopback SSH host is POSIX) and the metacharacter-path test are skipped on Windows, and the symbolic-link part of `test_copy_link_and_corruption` is skipped there. All other new tests are cross-platform.

### Coverage against the requested scenarios and the audit's T01–T18

| Scenario | Test(s) |
|---|---|
| Legacy default unchanged (T07) | `test_legacy_launcher_is_byte_for_byte_unchanged`, `test_default_keeps_staging_inside_the_launcher`, `test_legacy_run_stages_inside_the_job`, `test_legacy_remote_slurm_is_unchanged`, `test_default_json_is_unchanged`, `test_pre_staged_submission_uses_parsable_output` (legacy submit has no `--parsable`), plus all 168 existing tests |
| Inheritance and overrides (T05, T06) | `test_resolution_matrix`, `test_inheritance_follows_later_workflow_changes`, `test_task_opt_out_keeps_legacy_launcher`, `test_inherited_and_explicit_pre_stage_stage_before_submission` |
| Invalid values, positional API | `test_invalid_values_are_rejected`, `test_positional_api_is_unchanged` |
| Order relative to `sbatch`; no scheduler use during stage-in | `LifecycleOrderTests` (call sequence), `test_inputs_are_staged_before_submission` (event time before mock-`sbatch` time; marker and inputs present at submission), `test_stage_in_runs_over_ssh_before_remote_sbatch`, `test_scheduler_stager_mover_is_rejected` |
| Failed staging (T01), missing input, later input fails (T02) | `test_failed_staging_never_submits`, `test_missing_input_fails_staging_without_submission`, `test_failure_of_a_later_input_stops_staging_and_submission`, `test_remote_staging_failure_never_submits`, `StrictStagerTests` |
| Corrupted or partial content | `test_corrupted_transfer_is_not_marked_complete`, `test_copy_link_and_corruption` |
| SSH drop (T03), failed remote script or marker creation | `test_ssh_disconnect_during_stage_in_never_submits`, `test_failed_remote_script_creation_never_submits`, `test_failed_marker_write_never_submits` |
| Submission failure (T04), execution failure, unexpected scheduler output | `test_submission_and_execution_failures_are_distinguished`, `test_failure_phase_does_not_depend_on_display_text`, `test_parsable_job_id`, `test_rejected_submission_keeps_staged_inputs`, `test_job_failure_is_an_execution_failure`, `test_failed_remote_sbatch_is_a_submission_failure`, `test_errors_are_typed` |
| Non-shared scratch (T08) | `test_job_fails_clearly_when_staged_data_is_not_visible_in_the_allocation` (emulated); not detectable before submission, see limitations |
| BeeOND (T09), parallel mode, `StagerMover.SLURM`, unsupported backends | `test_beeond_explicit_request_is_rejected`, `test_beeond_inherited_request_falls_back_with_warning`, `test_parallel_mode_is_not_eligible`, `test_scheduler_stager_mover_is_rejected`, `test_explicit_request_on_unsupported_backend_is_rejected`, `test_other_task_types_are_unchanged_under_workflow_default`; existing `tests.test_beeond` passes |
| Stale checkpoint with changed input (T10), retry, stale marker | `test_changed_input_invalidates_a_successful_checkpoint`, `test_changed_remote_input_invalidates_a_successful_checkpoint`, `test_checkpoint_that_cannot_be_reverified_is_not_reused`, `test_checkpoint_without_identity_is_not_reused`, `test_checkpoint_resume_neither_restages_nor_resubmits`, `test_retry_after_partial_staging_restages_and_never_trusts_a_stale_marker` |
| Spaces and metacharacters (T11) | `test_stage_in_handles_spaces_in_scratch_paths`, `test_shell_metacharacters_in_scratch_paths_are_never_executed` (fails without the `context.sh` fix), `test_strict_mode_reports_failures_and_handles_spaces`, `test_copy_link_and_corruption` (spaces in paths) |
| Path traversal | `test_unsafe_references_are_rejected`, `test_traversal_reference_is_refused_before_any_transfer`, `test_dry_run_rejects_unsafe_references` |
| Multiple producers, repeated refs (T12), concurrent consumers (T15), globs | `test_manifest_and_substitutions_cover_multiple_producers`, `test_repeated_references_and_concurrent_consumers`, the glob in `pre_stage_mock.py`, `test_stage_in_handles_spaces_in_scratch_paths` |
| Dry run (T13) | `test_dry_run_neither_stages_nor_submits` (no scratch, no checkpoint entry, no local command), `test_dry_run_never_contacts_the_remote_host` (zero SSH events) |
| No inputs (T14) | `test_task_without_inputs_submits_directly`, `test_empty_inputs_produce_a_no_op_stage_script` |
| CWL and FAIR (T17) | `test_cwl_export_is_independent_of_pre_stage`, `test_fair_records_pre_stage_metadata_without_paths`, a path-free metadata assertion |
| RemoteSlurm MRO and constructor, non-default port (T18) | `test_pre_stage_survives_the_multiple_inheritance_constructor`, `test_remote_example_with_loopback_ssh`, `test_remote_submission_uses_parsable_output`; one `sbatch` per task asserted |
| Prolonged queue (T16) | Not testable without a real queue; the filesystem requirement is documented |
| Cleanup | Failure tests assert that staged data and markers are kept after submission or execution failures; earlier staged inputs are discarded at the next stage-in; garbage collection is unchanged and covered by the existing suites |

## 7. Documentation and tutorial updates

The guide is `docs/scheduler_prestaging.md`, linked from `README.md`, `docs/README.md`, and each affected guide. For the audit fixes it gained a "Verification and integrity" section. The eligibility, generated-files, failure, checkpoint, dry-run, metrics, security, and evidence sections were rewritten to match the new behaviour. `checkpoints.md`, `tasktype_interoperability.md`, `user_guide.md`, `configuration.md`, `developer_guide.md`, `architecture.md`, `fair_principles.md`, `platform_support.md`, `README.md` (including the project-status assessment), `AGENTS.md`, the Slurm example README, Lesson 14, the notebook's pre-staging cells, and the troubleshooting table were updated accordingly. The validator's 19-lesson structure is unchanged. The repository has no changelog convention, so none was added.

## 8. CI/CD changes

- `quality`: ruff and mypy cover `dagon/prestage.py`, `tools/ci_prestage_slurm.py`, and the new examples.
- `test`, `rocky-linux`, `raspberry-pi`: the new test modules run through the existing `unittest discover`, and `pre_stage_mock.py` runs through `tools/run_local_examples.py`.
- `beeond-slurm`, renamed in display to "BeeOND and pre-staging on Slurm (emulated site)" (the job id is unchanged, so `needs:` still works): it runs the pre-staging unit tests, `tools/ci_prestage_slurm.py --partition ci`, and `pre_stage_local.py --partition ci`. On failure it collects the stage-in scripts and markers. The harness now also covers `--parsable` job identifiers, content verification, the `StagerMover.SLURM` rejection, changed-input checkpoint invalidation, `..` refusal, and the side-effect-free dry run.
- No jobs were removed. `development` is still a trigger. Release automation is untouched.

## 9. Known limitations

1. **No production validation.** There is no multi-node, production-scale, or real-queue evidence. The CI cluster is a single node with an empty queue, so it shows ordering and gating, not queue-time effects. The audit fixes, like the rest of the feature, have not yet run against real `sbatch`.
2. **`--parsable` with `-W`** is assumed to print the job identifier on the first line, then wait. This is standard `sbatch` behaviour, but it has been exercised here only with the mock and the loopback double. The CI `order` scenario checks it with real `sbatch`.
3. **Integrity is CRC-based and partial.** `cksum` detects accidental corruption, not tampering. `SCP`, `GRIDFTP`, and `SKYCDS` inputs are existence-only. Content verification and checkpoint re-verification read every input once more on the submission host (I/O proportional to input size).
4. **Checkpoint reuse is conservative.** A completed task with any existence-only input is never reused: it is staged and submitted again on resume. Checkpoints written before policy version 2 are not reused. Legacy (non-pre-staged) checkpoints are still reused without input validation, as before.
5. **Shared-scratch visibility cannot be verified before submission.** The compute-side check catches a missing or empty scratch at job start, after the allocation is granted. It checks existence on the compute node, not content, so it cannot detect a different copy of the same files at the same path.
6. **User-command quoting (legacy parser).** A `workflow://` reference ends at a space and is substituted unquoted. Scratch paths with spaces break the user command, although staging succeeds. A trailing `;` must be separated by a space.
7. **The legacy lifecycle keeps historical weaknesses**, intentionally byte-identical: an unquoted `cd` in the launcher, transfer failures not reflected in `code`, `eval` of expanded paths, and an unchecked `workflow://` parser that accepts `..` (F-004 is fixed for pre-staging only). Only `context.sh` was fixed in both modes.
8. **BeeOND, parallel mode, and `StagerMover.SLURM` are ineligible** (future work, if ever, under a separately designed contract).
9. **Dry-run plans are approximate.** Because a pre-staged dry run skips context discovery, it shows placeholders for unassigned directories and does not report the mover or integrity levels.
10. **Same-destination concurrency and cancellation.** Concurrent consumers are safe with distinct working directories (tested). Two tasks sharing one fixed `working_dir`, and cancellation during stage-in, are not guarded or tested.
11. **Timing.** `allocation_wait_seconds` and `execution_seconds` have one-second resolution and rely on synchronised clocks between the submission host and the compute nodes. `scheduler_wall_seconds` includes the queue wait.
12. **Pre-existing, not caused by this change.** A full-suite run once left untracked `ssh_key`/`ssh_key.pub` files in the repository root (created by an existing test's context script); I moved them to the scratchpad. Ruff reports pre-existing issues in `dagon/stager/base.py`, `dagon/task.py`, `dagon/batch.py`, and the legacy Slurm demos, all outside the CI ruff targets.

## 10. Remaining HPC-cluster validation

- Push the branch and confirm that the `beeond-slurm` CI job passes, especially `tools/ci_prestage_slurm.py` (all eight scenarios) and `pre_stage_local.py` with real `sbatch`.
- On a production site, with authorisation: run `pre_stage_local.py --scratch <shared> --cores <N>` and `--legacy` with a representative input size. Confirm the `staging finished <= allocation started` evidence, that `sacct` shows the job's start after stage-in, and that `sacct` shows no job other than the compute job for the task.
- Run `pre_stage_remote.py` against a real login node (key handling, `create_file` over SSH, remote `sbatch --parsable`, checkpoint re-verification over SSH), including a non-default port.
- Confirm the shared, persistent scratch assumption for each site's file systems. Test a deliberately node-local path to observe the compute-side failure message.
- Measure the cost of content verification for representative input sizes on the login node, and exercise the SCP and GridFTP movers (existence-only) in pre-staged mode where they are used.

## 11. Commit history

```text
(this commit) Record the audit-fix commits in the implementation report
aac6d5c Document the pre-staging audit fixes and update the report
c6b9761 Cover the audit fixes in the real-Slurm pre-staging harness
88e5c17 Fix the audit findings in scheduler-aware pre-staging
2d0d69a Add implementation report for scheduler-aware pre-staging
4c971a5 Document the compute-side visibility check and quoting fixes
025525e Harden pre-staging against injection and non-shared scratch
1170792 Document scheduler-aware pre-staging
531c7bf Check scheduler-aware pre-staging in CI
91b9251 Add pre-staging examples for mock, local and remote Slurm
5a13076 Test scheduler-aware pre-staging with mock Slurm and SSH
3c94ee7 Add scheduler-aware pre-staging for Slurm and RemoteSlurm
```
