# Tutorial troubleshooting

Run commands from the repository root and use the same interpreter for installation and execution: `python -m pip ...` and `python ...`.

| Symptom | Diagnostic evidence | Safe response |
|---|---|---|
| `ModuleNotFoundError: dagon` | `python -m pip show dagonstar` | Activate the intended environment and install editable source. |
| Missing producer | Inspect the exact `workflow://` workflow, task, and path segments | Correct the logical identifier; do not substitute a host-specific path. |
| Cycle error | Print each task's `prevs` and `nexts` after dependency construction | Remove or redesign the erroneous causal edge. |
| Missing scientific output | Use the task's printed `working_dir`; inspect its `.dagon` launcher and captures | Fix the task command or environment. |
| Checkpoint does not reuse | Inspect checkpoint `_scratch_dir` and preserved task directories | Invalidate deliberately or restore the exact recorded context. |
| Docker/SSH/Slurm failure | Separate graph validation, command generation, service availability, and live execution | Follow site policy; never embed credentials or disable trust checks casually. |
| Pre-staged Slurm task fails before any job appears | Read `task.failure_phase` (`staging`, `submission`, `execution`) and `.dagon/stage_in.sh`; a missing producer output is the usual staging cause; "staged content differs from its source" means a transfer wrote wrong or partial data; a `..` in a `workflow://` reference is refused; "another pre-staged run holds the stage-in lock" means a concurrent run uses the same working directory, or a killed run left `.dagon/stage-in.lock` behind; "could not record the stage-in lock owner" means the owner token could not be written (often a full or read-only file system), and the new lock was removed; "staged inputs changed between stage-in and the start of the job" is an execution failure caused by changes while queued; "returned success, but the job left no completion record" means the job never ran its launcher, usually because it was cancelled while pending | Confirm the scratch directory is shared and persistent; BeeOND tasks and `StagerMover.SLURM` cannot pre-stage. |
| Local web/LLM mock cannot bind | Inspect the socket error and host policy | Run on a host that permits loopback sockets; do not substitute a public endpoint merely to finish the lesson. |
| CWL JSON parses but validation fails | Run an available CWL v1.2 validator and inspect the reported field | Treat parsing and standards validation as different levels of evidence. |

Tutorial scripts use temporary directories and therefore clean their artifacts on success. Copy an example and select a persistent scratch directory when extended inspection is required.
