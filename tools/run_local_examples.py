"""Run the self-contained local examples as a cross-platform smoke test.

Usage (from the repository root)::

    python tools/run_local_examples.py

Every listed example uses only local processes, temporary scratch directories,
and loopback mock services; none needs ``dagon.ini``, credentials, Docker, SSH,
Slurm, or network access beyond ``127.0.0.1`` (``pre_stage_mock.py`` and the
Lesson 23 and 25 scripts replace ``sbatch`` with a local mock scheduler; the
infrastructure lessons mock their Docker, Kubernetes, Nomad, SSH, and cloud
clients, and the agentic examples use the deterministic ``mock`` adapter).
The script exits non-zero when any example fails and prints the tail of its
output.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXAMPLES = [
    "examples/tutorial/lesson_00_environment_check.py",
    "examples/tutorial/lesson_01_first_local_task.py",
    "examples/tutorial/lesson_02_build_a_dag.py",
    "examples/tutorial/lesson_03_workflow_data_dependencies.py",
    "examples/tutorial/lesson_04_validate_and_fix_cycles.py",
    "examples/tutorial/lesson_05_scratch_launchers_and_logs.py",
    "examples/tutorial/lesson_06_data_staging.py",
    "examples/tutorial/lesson_07_checkpoint_and_resume.py",
    "examples/tutorial/lesson_08_asynchronous_execution.py",
    "examples/tutorial/lesson_09_native_python_tasks.py",
    "examples/tutorial/lesson_10_web_tasks.py",
    "examples/tutorial/lesson_11_llm_tasks.py",
    "examples/tutorial/lesson_12_faas_tasks.py",
    "examples/tutorial/lesson_13_iot_tasks.py",
    "examples/tutorial/lesson_14_agentic_specification.py",
    "examples/tutorial/lesson_15_agentic_tools_and_guardrails.py",
    "examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py",
    "examples/tutorial/lesson_17_docker_tasks.py",
    "examples/tutorial/lesson_18_apptainer_tasks.py",
    "examples/tutorial/lesson_19_kubernetes_tasks.py",
    "examples/tutorial/lesson_20_nomad_tasks.py",
    "examples/tutorial/lesson_21_ssh_remote_tasks.py",
    "examples/tutorial/lesson_22_cloud_tasks.py",
    "examples/tutorial/lesson_23_slurm_tasks.py",
    "examples/tutorial/lesson_24_beeond_storage.py",
    "examples/tutorial/lesson_25_scheduler_prestaging.py",
    "examples/tutorial/lesson_26_data_movers.py",
    "examples/tutorial/lesson_27_fair_by_design.py",
    "examples/tutorial/lesson_28_meta_workflows.py",
    "examples/tutorial/lesson_29_cwl_export.py",
    "examples/tutorial/lesson_30_compute_continuum.py",
    "examples/tutorial/lesson_31_operations.py",
    "examples/tutorial/lesson_32_capstone.py",
    "examples/fair/fair_local.py",
    "examples/faas/mock_sync.py",
    "examples/faas/local_http.py",
    "examples/iot/observe_mock.py",
    "examples/llm/local_mock_llm.py",
    "examples/dataflow/slurm/beeond_local_emulation.py",
    "examples/adhoc/portable.py",
    "examples/adhoc/custom_adapter.py",
    "examples/adhoc/streaming.py",
    "examples/cwl/export_streaming_workflow.py",
    "examples/cwl/export_meta_workflow.py",
    "examples/meta/meta_workflow_local.py",
    "examples/dataflow/slurm/pre_stage_mock.py",
    "examples/agentic/tool_free.py",
    "examples/agentic/guarded_repair.py",
    "examples/agentic/evaluation_failure.py",
    "examples/agentic/checkpoint_identity.py",
    "examples/agentic/mixed_workflow.py",
    "examples/agentic/cwl_local.py",
]


def main() -> int:
    environment = dict(os.environ)
    paths = [str(ROOT)] + [item for item in environment.get("PYTHONPATH", "").split(os.pathsep) if item]
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    failures = []
    for relative in EXAMPLES:
        started = time.time()
        with tempfile.TemporaryDirectory(prefix="dagon-example-") as cwd:
            completed = subprocess.run([sys.executable, str(ROOT / relative)], cwd=cwd, env=environment,
                                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        status = "ok" if completed.returncode == 0 else "FAILED (%d)" % completed.returncode
        print("%-60s %s  %.1fs" % (relative, status, time.time() - started), flush=True)
        if completed.returncode:
            failures.append(relative)
            tail = (completed.stdout + completed.stderr).strip().splitlines()[-25:]
            print("\n".join("    " + line for line in tail), flush=True)
    print("%d/%d examples passed" % (len(EXAMPLES) - len(failures), len(EXAMPLES)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
