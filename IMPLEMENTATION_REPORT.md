# Implementation report: scheduler-aware pre-staging

- **Branch:** `feature/scheduler-aware-prestaging`, based on `development` at `d8da197`. At the user's request, `8dec028` was pushed to `origin/feature/scheduler-aware-prestaging` and `development` was fast-forwarded to it (no merge commit; `development` had not moved since `d8da197`). No PR; `main` is untouched. The post-audit work in [section 3](#post-audit-deep-validation-d-001-and-d-002) (version 2.9.4, D-001, D-002, the deep site check) was pushed to `development` at `ab4cf0d` at the user's request. The remote feature branch has since been deleted.
- **Inputs:** `DAGonStar_Claude_Code_Implementation_Plan.md` (the plan) and `AGENTS.md`. There is no `CLAUDE.md` in the repository. Prepared for review against `DAGonStar_Codex_Independent_Audit_Plan.md`.
- **Audit remediation:** the first independent audit (verdict FAIL at `2d0d69a`) reported six findings, F-001 to F-006, addressed in [section 2](#2-audit-remediation). The repeat audit (`AUDIT_REPORT_SCHEDULER_PRESTAGING.md`, verdict FAIL) confirmed F-001 to F-005 resolved and F-006 substantially resolved, and reported three new findings, R-001 to R-003, addressed in [section 3](#3-repeat-audit-remediation). The second repeat audit (verdict NEEDS-EVIDENCE at `14b8698`) confirmed R-001 to R-003 resolved and left one medium finding, M-001, and one failed CI job (Windows / Python 3.10). Both are addressed in [section 3](#second-repeat-audit-m-001-and-ci). The third repeat audit (verdict NEEDS-EVIDENCE at `75856b3`) confirmed M-001 resolved and the Windows diagnosis consistent, and reported one low finding, L-001 (this report's file inventory still listed 41 harness checks), now corrected. Its remaining condition, a green CI run on the pushed commit, was met by run 43568759582 on `8dec028`. The fifth repeat audit, at `e887d2e`, gave the verdict **PASS** with no open findings. A deeper production-cluster test after that audit found one new high-severity defect, D-001 (a job cancelled while pending was reported as completed), and, while fixing it, an NFS visibility issue, D-002. Both are fixed and recorded in [section 3](#post-audit-deep-validation-d-001-and-d-002). CI run [43579136060](https://github.com/DagOnStar/dagonstar/actions/runs/43579136060) on `ab4cf0d` passed every job; the fixes have not been independently audited yet.
- **Environment:** macOS 26.6.2 (arm64), Python 3.12.10, GNU bash 3.2.57, ruff 0.17.3, mypy 2.4.1.
- **Version:** `setup.cfg` sets the package version to **2.9.4**. That is above the latest GitHub release, `v2.0.2` (whose `setup.cfg` still said 1.0.2), and the latest PyPI release, 1.0.2. No tag was created.
- **Real-cluster validation: manual runs on one production cluster.** At the user's request, the final code was run on a production Slurm 23.11.3 cluster (RHEL 8 family, login node plus CPU compute nodes, `/home` on NFS shared by all nodes, partition `norm-wn`, Python 3.11 in a dedicated virtual environment). After the M-001 fix, the 44-check harness `tools/ci_prestage_slurm.py`, `pre_stage_local.py` in both lifecycles, and `pre_stage_remote.py` over real SSH from this workstation all passed again, and the 86 pre-staging unit tests passed on the cluster's Linux login node (details in [section 7](#7-test-results)). That is evidence for one site and Slurm release, with small inputs on a nearly idle partition, not a general guarantee. CI run [43568759582](https://github.com/DagOnStar/dagonstar/actions/runs/43568759582) on the push of `8dec028` to `development` passed every job (see [section 9](#9-cicd-changes)).

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
- **Gate.** No scheduler submission of any kind happens before stage-in has succeeded. In particular, `sbatch` is never called when stage-in fails or cannot be confirmed, and `StagerMover.SLURM`, which submits copy jobs, is ineligible. A submission is treated as completed only when `sbatch --parsable` printed a job identifier.
- **Integrity.** For inputs whose source is readable on the submission host (same-host `COPY` and `LINK`), the staged tree is compared with the source file by file (names, POSIX `cksum` CRC, and size). Other movers are checked for existence only at stage-in, and this is stated as such. For every input, the compute launcher re-checks the staged content against the listing recorded at stage-in before the command runs, so a change while the job is queued stops the job.
- **Concurrency.** Tasks of one workflow that share a fixed working directory are ineligible. A token-owned lock (`.dagon/stage-in.lock`, created atomically with `mkdir`) is held from stage-in until `sbatch` returns, so a concurrent run in another process cannot replace the inputs. Taking it is fail-atomic: if the owner token cannot be written and read back, `stage_in.sh` removes the new lock and exits 1 before it removes or transfers anything.
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

## 3. Repeat-audit remediation

| ID | Severity | Finding | Resolution | Regression evidence |
|---|---|---|---|---|
| R-001 | High | `sbatch` exiting 0 without a parsable job identifier was accepted as completion (`COMPLETED`, checkpoint `code` 0, `scheduler_job_id` `None`) | `Task._submit_pre_staged` requires a job identifier for every claimed success. Exit 0 without one sets the checkpoint `code` to 1, sets the phase to `FAILED` and `failure_phase` to `submission`, and raises `SchedulerSubmissionError` ("returned success without a job identifier"). The task is never reused as completed | `test_success_without_a_job_identifier_is_never_completed` (empty output, `Submitted batch job 7`, a warning line, `7 jobs`), `test_remote_success_without_job_identifier_fails` (over the SSH double); real-cluster `order` scenario recorded a numeric job identifier from `--parsable -W` |
| R-002 | High | The compute launcher checked only existence, so content changed while the job was queued reached the payload | After verification, `stage_in.sh` writes `.dagon/stage-in-destinations.txt`, the `cksum` listing of every staged destination, whatever the mover. Its SHA-256 is recorded in the marker as `destination_identity_sha256`. Before the prologue and the command, the compute launcher recomputes the listing and exits with "staged inputs changed between stage-in and the start of the job" on any difference, including a missing record | `test_staged_input_changed_while_queued_never_reaches_the_command` (same-size rewrite, truncation, removal; the command never runs), `test_stage_in_lock_is_released_after_the_job` (marker field); real-cluster `mutation` scenario: the job started on a compute node, the guard fired (message in `slurm-<id>.out`), and the command never ran |
| R-003 | High | Two tasks sharing one fixed `working_dir` could delete each other's marker, records, and inputs | Within a workflow, a shared working directory on the same host (normalised path) makes the task ineligible (`Task.shared_working_dir_task`). An explicit `pre_stage=True` is refused at `Workflow.add_task`; an inherited default falls back to legacy with a warning. Across processes, `stage_in.sh` takes `.dagon/stage-in.lock` with `mkdir` before it removes or writes anything, and exits 75 if the lock is held. The task then fails in staging with `stage_in_lock_busy` and nothing is submitted. DAGonStar releases only a lock whose `owner` token matches its own random per-run token, after `sbatch` returns or stage-in fails (local `shutil.rmtree`; remote token-checked `rm -rf` over SSH) | `test_shared_working_directory_is_not_eligible` (explicit, inherited, different host), `test_another_runs_lock_blocks_stage_in_without_touching_its_data`, `test_lock_is_released_when_staging_fails`, `test_stage_in_lock_is_released_after_the_job`, `test_remote_lock_is_released_over_ssh`; real-cluster `lock` scenario |

Status of the original findings, as confirmed by the repeat audit and unchanged since: F-001 to F-005 resolved, and F-006 now fully resolved by R-001.

Real-cluster observations relevant to these fixes:

- Slurm accounting storage is disabled on the cluster (`AccountingStorageType = (null)`), so `sacct` could not list jobs.
- Instead, the job output files were counted. Every task that reached `sbatch` left exactly one `slurm-<id>.out`. The refused tasks (the `gate`, `traversal`, and `lock` scenarios) left none, and no output file mentions a `stagein` copy job.

### Post-audit deep validation (D-001 and D-002)

After the fifth repeat audit's PASS, the user asked for a deeper test on the production cluster. The new manual tool `tools/hpc_prestage_deep.py` exercises what the harness cannot: large and many-file inputs, a two-node allocation, real pending states induced with `--begin`, a change and a cancellation while pending, two processes contending for one working directory, node-local scratch, and RemoteSlurm checkpoint re-verification over real SSH. Its first full run passed 24 of 26 checks. The two failures exposed D-001.

| ID | Severity | Finding | Resolution | Regression evidence |
|---|---|---|---|---|
| D-001 | High | On Slurm 23.11.3, `sbatch -W` exits 0 and prints the job identifier for a job cancelled while still pending. A probe job showed `JobState=CANCELLED`, `ExitCode=0:0`, and `sbatch exit=0`. DAGonStar took exit 0 plus a job identifier as completion: the task was `FINISHED` with checkpoint `code` 0 although its command never ran, and a resumed run reused it. The legacy lifecycle has the same weakness | The compute launcher sets an `EXIT` trap, before the guards and the command, that writes `.dagon/compute-finished.txt` as `<SLURM_JOB_ID> <exit status>` however the launcher ends. After `sbatch` exits 0 with a job identifier, `Task._compute_completion_problem()` reads the record (up to five attempts, one second apart) and `compute_record_problem()` accepts it only if it names that job with status 0. Otherwise the task fails in the `execution` phase ("returned success, but the job left no completion record"), the checkpoint `code` is set to 1, and `compute_completion_confirmed` is absent from the metadata. `PRE_STAGE_POLICY_VERSION` becomes 3, so version-2 checkpoints, which may record such false successes, are not reused. The legacy launcher is unchanged (byte-for-byte fixture), so legacy tasks keep the weakness; this is documented | `test_compute_record_must_name_the_job_and_status_zero`, `test_job_cancelled_before_it_started_is_never_completed` (with a stale record from an earlier attempt present), `test_remote_job_cancelled_before_it_started_is_never_completed`, record assertions in `test_inputs_are_staged_before_submission` (`4242 0`) and the queued-change test (`4242 1`, the trap ran on the guard's exit). The two cancellation tests fail with the check disabled. New harness scenario `cancelled` (3 checks): real `--begin` plus `scancel`. Deep `cancel` scenario: execution failure with the cancelled job's identifier, lock released, resumed run rerun and completed |
| D-002 | High (found while fixing D-001) | The first version of the fix removed the record in `stage_in.sh` with `rm -f`. On the cluster's NFS v4.2 `/home`, the login node then cached the file as absent: a file created on a compute node stayed invisible to the login node for more than five seconds, while an existing file rewritten from a compute node was visible at once (direct probe). Every short pre-staged job was therefore reported as never having run: the harness passed 24 of 47 checks, the deep check 10 of 26, and `pre_stage_local.py --legacy` failed (its pre-staged producers). Only jobs longer than the cache lifetime passed | `stage_in.sh` now empties the record (`: > .dagon/compute-finished.txt \|\| exit 1`) instead of removing it, so the job overwrites an existing file and the controller's next open sees the new content. An empty record still counts as "never ran", and an earlier attempt's record is emptied before anything is staged | `test_completion_record_is_emptied_and_written_by_an_exit_trap` (generated text: emptied, not in any `rm` line, before staging; trap before the command). On the cluster after the change: harness 47/47, deep check 26/26, both local lifecycles `Verification: ok`, and RemoteSlurm (record read with `cat` over SSH) `compute_completion_confirmed: true` |

Deep-check measurements on the production cluster (one run each unless stated; Slurm 23.11.3, partition `norm-wn`, two idle 32-core nodes, NFS v4.2 `/home`):

| Scenario | Observation |
|---|---|
| `volume` (1 GiB file and 5,000 small files, same-host `cp -r`) | Both inputs content-verified at stage-in; the job's checksum of the large file matched the producer's; all 5,000 files seen. Stage-in on the login node took 43 to 103 s across five runs (46 to 52 s in the last three). The consumer's job ran 18 s (Slurm `RunTime`) with pre-staging and 10 s in the legacy lifecycle |
| `multinode` | `--nodes=2 --ntasks-per-node=1`: `srun` on both compute nodes saw byte-identical staged content |
| `queue` | `squeue` showed the job pending with reason `BeginTime`; allocation wait 66, 98, and 81 s in three runs; the job read its staged input |
| `queued-change` | An input changed while the job was pending stopped the job at start (execution failure with that job's identifier); the command never ran |
| `cancel` | Before D-001: reported completed. After: execution failure with the cancelled job's identifier, lock released, resumed run staged again and completed |
| `contention` | A second process using the working directory of a first, whose job was pending, failed in staging as lock-busy and left the first run's lock and data untouched; the first completed with its own input |
| `node-local` | Scratch on the login node's local `/tmp`: stage-in succeeded, the job failed in the execution phase, and the command never ran |
| `remote-checkpoint` (from this workstation over real SSH) | First run completed; an unchanged input was reused after identity re-verification over SSH; a changed producer output ran the task again with the new input |

The volume timing does not support the core-hour estimate on this site. Pre-staging lengthened the consumer's allocation by about 8 s, because the job re-reads every staged input at start (the R-002 check, which includes 5,000 small files). The legacy job copied the same data inside its allocation in about 10 s in total. Under these conditions, `estimated_allocated_core_hours_saved`, computed from the 46 to 52 s of login-node staging, overstates the saving. `docs/scheduler_prestaging.md` (Motivation) and the README status now say so. Timings come from single runs on an otherwise idle partition. `sbatch -W` returns on its own polling schedule (42 s for both consumers), so its duration cannot resolve the allocated time; the tool reads `RunTime` from `scontrol show job`.

### Second repeat audit (M-001 and CI)

| ID | Severity | Finding | Resolution | Regression evidence |
|---|---|---|---|---|
| M-001 | Medium | After the atomic `mkdir` that takes the stage-in lock, `echo <token> > owner` was unchecked. The script has no `set -e`, so a failed write let staging continue and left an ownerless lock that the token-checked release could never remove | `PreparedTask.stage_in_script` now writes the token and reads it back (`head -n 1`). If either fails, it removes the lock directory it has just created, prints "could not record the stage-in lock owner … nothing was staged", and exits 1. This happens before the marker, records, or earlier inputs are removed and before any transfer. The task fails in the `staging` phase, `stage_in_lock_busy` stays unset, and `sbatch` is never called | `test_lock_owner_write_failure_gives_the_lock_back_before_staging` (local: earlier inputs and marker survive, no lock left, no submission) and `test_remote_lock_owner_write_failure_stops_before_sbatch` (over the SSH double: no `sbatch`, no lock). The failure is injected by prepending `umask 0277` to the generated script, so `mkdir` succeeds but the owner write is refused. Both tests fail against the unguarded script and pass with the guard. They are skipped on Windows and as root, where file permissions do not bind. New harness scenario `owner` (3 checks) |
| CI | Required platform | Run 43549373340 at `14b8698`: `Windows / Python 3.10` failed in `test_inputs_are_staged_before_submission` with `AssertionError: 3 != 2` (252 tests, 1 failure, 29 skipped). The emulated-Slurm job and the other 11 jobs passed, including `Windows / Python 3.13` on the same commit | The assertion counts the mock `sbatch` log. Concurrent mock-`sbatch` processes appended to one JSON-lines file, and on Windows concurrent appends can lose a record. That is a race in the test double, not in DAGonStar. `examples/dataflow/slurm/mock_scheduler.py` now writes each record to its own file in `<log>.d/` with an atomic `os.replace`, and `read_log` reads them back in time order. The production code did not change for this | Local full suite and `pre_stage_mock.py` pass. Confirming the fix on Windows requires a new CI run, which needs the branch pushed |

## 4. Files

### Created

| File | Purpose |
|---|---|
| `dagon/prestage.py` | Policy validation, `PreparedTask`, `StageInput` (with integrity level), stage-in script and compute launcher renderers, content-comparison and identity helpers, reference validation, marker document, `TaskPhase`, error hierarchy, core-hour estimate |
| `docs/scheduler_prestaging.md` | Dedicated guide (motivation, 200-core example, lifecycles, inheritance table, eligibility, filesystem requirements, recipes, generated files, verification and integrity, failure table, retries/checkpoints, dry run, events/metrics, CWL, security, evidence, FAQ/migration) |
| `examples/dataflow/slurm/mock_scheduler.py` | Deterministic `sbatch -W` stand-in that logs submission-time observations (one atomically written file per record, safe for concurrent submissions) and honours `--parsable` |
| `examples/dataflow/slurm/pre_stage_mock.py` | Scheduler-free coastal-forecast workflow, legacy vs pre-staged, with assertions (`Verification: ok`) |
| `examples/dataflow/slurm/pre_stage_local.py` | Same workflow on a real local Slurm installation, with ordering evidence |
| `examples/dataflow/slurm/pre_stage_remote.py` | Same workflow on RemoteSlurm over SSH; no embedded hosts or credentials |
| `tests/test_scheduler_prestaging.py` | 73 local tests (configuration, generation, lifecycle order, strict stager, content identity, mock-`sbatch` integration, checkpoints, dry run, queue-time changes, locking including a failed owner write, the completion record and a job cancelled while pending, examples) |
| `tests/test_remote_scheduler_prestaging.py` | 17 RemoteSlurm tests with a loopback SSH double |
| `tests/fixtures/legacy_slurm_launcher.sh` | Legacy launcher captured from the unmodified `development` code |
| `tools/ci_prestage_slurm.py` | Live-Slurm harness (12 scenarios: order, legacy, gate, beeond, stager, checkpoint, traversal, dry, mutation, lock, owner, cancelled; 47 checks, or 44 when run as root, which skips `owner`) |
| `tools/hpc_prestage_deep.py` | Manual site-validation tool, not run in CI: volume, multinode, queue, queued-change, cancel, contention, node-local (26 checks on the login node), and remote-checkpoint over real SSH (4 checks); prints measured timings |
| `IMPLEMENTATION_REPORT.md` | This report |

### Modified

| File | Change |
|---|---|
| `dagon/task.py` | `pre_stage`/`pre_stage_capable` class attributes; resolution and validation, including the `StagerMover.SLURM` refusal; `discover_context`, `build_stage_plan` (integrity level per input; reference validation in strict mode), and `prepare_task` (refactor of `pre_process_command`, which now renders `legacy_launcher()`); `execute` split into `execute_legacy`, `execute_pre_staged` (with `_submit_pre_staged` and the stage-in lock lifecycle), and the side-effect-free `plan_pre_staged_dry_run`; identity recording and `validate_pre_staged_checkpoint` in `reuse_checkpoint`; `parsable_job_id` failure classification, with a job identifier required for success; shared-working-directory ineligibility; metrics, phases, and typed failures; quoted `cd` in `context.sh` |
| `dagon/batch.py` | `Slurm`/`RemoteSlurm` accept `pre_stage` (last keyword); `pre_stage_capable = True`; `run_on_submission_host`, `run_stage_in`, `run_identity_check` (no file written), `release_stage_lock` (token-checked), `write_stage_marker` (atomic: local `os.replace`, remote temporary file plus `mv`), `read_scratch_file`, `requested_cores`; `--parsable` for pre-staged submissions only; BeeOND ineligibility; `pre_stage` in JSON and execution metadata |
| `dagon/__init__.py` | `Workflow(pre_stage=False)`; `add_task` validates explicit overrides, including a working directory shared with an existing task; JSON round trip (key emitted only when enabled) |
| `dagon/stager/base.py` | `strict` mode for `stage_in`/`generate_command`: failure propagation, IFS-newline space safety, single-quoted `eval` template. `Stager.last_data_mover` records the chosen mover. The legacy text is unchanged |
| `tests/helpers.py` | Canned context script (no network), scratch config, mock-scheduler loader |
| `.github/workflows/ci.yml` | Ruff and mypy targets; the `beeond-slurm` job runs the pre-staging unit tests, `tools/ci_prestage_slurm.py`, and `pre_stage_local.py`; failure log collection |
| `tools/run_local_examples.py` | Adds `pre_stage_mock.py` |
| `README.md` | Feature list, status assessment, examples list, docs index, troubleshooting |
| `AGENTS.md` | Important path, CI note, "Scheduler-aware pre-staging maintenance" rules (now also: no scheduler submission of any kind before stage-in, content verification, checkpoint re-verification, side-effect-free dry run, `..` refusal, `--parsable` classification) |
| `docs/README.md`, `architecture.md`, `reference_guide.md`, `user_guide.md`, `configuration.md`, `developer_guide.md`, `checkpoints.md`, `fair_principles.md`, `cwl_export.md`, `tasktype_interoperability.md`, `beeond.md`, `platform_support.md`, `examples/dataflow_slurm.md` | Lifecycle, API, configuration, extension points (`run_identity_check`), restart semantics, metrics, CWL boundary, backend matrix, BeeOND limitation, CI description |
| `docs/tutorial/lesson_14_submit_a_task_through_slurm.md`, `DAGonStar_tutorial.ipynb`, `resources/glossary.md`, `resources/troubleshooting.md` | Lesson 14 section, controlled experiment and diagnosis; notebook section, exercise and verification cells (still 19 lessons) |
| `examples/dataflow/slurm/README.md` | Demos 5 to 7 with prerequisites and commands |

## 5. Architectural decisions

1. **Structured plan instead of text splitting.** `Task.prepare_task()` returns a `PreparedTask` with the header, prologue, stage blocks (one per reference), invocation, manifest, and resolved command. All three scripts (legacy launcher, `stage_in.sh`, compute launcher) are rendered from it, so each input is staged exactly once in each mode.
2. **One planning pass per execution.** Some movers have side effects while DAGonStar plans staging: SCP key exchange, an immediate local-to-remote SCP, GridFTP, and SKYCDS. The plan is therefore built once, in strict mode when pre-staging. Those transfers keep their semantics and still finish before `sbatch`. They run on the submission host, never as scheduler jobs.
3. **Same nonallocated route as `context.sh`.** `stage_in.sh` runs through `run_on_submission_host`: local bash for `Slurm`, SSH `create_file` plus `bash` for `RemoteSlurm`.
4. **Capability-based eligibility.** Eligibility comes from `pre_stage_capable` and `pre_stage_unsupported_reason()`, never from the type name. Explicit unsupported requests raise, both at `add_task` and again before scratch creation. An inherited default on an ineligible task keeps the legacy lifecycle, so a mixed workflow can enable the default without failing its Docker, Native, and other tasks.
5. **No scheduler use before stage-in (F-001).** Rejecting `StagerMover.SLURM` was chosen over a redesign. A scheduler-assisted stage-in would be a different contract (copy jobs consume allocations and need job-exit tracking), so it stays out of scope rather than being presented as pre-staging.
6. **Strict mode inside the existing stager**, rather than a second staging implementation. The legacy loop does not report a failed `cp` through `$?`, because the trailing `if` resets it. This was kept for compatibility, and strict mode fixes it for pre-staging only.
7. **Integrity matched to what can be substantiated (F-003).** Content is compared only where both trees are readable by the stage-in script. POSIX `cksum` was chosen because it exists on Linux, macOS, and Git Bash, unlike `sha256sum` or `shasum`. Its CRC detects accidental corruption, not tampering, and the documentation says so. Existence-only inputs are labelled, not presented as verified.
8. **Content identity, not timestamps (F-002).** The identity is a hash of names, CRCs, and sizes, recomputed against the producers' current directories. A producer that reruns with identical content does not invalidate its consumers; any content change does. When re-verification is impossible, the safe default is to rerun.
9. **Marker written by Python after a verified exit 0** (atomic). `stage_in.sh` removes any old marker, identity record, and staged inputs first. The marker is provenance, never a skip token.
10. **Structured submission evidence (F-006, R-001).** `--parsable` is added only to pre-staged submissions, so the legacy submit command is unchanged. Completion requires the job identifier; an exit status alone is not evidence that the scheduler accepted and ran the job.
11. **Compute-side visibility check.** A non-shared scratch cannot be detected before submission. The compute launcher therefore fails fast if the marker or an input is not visible, before the prologue and the command run.
12. **Public `Status` unchanged.** Internal `TaskPhase` (`PREPARING`, `STAGING`, `STAGED`, `SUBMITTED`, `COMPLETED`, `FAILED`) is separate, and `RUNNING` keeps its meaning.
13. **Events.** In pre-staged mode, `on_task_staging_in_start/end` bracket context discovery, planning, and the actual transfer. Legacy timing is unchanged and documented.
14. **Two identities (R-002).** The source identity serves checkpoint re-verification and covers only sources readable on the submission host. The destination identity covers every staged copy and is checked by the compute launcher. Re-reading inputs inside the allocation costs some allocated time, but it is a local scratch read, not a transfer, and it is the only point at which queue-time changes can be detected.
15. **Reject within a workflow, lock across processes (R-003).** Duplicate directories in one workflow are a configuration error and are refused deterministically. Cross-process collisions cannot be detected at configuration time, so a `mkdir` lock with an owner token guards them. Rerunning a killed run requires removing its stale lock by hand, which is safer than guessing whether the holder is still alive.

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

## 6. API changes (all additive, positional order preserved)

- `Workflow(..., portable_emulation=False, pre_stage=False)`, plus the attribute `workflow.pre_stage`.
- `Slurm(..., beeond=None, pre_stage=None)` and `RemoteSlurm(..., ssh_port=22, pre_stage=None)`; also works through `DagonTask(TaskType.SLURM, ..., pre_stage=...)`.
- `Task` additions:
  - Methods: `resolve_pre_stage()`, `validate_pre_stage_declaration(workflow=None)`, `pre_stage_unsupported_reason()`, `shared_working_dir_task(workflow=None)`, `prepare_task()`, `discover_context()`, `build_stage_plan()`, `execute_pre_staged()`, `plan_pre_staged_dry_run()`, `execute_legacy()`, `validate_pre_staged_checkpoint()`, `pre_stage_metadata()`.
  - Attributes: `pre_stage_phase`, `pre_stage_metrics`, `prepared_task`, `failure_phase`, `pre_stage_submission`.
  - Backend hooks: `run_stage_in`, `run_identity_check`, `release_stage_lock`, `write_stage_marker`, `read_scratch_file`, `requested_cores`.
- `dagon.task.parsable_job_id()`.
- `Stager.stage_in(..., strict=False)`, `Stager.generate_command(..., strict=False)`, and `Stager.last_data_mover`.
- New module `dagon.prestage`, including `validate_reference_path`, `identity_script`, `identity_digest`, `destination_identity_body`, `lock_release_script`, `compute_record_problem`, `COMPUTE_RECORD_NAME`, `IDENTITY_NAME`, `DESTINATION_IDENTITY_NAME`, `LOCK_NAME`, `LOCK_BUSY_EXIT`, `INTEGRITY_CONTENT`, and `INTEGRITY_EXISTENCE`. `PreparedTask.stage_in_script(lock_token=None)` takes the lock only when given a token. `PRE_STAGE_POLICY_VERSION` is 3 (2 before D-001), and the marker schema is `dagonstar.stage-in-marker/2`.
- JSON: workflow `pre_stage` (only when `True`) and task `pre_stage` (only when not `None`). `get_execution_metadata()["pre_stage"]` and FAIR `execution.pre_stage` appear only when pre-staging is configured. They gain `inputs_content_verified`, `scheduler_job_id`, `compute_completion_confirmed`, `dry_run`, and `stage_in_lock_busy`, and remain path-free. CWL output is unchanged and independent of `pre_stage` (tested).
- `pre_process_command()` keeps its signature and output.

## 7. Test results

The latest results, after the D-001 and D-002 fixes and the version change to 2.9.4:

| Where | Command | Result |
|---|---|---|
| Workstation | `python3 -m unittest discover -s tests` | **258 tests, OK** (168 existing + 90 pre-staging) |
| Workstation | `python3 tools/run_local_examples.py`; `tools/validate_tutorial.py`; required `py_compile`; CI ruff targets (now including `tools/hpc_prestage_deep.py`); CI mypy targets; `git diff --check` | 18/18; 19 lessons and links; OK; all passed; no issues; clean |
| Workstation | `python3 -m pip install -e .` | installed `dagonstar` 2.9.4 |
| Cluster | `tools/ci_prestage_slurm.py --partition norm-wn` (real `sbatch`) | **47 passed, 0 failed**, including `cancelled`. Census: 21 task directories, 16 `slurm-*.out` files (17 submitted tasks, one cancelled before it started, so no output), no output in the four refused tasks, no `stagein` copy job |
| Cluster | `tools/hpc_prestage_deep.py --partition norm-wn --size-mib 1024` | **26 passed, 0 failed** |
| Workstation to cluster | `tools/hpc_prestage_deep.py --remote-scratch ... --host ... --partition norm-wn` (real SSH) | **4 passed, 0 failed** |
| Cluster | `python -m unittest tests.test_scheduler_prestaging tests.test_remote_scheduler_prestaging` | 90 tests, OK |
| Cluster | `pre_stage_local.py --cores 2` and `--legacy` | both `Verification: ok` |
| Workstation to cluster | `pre_stage_remote.py` over real SSH | `Verification: ok`, `policy_version: 3`, `compute_completion_confirmed: true` (job 19037) |

The tables below record the earlier rounds. The first block ran on this workstation after the second-repeat-audit fixes (M-001 and the mock-log race); the second ran on the production cluster.

| Command | Result |
|---|---|
| Baseline before any change: `python3 -m unittest discover -s tests` | 168 tests, OK |
| `python3 -m unittest discover -s tests -v` | **254 tests, OK, 0 skipped** on macOS (168 existing + 86 pre-staging), after the M-001 fix |
| `python3 tools/run_local_examples.py` (with `PYTHONPATH=$PWD`) | 18/18 examples passed, including `pre_stage_mock.py` |
| `python3 tools/validate_tutorial.py`; notebook JSON load | Validated 19 canonical lessons and internal tutorial links; notebook is valid JSON |
| `python3 -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py dagon/stager/*.py` | OK |
| `ruff check` on the CI-targeted files | All checks passed |
| `mypy --follow-imports=skip` on the CI-typed modules, including `dagon/prestage.py` | No issues (local mypy 2.4 needed `--python-version 3.10`; CI pins mypy 1.13) |
| `ruff check --select F` on `dagon/task.py`, `dagon/batch.py`, `dagon/stager/base.py` (outside the CI targets) | 6 findings, all pre-existing in `development`; none introduced by this work |
| `git diff --check` (working tree) | Clean |
| `git diff --check development...HEAD` | Five trailing-whitespace lines, all in `tests/fixtures/legacy_slurm_launcher.sh`, intentional (byte-identical legacy launcher) |
| `tools/ci_prestage_slurm.py` against the mock `sbatch` (scratch script, not CI) | 44 passed, 0 failed (11 scenarios) |

On the production cluster (Slurm 23.11.3, partition `norm-wn`, scratch under the NFS-shared `/home`, Python 3.11.7 venv with the base dependencies, code synced from this working tree):

| Command | Result |
|---|---|
| `python tools/ci_prestage_slurm.py --scratch <home>/... --partition norm-wn` (real `sbatch`) | **44 passed, 0 failed**: order (including `--parsable` job identifier and content verification), legacy, gate, beeond, stager, checkpoint (unchanged reused, changed rerun), traversal, dry, mutation (guard fired on the compute node; command never ran), lock, and owner (on NFS, the injected owner-write failure produced the new message, left no lock, kept the earlier inputs, and submitted nothing). Run as an unprivileged user. The earlier run at `14b8698` passed the first 41 checks |
| `pre_stage_local.py --scratch <home>/... --partition norm-wn --cores 2` and `--legacy` | Both `Verification: ok`; stage-in finished 1 s before the allocation started the launcher; job identifier recorded |
| `pre_stage_remote.py --host <cluster> --user <user> --key <key> --remote-scratch <home>/... --partition norm-wn`, run from this workstation over real SSH (paramiko) | `Verification: ok`; stage-in on the login host completed before the remote `sbatch --parsable`; `inputs_content_verified: 2` |
| `python -m unittest tests.test_scheduler_prestaging tests.test_remote_scheduler_prestaging` on the Linux login node | 86 tests, OK |
| Job-output census of the harness scratch directory (run at `14b8698`) | 14 `slurm-*.out` files for 17 task directories: one per submitted task, none for the three refused tasks, none for a `stagein` copy job |

All cluster rows above were run on the code as committed for the second repeat audit, synced from this working tree; the remote example recorded job identifier 18931.

For the third repeat audit (no code change; only this report changed), the harness and unit tests were rerun on the cluster against the audited commit `75856b3`: **44 passed, 0 failed**, and 86 unit tests OK. Job-output census of that harness run: 19 task directories, 15 `slurm-*.out` files (exactly one per submitted task), no output in the four refused tasks (`gate`, `traversal`, `lock`, `owner`), and no `stagein` copy job.

Expected skips on other platforms: `tests/test_remote_scheduler_prestaging.py` (the loopback SSH host is POSIX) and the metacharacter-path test are skipped on Windows, and the symbolic-link part of `test_copy_link_and_corruption` is skipped there. All other new tests are cross-platform.

### Coverage against the requested scenarios and the audit's T01–T18

| Scenario | Test(s) |
|---|---|
| Legacy default unchanged (T07) | `test_legacy_launcher_is_byte_for_byte_unchanged`, `test_default_keeps_staging_inside_the_launcher`, `test_legacy_run_stages_inside_the_job`, `test_legacy_remote_slurm_is_unchanged`, `test_default_json_is_unchanged`, `test_pre_staged_submission_uses_parsable_output` (legacy submit has no `--parsable`), plus all 168 existing tests |
| Inheritance and overrides (T05, T06) | `test_resolution_matrix`, `test_inheritance_follows_later_workflow_changes`, `test_task_opt_out_keeps_legacy_launcher`, `test_inherited_and_explicit_pre_stage_stage_before_submission` |
| Invalid values, positional API | `test_invalid_values_are_rejected`, `test_positional_api_is_unchanged` |
| Success without job identifier (T04) | `test_success_without_a_job_identifier_is_never_completed`, `test_remote_success_without_job_identifier_fails` |
| Queue-time changes (T16 by source trace) and node-local scratch (T08) | `test_staged_input_changed_while_queued_never_reaches_the_command`, real-cluster `mutation` scenario; a different copy at the same path is now caught if its content differs from what was staged |
| Same-destination concurrency (T15) | `test_shared_working_directory_is_not_eligible`, `test_another_runs_lock_blocks_stage_in_without_touching_its_data`, `test_lock_is_released_when_staging_fails`, `test_stage_in_lock_is_released_after_the_job`, `test_remote_lock_is_released_over_ssh`, `test_lock_owner_write_failure_gives_the_lock_back_before_staging`, `test_remote_lock_owner_write_failure_stops_before_sbatch`, real-cluster `lock` and `owner` scenarios |
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
| Prolonged queue (T16) | Content changes during the queue are detected at job start (above); an actual long queue wait was not observed (the cluster partition was nearly idle) |
| Cleanup | Failure tests assert that staged data and markers are kept after submission or execution failures; earlier staged inputs are discarded at the next stage-in; garbage collection is unchanged and covered by the existing suites |

## 8. Documentation and tutorial updates

The guide is `docs/scheduler_prestaging.md`, linked from `README.md`, `docs/README.md`, and each affected guide. For the audit fixes it gained a "Verification and integrity" section. The eligibility, generated-files, failure, checkpoint, dry-run, metrics, security, and evidence sections were rewritten to match the new behaviour. `checkpoints.md`, `tasktype_interoperability.md`, `user_guide.md`, `configuration.md`, `developer_guide.md`, `architecture.md`, `fair_principles.md`, `platform_support.md`, `README.md` (including the project-status assessment), `AGENTS.md`, the Slurm example README, Lesson 14, the notebook's pre-staging cells, and the troubleshooting table were updated accordingly. For the repeat audit, the guide gained "Changes while the job is queued" and "Concurrent runs" sections, new rows for the destination record, the lock, the lock-busy failure, and a successful exit without a job identifier, and a record of the production-cluster evidence. `AGENTS.md`, `developer_guide.md` (`release_stage_lock`), `architecture.md`, `platform_support.md`, `user_guide.md`, `README.md`, Lesson 14, the troubleshooting table, and the Slurm example README were updated to match. For the second repeat audit, the guide's "Concurrent runs" section, its generated-files and failure tables, and its evidence table describe the fail-atomic lock; `AGENTS.md` gained the matching rule; Lesson 14, the troubleshooting table, and the README status section name the new message. The validator's 19-lesson structure is unchanged. The repository has no changelog convention, so none was added.

## 9. CI/CD changes

- `quality`: ruff and mypy cover `dagon/prestage.py`, `tools/ci_prestage_slurm.py`, and the new examples. Ruff also covers `tools/hpc_prestage_deep.py` (added after the fifth audit).
- `test`, `rocky-linux`, `raspberry-pi`: the new test modules run through the existing `unittest discover`, and `pre_stage_mock.py` runs through `tools/run_local_examples.py`.
- `beeond-slurm`, renamed in display to "BeeOND and pre-staging on Slurm (emulated site)" (the job id is unchanged, so `needs:` still works): it runs the pre-staging unit tests, `tools/ci_prestage_slurm.py --partition ci`, and `pre_stage_local.py --partition ci`. On failure it collects the stage-in scripts and markers. The harness now also covers `--parsable` job identifiers, content verification, the `StagerMover.SLURM` rejection, changed-input checkpoint invalidation, `..` refusal, the side-effect-free dry run, a change while queued (`mutation`), the stage-in lock (`lock`), and a failed lock-owner write (`owner`, skipped as root; the CI job runs as the unprivileged runner user): 11 scenarios, 44 checks. After the fifth audit, the `cancelled` scenario (D-001) brings this to 12 scenarios and 47 checks.
- Run [43579136060](https://github.com/DagOnStar/dagonstar/actions/runs/43579136060) (push to `development` at `ab4cf0d`, version 2.9.4): **all 14 build and test jobs passed**. In the emulated-Slurm job: 90 pre-staging unit tests OK, the harness reported "47 passed, 0 failed" including the three `cancelled` checks (real `--begin` plus `scancel`), and `pre_stage_local.py` printed `Verification: ok`. `Windows / Python 3.10` ran 258 tests (32 skipped), OK. Release and PyPI jobs were skipped (no tag).
- No jobs were removed. `development` is still a trigger. Release automation is untouched.
- Run [43549373340](https://github.com/DagOnStar/dagonstar/actions/runs/43549373340) (`workflow_dispatch` at `14b8698`): 12 of 13 jobs passed, including "BeeOND and pre-staging on Slurm (emulated site)" (pre-staging unit tests, 41-check harness, `pre_stage_local.py`). `Windows / Python 3.10` failed on the mock-log race described in [section 3](#second-repeat-audit-m-001-and-ci). The fix was confirmed by the next run, below.
- Run [43568759582](https://github.com/DagOnStar/dagonstar/actions/runs/43568759582) (push to `development` at `8dec028`): **all 14 build and test jobs passed**, on Ubuntu (3.10, 3.12, 3.13), Ubuntu 24.04 (3.8), macOS (3.10, 3.13), Windows (3.10, 3.13), Rocky Linux 9 (3.9, 3.12), and Debian bookworm arm64, plus Quality, Build distributions, and "BeeOND and pre-staging on Slurm (emulated site)". In that job: 86 pre-staging unit tests OK, the harness reported "44 passed, 0 failed" including the three `owner` checks, and `pre_stage_local.py` printed `Verification: ok`. `Windows / Python 3.10` ran 254 tests (31 skipped), OK, including `test_inputs_are_staged_before_submission`. The release and PyPI jobs were skipped, as they are for non-tag pushes.

## 10. Known limitations

1. **Limited production validation.** Manual runs on one production cluster (Slurm 23.11.3, NFS-shared `/home`, nearly idle partition), including the deep check: inputs up to 1 GiB plus 5,000 files, two nodes, and induced pending states of about 1 to 2 minutes. There is no evidence for a busy queue with competing users, multi-terabyte transfers, other Slurm releases, site `sbatch` wrappers, or parallel file systems such as Lustre or GPFS. The CI single-node Slurm job passed on `8dec028` (run 43568759582).
2. **`--parsable` with `-W`** printed the job identifier on the first line and then waited, on Slurm 23.11.3. Other releases and site wrappers are not verified.
3. **Integrity is CRC-based and partial.** `cksum` detects accidental corruption, not tampering. `SCP`, `GRIDFTP`, and `SKYCDS` inputs are existence-only. Content verification and checkpoint re-verification read every input once more on the submission host (I/O proportional to input size).
4. **Checkpoint reuse is conservative.** A completed task with any existence-only input is never reused: it is staged and submitted again on resume. Checkpoints written under another policy version (now 3) are not reused. Legacy (non-pre-staged) checkpoints are still reused without input validation, as before.
5. **Shared-scratch visibility cannot be verified before submission.** The compute-side check catches missing, empty, or different staged content at job start, after the allocation is granted. Content checks use CRCs stored in the same scratch directory, so they detect accidental changes, not tampering. Re-reading the inputs at job start uses allocated time: on the production cluster it made a 1 GiB plus 5,000-file consumer run 18 s instead of the legacy 10 s, so the core-hour estimate can overstate the saving (see [section 3](#post-audit-deep-validation-d-001-and-d-002)).
6. **User-command quoting (legacy parser).** A `workflow://` reference ends at a space and is substituted unquoted. Scratch paths with spaces break the user command, although staging succeeds. A trailing `;` must be separated by a space.
7. **The legacy lifecycle keeps historical weaknesses**, intentionally byte-identical: an unquoted `cd` in the launcher, transfer failures not reflected in `code`, `eval` of expanded paths, and an unchecked `workflow://` parser that accepts `..` (F-004 is fixed for pre-staging only). Only `context.sh` was fixed in both modes.
8. **BeeOND, parallel mode, and `StagerMover.SLURM` are ineligible** (future work, if ever, under a separately designed contract).
9. **Dry-run plans are approximate.** Because a pre-staged dry run skips context discovery, it shows placeholders for unassigned directories and does not report the mover or integrity levels.
10. **Locks and cancellation.** A run killed during stage-in or while its job is queued leaves `.dagon/stage-in.lock` behind (a failed owner write no longer does); a later run then fails in staging until the lock is removed by hand (the message says so). A job cancelled while pending is an execution failure (D-001) and is tested; cancellation during stage-in is not otherwise handled or tested. A legacy (non-pre-staged) Slurm task whose job is cancelled while pending is still reported as finished, because the legacy launcher is kept byte for byte. Shared working directories are detected within one workflow and between processes on the same file system, but the lock relies on atomic `mkdir`, which is not atomic on every network file system configuration.
11. **Timing.** `allocation_wait_seconds` and `execution_seconds` have one-second resolution and rely on synchronised clocks between the submission host and the compute nodes. `scheduler_wall_seconds` includes the queue wait.
12. **Completion record and shared file systems.** The controller re-reads `.dagon/compute-finished.txt` for up to five seconds. Because `stage_in.sh` creates it empty and the job overwrites it, NFS shows the job's write on the next open. A file system without close-to-open consistency could still delay it beyond that, which would make a finished job fail as "never ran" (the safe direction).
13. **Pre-existing, not caused by this change.** A full-suite run once left untracked `ssh_key`/`ssh_key.pub` files in the repository root (created by an existing test's context script); I moved them to the scratchpad. Ruff reports pre-existing issues in `dagon/stager/base.py`, `dagon/task.py`, `dagon/batch.py`, and the legacy Slurm demos, all outside the CI ruff targets.

## 11. Remaining HPC-cluster validation

- Done: CI run 43568759582 on the pushed commit `8dec028` is fully green, including `Windows / Python 3.10` and the emulated-Slurm job with all eleven harness scenarios (the third repeat audit's only merge-blocking item).
- Done: CI run 43579136060 on `ab4cf0d` is green, including the 47-check harness with `cancelled`. Still open: an independent audit of the D-001 and D-002 fixes.
- Performance follow-up (general, not site-specific): stage-in reads a content-verified input up to five times (copy, comparison of both sides, then both records), where computing each side's checksum once would remove two full reads; `dagon_tree_digest` starts one `cksum` per file, which is slow for many small files both on the login node and inside the allocation; and `estimated_allocated_core_hours_saved` ignores the compute-side re-check, so it should subtract a measured re-check time or be labelled an upper bound.
- Done on one production cluster: the harness, both local lifecycles, `pre_stage_remote.py` over real SSH, a 1 GiB plus 5,000-file input, a two-node job, induced queue waits, a change and a cancellation while pending, process contention, node-local scratch, and checkpoint re-verification over real SSH. Still open: a busy partition with competing users, multi-terabyte inputs, a site with Slurm accounting enabled (to confirm with `sacct` that no job other than the compute job ran), a non-default SSH port, and other Slurm releases (whether `sbatch -W` also exits 0 for cancelled pending jobs).
- Confirm the shared, persistent scratch assumption for each site's file systems, including how quickly the submission host sees a rewritten file.
- Repeat the volume comparison with several runs, larger inputs, and a slower path into the allocation, to find where pre-staging saves allocated time; consider a cheaper compute-side check for many small files (it runs one `cksum` per file). Measure the cost of content verification for representative input sizes on the login node, and exercise the SCP and GridFTP movers (existence-only) in pre-staged mode where they are used.

## 12. Commit history

```text
(this commit) Record the green CI run for version 2.9.4
ab4cf0d Update the implementation report for the deep validation and version 2.9.4
70ef6bb Set the package version to 2.9.4
534f0e5 Require a completion record before treating a job as finished (D-001, D-002)
e887d2e Record the green CI run on development
8dec028 Correct the report inventory for the third repeat audit (L-001)
75856b3 Update the implementation report for the second repeat audit
d78d9a8 Make taking the stage-in lock fail-atomic (M-001)
674590b Make the mock sbatch log safe for concurrent writers
14b8698 Record the repeat-audit commits in the implementation report
fc840d1 Fix the repeat-audit findings R-001 to R-003 and record cluster evidence
22881f6 Check queue-time changes and the stage-in lock in the Slurm harness
1e3893d Fix the repeat-audit findings in scheduler-aware pre-staging
fb4b8d6 Record the audit-fix commits in the implementation report
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
