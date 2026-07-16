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
| Local web/LLM mock cannot bind | Inspect the socket error and host policy | Run on a host that permits loopback sockets; do not substitute a public endpoint merely to finish the lesson. |
| CWL JSON parses but validation fails | Run an available CWL v1.2 validator and inspect the reported field | Treat parsing and standards validation as different levels of evidence. |

Tutorial scripts use temporary directories and therefore clean their artifacts on success. Copy an example and select a persistent scratch directory when extended inspection is required.
