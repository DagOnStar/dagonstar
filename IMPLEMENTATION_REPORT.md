# Implementation report: scheduler-aware pre-staging

- **Branch:** `feature/scheduler-aware-prestaging`, based on `development` at `d8da197`. Not pushed, not merged, no PR.
- **Inputs:** `DAGonStar_Claude_Code_Implementation_Plan.md` (the plan) and `AGENTS.md`. There is no `CLAUDE.md` in the repository. Prepared for review against `DAGonStar_Codex_Independent_Audit_Plan.md`.
- **Environment:** macOS 26.6.2 (arm64), Python 3.12.10, GNU bash 3.2.57, ruff 0.17.3, mypy 2.4.1.
- **Real-cluster validation: none.** No production or multi-node Slurm cluster was used. No real job was submitted from this workstation. The only real-`sbatch` evidence is designed to come from the CI `beeond-slurm` job (single-node, emulated site). That job has not run yet, because the branch is not pushed.

## 1. Implementation summary

`pre_stage` is an opt-in mode for Slurm and RemoteSlurm tasks. It turns the legacy lifecycle

```text
create scratch -> launcher (stage-in + command) -> sbatch -W -> queue -> allocation -> stage-in -> compute
```

into

```text
create scratch -> checkpoint record -> context.sh -> stage plan -> stage_in.sh on the submission host
  -> verify inputs -> .dagon/stage-in-complete.json -> compute-only launcher -> sbatch -W -> queue -> allocation
  -> verify inputs visible on the compute node -> compute
```

- **Configuration.** `Workflow(pre_stage=False)` sets the default. `Slurm/RemoteSlurm(pre_stage=None|True|False)` inherits or overrides it. Values must be strict booleans.
- **Gate.** `sbatch` is never called when stage-in fails or cannot be confirmed.
- **Typed failures.** Errors are `StageInFailedError`, `SchedulerSubmissionError`, `ScheduledExecutionError`, and `PreStageConfigurationError`, and `task.failure_phase` records the phase.
- **Ineligible tasks.** BeeOND and parallel-mode tasks are ineligible: an explicit request raises, and an inherited workflow default falls back to the legacy lifecycle with a warning. Other task types keep their legacy behaviour.
- **Legacy launcher.** It is byte-for-byte unchanged, guarded by a fixture captured before the refactor.
- **Hardening found during the work.** The legacy `context.sh` ran `cd <scratch>/.dagon` unquoted, so shell syntax in a scratch path was executed in every lifecycle. It is now quoted. The new transfer loop is injection-safe.

## 2. Files

### Created

| File | Purpose |
|---|---|
| `dagon/prestage.py` | Policy validation, `PreparedTask`, `StageInput`, stage-in script and compute launcher renderers, marker document, `TaskPhase`, error hierarchy, core-hour estimate |
| `docs/scheduler_prestaging.md` | Dedicated guide (motivation, 200-core example, lifecycles, inheritance table, eligibility, filesystem requirements, recipes, generated files, failure table, retries/checkpoints, dry run, events/metrics, CWL, security, evidence, FAQ/migration) |
| `examples/dataflow/slurm/mock_scheduler.py` | Deterministic `sbatch -W` stand-in that logs submission-time observations |
| `examples/dataflow/slurm/pre_stage_mock.py` | Scheduler-free coastal-forecast workflow, legacy vs pre-staged, with assertions (`Verification: ok`) |
| `examples/dataflow/slurm/pre_stage_local.py` | Same workflow on a real local Slurm installation, with ordering evidence |
| `examples/dataflow/slurm/pre_stage_remote.py` | Same workflow on RemoteSlurm over SSH; no embedded hosts or credentials |
| `tests/test_scheduler_prestaging.py` | 50 local tests (configuration, generation, lifecycle order, strict stager, mock-`sbatch` integration, examples) |
| `tests/test_remote_scheduler_prestaging.py` | 10 RemoteSlurm tests with a loopback SSH double |
| `tests/fixtures/legacy_slurm_launcher.sh` | Legacy launcher captured from the unmodified `development` code |
| `tools/ci_prestage_slurm.py` | Live-Slurm CI harness (order, legacy, gate, BeeOND negative) |
| `IMPLEMENTATION_REPORT.md` | This report |

### Modified

| File | Change |
|---|---|
| `dagon/task.py` | `pre_stage`/`pre_stage_capable` class attributes; resolution and validation; `discover_context`, `build_stage_plan`, and `prepare_task` (refactor of `pre_process_command`, which now renders `legacy_launcher()`); `execute` split into `execute_legacy` and `execute_pre_staged`; metrics, phases, and typed failures; quoted `cd` in `context.sh` |
| `dagon/batch.py` | `Slurm`/`RemoteSlurm` accept `pre_stage` (last keyword); `pre_stage_capable = True`; `run_on_submission_host`, `run_stage_in`, `write_stage_marker` (atomic: local `os.replace`, remote temporary file plus `mv`), `read_scratch_file`, `requested_cores`; BeeOND ineligibility; `pre_stage` in JSON and execution metadata. The `context.sh` route is refactored without a behaviour change |
| `dagon/__init__.py` | `Workflow(pre_stage=False)`; `add_task` validates explicit overrides; JSON round trip (key emitted only when enabled) |
| `dagon/stager/base.py` | `strict` mode for `stage_in`/`generate_command`: failure propagation, IFS-newline space safety, single-quoted `eval` template, exported `file`/`dst`. The legacy text is unchanged |
| `tests/helpers.py` | Canned context script (no network), scratch config, mock-scheduler loader |
| `.github/workflows/ci.yml` | Ruff and mypy targets; the `beeond-slurm` job runs the pre-staging unit tests, `tools/ci_prestage_slurm.py`, and `pre_stage_local.py`; failure log collection |
| `tools/run_local_examples.py` | Adds `pre_stage_mock.py` |
| `README.md` | Feature list, status assessment, examples list, docs index, troubleshooting |
| `AGENTS.md` | Important path, CI note, "Scheduler-aware pre-staging maintenance" rules |
| `docs/README.md`, `architecture.md`, `reference_guide.md`, `user_guide.md`, `configuration.md`, `developer_guide.md`, `checkpoints.md`, `fair_principles.md`, `cwl_export.md`, `tasktype_interoperability.md`, `beeond.md`, `platform_support.md`, `examples/dataflow_slurm.md` | Lifecycle, API, configuration, extension points, restart semantics, metrics, CWL boundary, backend matrix, BeeOND limitation, CI description |
| `docs/tutorial/lesson_14_submit_a_task_through_slurm.md`, `DAGonStar_tutorial.ipynb`, `resources/glossary.md`, `resources/troubleshooting.md` | Lesson 14 section, controlled experiment and diagnosis; notebook section, exercise and verification cells (still 19 lessons) |
| `examples/dataflow/slurm/README.md` | Demos 5 to 7 with prerequisites and commands |

## 3. Architectural decisions

1. **Structured plan instead of text splitting.** `Task.prepare_task()` returns a `PreparedTask` with the header, prologue, stage blocks (one per reference), invocation, manifest, and resolved command. All three scripts (legacy launcher, `stage_in.sh`, compute launcher) are rendered from it, so each input is staged exactly once in each mode.
2. **One planning pass per execution.** Some movers have side effects while DAGonStar plans staging: SCP key exchange, an immediate local-to-remote SCP, GridFTP, and SKYCDS. The plan is therefore built once, in strict mode when pre-staging. Those transfers keep their semantics and still finish before `sbatch`.
3. **Same nonallocated route as `context.sh`.** `stage_in.sh` runs through `run_on_submission_host`: local bash for `Slurm`, SSH `create_file` plus `bash` for `RemoteSlurm`. This follows the plan's observation that `context.sh` never enters the scheduler.
4. **Capability-based eligibility.** Eligibility comes from `pre_stage_capable` and `pre_stage_unsupported_reason()`, never from the type name. Explicit unsupported requests raise, both at `add_task` and again before scratch creation. An inherited default on an ineligible task keeps the legacy lifecycle: only eligible backends log a warning, and other task types are silent, which is the documented policy. This lets a mixed workflow enable the default without failing its Docker, Native, and other tasks.
5. **Strict mode inside the existing stager**, rather than a second staging implementation. The legacy loop does not report a failed `cp` through `$?`: the trailing `if` resets it. This was kept for compatibility, and strict mode fixes it for pre-staging only.
6. **Marker written by Python after a verified exit 0** (atomic). `stage_in.sh` removes any old marker first. The marker is provenance, never a skip token, so changed or partial inputs are always restaged.
7. **Compute-side visibility check.** A non-shared scratch cannot be detected before submission. The compute launcher therefore fails fast if the marker or an input is not visible, before the prologue and the command run.
8. **Public `Status` unchanged.** Internal `TaskPhase` (`PREPARING`, `STAGING`, `STAGED`, `SUBMITTED`, `COMPLETED`, `FAILED`) is separate, and `RUNNING` keeps its meaning.
9. **Events.** In pre-staged mode, `on_task_staging_in_start/end` bracket the actual transfer. Legacy timing is unchanged and documented.

### Discrepancies between the plan and the code

| Plan assumption | Observed in source | Handling |
|---|---|---|
| Line numbers in `task.py`/`batch.py` | Close but shifted (for example `Workflow` at line 100, `pre_process_command` at line 636 before the change) | Rechecked before editing |
| The stager propagates transfer failures through `code=1` | The `if [ $? -ne 0 ]` after the loop sees the status of the preceding `if`, so a failed `cp` is lost | Strict mode for pre-staging; legacy unchanged and documented |
| Stage-in is always shell text in the launcher | Some movers transfer while DAGonStar plans staging | Documented; they still finish before `sbatch` |
| Generated scripts are quote-safe | The legacy `cd` in the launcher and `context.sh` was unquoted, and the stager used `eval` on expanded paths | `context.sh` fixed (both modes); new scripts quoted; the legacy launcher is kept byte-identical by design |
| "Shell paths with spaces" fully supported | `workflow://` references end at a space and are substituted unquoted into the user command (legacy parser) | Stage-in supports spaces and metacharacters (tested). The user-command limitation is documented, with a workaround (`f=workflow:///A/x ; cat "$f"`) |
| BeeOND staging target | Inputs are staged into `<working_dir>/.dagon/inputs`, not into the BeeOND mount | BeeOND remains ineligible (conservative; the task- and workflow-scope lifecycles depend on an allocation); documented as future work |

## 4. API changes (all additive, positional order preserved)

- `Workflow(..., portable_emulation=False, pre_stage=False)`, plus the attribute `workflow.pre_stage`.
- `Slurm(..., beeond=None, pre_stage=None)` and `RemoteSlurm(..., ssh_port=22, pre_stage=None)`; also works through `DagonTask(TaskType.SLURM, ..., pre_stage=...)`.
- `Task` additions:
  - Methods: `resolve_pre_stage()`, `validate_pre_stage_declaration()`, `pre_stage_unsupported_reason()`, `prepare_task()`, `discover_context()`, `build_stage_plan()`, `execute_pre_staged()`, `execute_legacy()`, `pre_stage_metadata()`.
  - Attributes: `pre_stage_phase`, `pre_stage_metrics`, `prepared_task`, `failure_phase`.
  - Backend hooks: `run_stage_in`, `write_stage_marker`, `read_scratch_file`, `requested_cores`.
- `Stager.stage_in(..., strict=False)` and `Stager.generate_command(..., strict=False)`.
- New module `dagon.prestage`.
- JSON: workflow `pre_stage` (only when `True`) and task `pre_stage` (only when not `None`). `get_execution_metadata()["pre_stage"]` and FAIR `execution.pre_stage` appear only when pre-staging is configured. CWL output is unchanged and independent of `pre_stage` (tested).
- `pre_process_command()` keeps its signature and output.

## 5. Test results

Commands were run on this workstation after the final commit; the results are below.

| Command | Result |
|---|---|
| Baseline before any change: `python3 -m unittest discover -s tests` | 168 tests, OK |
| `python3 -m unittest discover -s tests -v` | **228 tests, OK, 0 skipped** on macOS (168 existing + 60 new) |
| `python3 tools/run_local_examples.py` (with `PYTHONPATH=$PWD`) | 18/18 examples passed, including `pre_stage_mock.py` |
| `python3 tools/validate_tutorial.py` | Validated 19 canonical lessons and internal tutorial links |
| `python3 -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py` and `python3 -m compileall -q dagon` | OK |
| `ruff check` on the CI-targeted files (now including `dagon/prestage.py`, the new tests, tools, and examples) | All checks passed |
| `mypy --follow-imports=skip` on the CI-typed modules plus `dagon/prestage.py` | No issues (local mypy 2.4 needed `--python-version 3.10`; CI pins mypy 1.13) |
| `bash -n` on `tools/ci/slurm/*.sh`; generated scripts checked with `bash -n` inside the tests | OK |
| `git diff --check` | Clean |
| `tools/ci_prestage_slurm.py` against the mock `sbatch` (scratch script, not CI) | 20 passed, 0 failed |
| `tools/ci_prestage_slurm.py` and `pre_stage_local.py` with real `sbatch` | **Not run here** (no Slurm on this workstation); designed for the CI `beeond-slurm` job |

Expected skips on other platforms: `tests/test_remote_scheduler_prestaging.py` (the loopback SSH host is POSIX) and the metacharacter-path test are skipped on Windows. All other new tests are cross-platform.

### Coverage against the requested scenarios and the audit's T01–T18

| Scenario | Test(s) |
|---|---|
| Legacy default unchanged (T07) | `test_legacy_launcher_is_byte_for_byte_unchanged`, `test_default_keeps_staging_inside_the_launcher`, `test_legacy_run_stages_inside_the_job`, `test_legacy_remote_slurm_is_unchanged`, `test_default_json_is_unchanged`, plus all 168 existing tests |
| Inheritance and overrides (T05, T06) | `test_resolution_matrix`, `test_inheritance_follows_later_workflow_changes`, `test_task_opt_out_keeps_legacy_launcher`, `test_inherited_and_explicit_pre_stage_stage_before_submission` |
| Invalid values, positional API | `test_invalid_values_are_rejected`, `test_positional_api_is_unchanged` |
| Order relative to `sbatch` | `LifecycleOrderTests` (call sequence), `test_inputs_are_staged_before_submission` (event time before mock-`sbatch` time; marker and inputs present at submission), `test_stage_in_runs_over_ssh_before_remote_sbatch` |
| Failed staging (T01), missing input, later input fails (T02) | `test_failed_staging_never_submits`, `test_missing_input_fails_staging_without_submission`, `test_failure_of_a_later_input_stops_staging_and_submission`, `test_remote_staging_failure_never_submits`, `StrictStagerTests` |
| SSH drop (T03), failed remote script or marker creation | `test_ssh_disconnect_during_stage_in_never_submits`, `test_failed_remote_script_creation_never_submits`, `test_failed_marker_write_never_submits` |
| Submission failure (T04) and execution failure | `test_submission_and_execution_failures_are_distinguished`, `test_rejected_submission_keeps_staged_inputs`, `test_job_failure_is_an_execution_failure`, `test_failed_remote_sbatch_is_a_submission_failure`, `test_errors_are_typed` |
| Non-shared scratch (T08) | `test_job_fails_clearly_when_staged_data_is_not_visible_in_the_allocation` (emulated); not detectable before submission, see limitations |
| BeeOND (T09), parallel mode, unsupported backends | `test_beeond_explicit_request_is_rejected`, `test_beeond_inherited_request_falls_back_with_warning`, `test_parallel_mode_is_not_eligible`, `test_explicit_request_on_unsupported_backend_is_rejected`, `test_other_task_types_are_unchanged_under_workflow_default`; existing `tests.test_beeond` passes |
| Retry, stale marker (T10), checkpoint resume | `test_retry_after_partial_staging_restages_and_never_trusts_a_stale_marker`, `test_checkpoint_resume_neither_restages_nor_resubmits` |
| Spaces and metacharacters (T11) | `test_stage_in_handles_spaces_in_scratch_paths`, `test_shell_metacharacters_in_scratch_paths_are_never_executed` (fails without the `context.sh` fix), `test_strict_mode_reports_failures_and_handles_spaces` |
| Multiple producers, repeated refs (T12), concurrent consumers (T15), globs | `test_manifest_and_substitutions_cover_multiple_producers`, `test_repeated_references_and_concurrent_consumers`, the glob in `pre_stage_mock.py`, `test_stage_in_handles_spaces_in_scratch_paths` |
| Dry run (T13) | `test_dry_run_neither_stages_nor_submits` |
| No inputs (T14) | `test_task_without_inputs_submits_directly`, `test_empty_inputs_produce_a_no_op_stage_script` |
| CWL and FAIR (T17) | `test_cwl_export_is_independent_of_pre_stage`, `test_fair_records_pre_stage_metadata_without_paths`, a path-free metadata assertion |
| RemoteSlurm MRO and constructor, non-default port (T18) | `test_pre_stage_survives_the_multiple_inheritance_constructor`, `test_remote_example_with_loopback_ssh`; one `sbatch` per task asserted |
| Prolonged queue (T16) | Not testable without a real queue; the filesystem requirement is documented |
| Cleanup | Failure tests assert that staged data and markers are kept and not deleted; garbage collection is unchanged and covered by the existing suites |

## 6. Documentation and tutorial updates

The new guide is `docs/scheduler_prestaging.md`, linked from `README.md`, `docs/README.md`, and each affected guide. Lesson 14 gained a learning outcome, a conceptual paragraph, run commands, expected results, a controlled experiment that includes the 200 × 1800 s / 3600 core-hour exercise, diagnosis, and scientific-practice notes. The notebook gained a pre-staging section with `run_example`/`run_tests` cells and a deterministic core-hour assertion, inside the Lesson 14 block. The validator's 19-lesson structure is unchanged. I audited `docs/getting_started.md` and found no statement made obsolete. The repository has no changelog convention, so none was added.

## 7. CI/CD changes

- `quality`: ruff and mypy now cover `dagon/prestage.py`, `tools/ci_prestage_slurm.py`, and the new examples.
- `test`, `rocky-linux`, `raspberry-pi`: the new test modules run through the existing `unittest discover`, and `pre_stage_mock.py` runs through `tools/run_local_examples.py`.
- `beeond-slurm`, renamed in display to "BeeOND and pre-staging on Slurm (emulated site)" (the job id is unchanged, so `needs:` still works): it runs the pre-staging unit tests, `tools/ci_prestage_slurm.py --partition ci`, and `pre_stage_local.py --partition ci`. On failure it collects the stage-in scripts and markers.
- No jobs were removed. `development` is still a trigger. Release automation is untouched.

## 8. Known limitations

1. **No production validation.** There is no multi-node, production-scale, or real-queue evidence. The CI cluster is a single node with an empty queue, so it shows ordering and gating, not queue-time effects.
2. **Shared-scratch visibility cannot be verified before submission.** The compute-side check catches a missing or empty scratch at job start, after the allocation is granted. It cannot detect a different copy of the same files at the same path.
3. **User-command quoting (legacy parser).** A `workflow://` reference ends at a space and is substituted unquoted. Scratch paths with spaces break the user command, although staging succeeds. A trailing `;` must be separated by a space.
4. **The legacy launcher keeps historical weaknesses**, intentionally byte-identical: an unquoted `cd`, transfer failures not reflected in `code`, and `eval` of expanded paths. Only `context.sh` was fixed, because it runs in both modes.
5. **BeeOND and parallel mode are ineligible** (future work).
6. **`StagerMover.SLURM`** copy jobs need the default `sbatch --export=ALL` to see `file`/`dst`. Their exit status is not checked; the final verification is what detects missing data.
7. **GridFTP and SKYCDS** transfer while DAGonStar plans staging, and their destination layout must match the verified paths. These movers were not exercised here.
8. **Timing.** `allocation_wait_seconds` and `execution_seconds` have one-second resolution and rely on synchronised clocks between the submission host and the compute nodes. `scheduler_wall_seconds` includes the queue wait.
9. **Dry run** still runs `context.sh` and creates the scratch directory, as the legacy dry run does.
10. **Pre-existing, not caused by this change.** A full-suite run once left untracked `ssh_key`/`ssh_key.pub` files in the repository root (created by an existing test's context script). The new tests do not create them (checked), and I moved the files to the scratchpad. Ruff reports pre-existing issues in `dagon/stager/base.py` and the legacy Slurm demos, which are outside the CI ruff targets.

## 9. Remaining HPC-cluster validation

- Push the branch and confirm that the `beeond-slurm` CI job passes, especially `tools/ci_prestage_slurm.py` and `pre_stage_local.py` with real `sbatch`.
- On a production site, with authorisation: run `pre_stage_local.py --scratch <shared> --cores <N>` and `--legacy` with a representative input size. Confirm the `staging finished <= allocation started` evidence, and that `sacct` shows the job's start after stage-in.
- Run `pre_stage_remote.py` against a real login node (key handling, `create_file` over SSH, remote `sbatch`), including a non-default port.
- Confirm the shared, persistent scratch assumption for each site's file systems. Test a deliberately node-local path to observe the compute-side failure message.
- Exercise the SCP, GridFTP, and `StagerMover.SLURM` movers in pre-staged mode where they are used.

## 10. Commit history

```text
4c971a5 Document the compute-side visibility check and quoting fixes
025525e Harden pre-staging against injection and non-shared scratch
1170792 Document scheduler-aware pre-staging
531c7bf Check scheduler-aware pre-staging in CI
91b9251 Add pre-staging examples for mock, local and remote Slurm
5a13076 Test scheduler-aware pre-staging with mock Slurm and SSH
3c94ee7 Add scheduler-aware pre-staging for Slurm and RemoteSlurm
```

The diff against `development` (`d8da197`) touches 37 files, with about 3,190 insertions and 105 deletions before this report. This report is committed separately.
