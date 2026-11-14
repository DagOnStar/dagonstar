"""Scheduler-aware pre-staging check against a live Slurm cluster (CI helper).

Usage (from the repository root, on a host where ``sbatch`` works)::

    python tools/ci_prestage_slurm.py [--scratch DIR] [--partition NAME]

The CI job ``beeond-slurm`` runs it on the single-node Slurm cluster set up by
``tools/ci/slurm/setup-slurm-beeond.sh``.  The scenarios are:

* ``order``: a pre-staged task's stage-in finishes, and its completion marker
  exists, before the allocation starts running the compute launcher; the job
  itself observes its inputs already on scratch when it starts;
* ``legacy``: the same task without pre-staging stages inside the job (no
  stage-in script or marker is written) and produces the same result;
* ``gate``: a failed stage-in (missing producer output) leaves no compute
  launcher and therefore never reached ``sbatch``;
* ``beeond``: an explicit ``pre_stage=True`` together with BeeOND is rejected
  before anything is staged or submitted.

A single-node cluster cannot show queue-time effects; this is ordering and
gating evidence only.  The script exits non-zero when any check fails.
"""
import argparse
import calendar
import json
import os
import sys
import tempfile
import time
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dagon import Workflow  # noqa: E402
from dagon.prestage import PreStageConfigurationError  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

Check = Tuple[str, bool, str]

# The job records, as its first action, its start time and whether the staged
# input is already present (the reference is rewritten to the staged path).
JOB = ("date +%s > job_started_at; staged=workflow:///produce/data.txt ; "
       "if [ -f \"$staged\" ]; then echo present; else echo absent; fi > input_at_start; "
       "wc -l < \"$staged\" > lines.txt")


def site_config(scratch: str, partition: Optional[str]) -> Dict[str, Dict[str, str]]:
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": partition or ""},
        "beeond": {"comment": "beeond-fs"},
    }


def read(*parts: Optional[str]) -> Optional[str]:
    if any(part is None for part in parts):
        return None
    filepath = os.path.join(*[str(part) for part in parts])
    if not os.path.isfile(filepath):
        return None
    with open(filepath, encoding="utf-8") as stream:
        return stream.read()


def two_tasks(name: str, scratch: str, partition: Optional[str], pre_stage: bool, produce: str):
    workflow = Workflow(name, config=site_config(scratch, partition), pre_stage=pre_stage)
    producer = DagonTask(TaskType.SLURM, "produce", produce, partition=partition, ntasks=1)
    consumer = DagonTask(TaskType.SLURM, "consume", JOB, partition=partition, ntasks=1)
    workflow.add_task(producer)
    workflow.add_task(consumer)
    return workflow, producer, consumer


def run(workflow: Workflow) -> Optional[BaseException]:
    try:
        workflow.run()
    except Exception as exc:  # reported as a check failure
        return exc
    return None


def scenario_order(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow, _producer, consumer = two_tasks("ci-prestage-order", scratch, partition, True, "seq 1 7 > data.txt")
    error = run(workflow)
    marker_text = read(consumer.working_dir, ".dagon", "stage-in-complete.json")
    marker = json.loads(marker_text) if marker_text else {}
    finished = (calendar.timegm(time.strptime(marker["staging_finished_at"], "%Y-%m-%dT%H:%M:%SZ"))
                if marker else None)
    started = (read(consumer.working_dir, "job_started_at") or "").strip()
    started_epoch = int(started) if started.isdigit() else None
    metadata = consumer.get_execution_metadata().get("pre_stage", {})
    return [
        ("order: workflow ran", error is None, repr(error)),
        ("order: task finished", consumer.status.name == "FINISHED", consumer.status.name),
        ("order: stage-in script written", read(consumer.working_dir, ".dagon", "stage_in.sh") is not None, ""),
        ("order: completion marker written", bool(marker), str(marker_text)),
        ("order: staging finished before the job started",
         finished is not None and started_epoch is not None and started_epoch >= finished,
         "finished=%s started=%s" % (finished, started_epoch)),
        ("order: input present when the job started",
         (read(consumer.working_dir, "input_at_start") or "").strip() == "present",
         str(read(consumer.working_dir, "input_at_start"))),
        ("order: result", (read(consumer.working_dir, "lines.txt") or "").strip() == "7",
         str(read(consumer.working_dir, "lines.txt"))),
        ("order: metadata phase", metadata.get("phase") == "COMPLETED", json.dumps(metadata)),
    ]


def scenario_legacy(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow, _producer, consumer = two_tasks("ci-prestage-legacy", scratch, partition, False, "seq 1 7 > data.txt")
    error = run(workflow)
    return [
        ("legacy: workflow ran", error is None, repr(error)),
        ("legacy: task finished", consumer.status.name == "FINISHED", consumer.status.name),
        ("legacy: no stage-in script", read(consumer.working_dir, ".dagon", "stage_in.sh") is None, ""),
        ("legacy: no completion marker", read(consumer.working_dir, ".dagon", "stage-in-complete.json") is None, ""),
        ("legacy: input staged inside the job",
         (read(consumer.working_dir, "input_at_start") or "").strip() == "present",
         str(read(consumer.working_dir, "input_at_start"))),
        ("legacy: same result", (read(consumer.working_dir, "lines.txt") or "").strip() == "7",
         str(read(consumer.working_dir, "lines.txt"))),
    ]


def scenario_gate(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow, producer, consumer = two_tasks("ci-prestage-gate", scratch, partition, True, "true")
    run(workflow)
    return [
        ("gate: producer finished", producer.status.name == "FINISHED", producer.status.name),
        ("gate: consumer failed in staging",
         consumer.status.name == "FAILED" and consumer.failure_phase == "staging",
         "%s %s" % (consumer.status.name, consumer.failure_phase)),
        ("gate: no compute launcher was submitted", read(consumer.working_dir, ".dagon", "launcher.sh") is None, ""),
        ("gate: no completion marker", read(consumer.working_dir, ".dagon", "stage-in-complete.json") is None, ""),
    ]


def scenario_beeond(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-prestage-beeond", config=site_config(scratch, partition))
    task = DagonTask(TaskType.SLURM, "fast", "true", partition=partition, beeond="task", pre_stage=True)
    try:
        workflow.add_task(task)
        rejected, detail = False, "accepted"
    except PreStageConfigurationError as exc:
        rejected, detail = True, str(exc)
    return [
        ("beeond: explicit pre_stage with BeeOND is rejected", rejected and "BeeOND" in detail, detail),
        ("beeond: nothing was staged or submitted", task.working_dir is None, str(task.working_dir)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="shared scratch directory (default: temporary)")
    parser.add_argument("--partition", default=None)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dagon-prestage-ci-") as temporary:
        scratch = os.path.abspath(args.scratch or temporary)
        os.makedirs(scratch, exist_ok=True)
        checks: List[Check] = []
        for scenario in (scenario_order, scenario_legacy, scenario_gate, scenario_beeond):
            print("== %s" % scenario.__name__, flush=True)
            checks.extend(scenario(scratch, args.partition))
    failed = 0
    for name, ok, detail in checks:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else " -> " + detail))
        failed += 0 if ok else 1
    print("Pre-staging Slurm checks: %d passed, %d failed" % (len(checks) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
