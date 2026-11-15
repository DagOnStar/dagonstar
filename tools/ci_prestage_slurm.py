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
  before anything is staged or submitted;
* ``stager``: an explicit ``pre_stage=True`` with ``StagerMover.SLURM`` (whose
  copy jobs are scheduler submissions) is rejected before anything runs;
* ``checkpoint``: a completed pre-staged task is reused when its input is
  unchanged and runs again, with the new input, when the producer's output
  changed after the checkpoint was written;
* ``traversal``: a ``workflow://`` reference with a ``..`` component fails in
  the staging phase without any transfer or submission;
* ``dry``: a dry run creates no scratch directory and submits nothing;
* ``mutation``: a staged input changed after stage-in but before the job
  starts is detected by the compute launcher, and the command never runs;
* ``lock``: a stage-in lock held by another run blocks stage-in and
  submission without touching that run's data, and a finished run releases
  its own lock;
* ``owner``: when the lock's owner token cannot be written (injected with
  ``umask 0277`` in the generated stage-in script), stage-in gives the new
  lock back and stops before removing earlier inputs or submitting.  Skipped
  when run as root, whom file permissions do not bind;
* ``cancelled``: a job held pending with ``--begin`` and cancelled with
  ``scancel`` (``sbatch -W`` then exits 0 on Slurm 23.11) is an execution
  failure, never a completed task, and its checkpoint is not reusable.

A single-node cluster cannot show queue-time effects; this is ordering and
gating evidence only.  The script exits non-zero when any check fails.
"""
import argparse
import calendar
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dagon import Workflow  # noqa: E402
from dagon.prestage import PreStageConfigurationError  # noqa: E402
from dagon.batch import Slurm  # noqa: E402
from dagon.prestage import COMPUTE_RECORD_NAME, LOCK_NAME, MARKER_NAME, PreparedTask  # noqa: E402
from dagon.stager.base import StagerMover  # noqa: E402
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
        ("order: job identifier from sbatch --parsable", str(metadata.get("scheduler_job_id") or "").isdigit(),
         json.dumps(metadata)),
        ("order: staged content compared with its source",
         [item.get("integrity") for item in marker.get("inputs", [])] == ["content"], str(marker_text)),
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


def scenario_stager(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-prestage-stager", config=site_config(scratch, partition))
    task = DagonTask(TaskType.SLURM, "copyjobs", "true", partition=partition, pre_stage=True)
    task.set_stager_mover(StagerMover.SLURM)
    try:
        workflow.add_task(task)
        rejected, detail = False, "accepted"
    except PreStageConfigurationError as exc:
        rejected, detail = True, str(exc)
    return [
        ("stager: explicit pre_stage with StagerMover.SLURM is rejected",
         rejected and "StagerMover.SLURM" in detail, detail),
        ("stager: nothing was staged or submitted", task.working_dir is None, str(task.working_dir)),
    ]


def scenario_checkpoint(scratch: str, partition: Optional[str]) -> List[Check]:
    checkpoint = os.path.join(scratch, "ci-prestage-checkpoint.json")

    def build():
        workflow, producer, consumer = two_tasks("ci-prestage-checkpoint", scratch, partition, True,
                                                 "seq 1 7 > data.txt")
        workflow.checkpoint_file = checkpoint
        return workflow, producer, consumer

    workflow, producer, first = build()
    error = run(workflow)
    workflow, _producer, unchanged = build()
    try:
        workflow.run(resume_checkpoint_file=checkpoint)
        resume_error = None
    except Exception as exc:  # reported as a check failure
        resume_error = exc
    if producer.working_dir is not None and os.path.isdir(producer.working_dir):
        with open(os.path.join(producer.working_dir, "data.txt"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write("".join("%d\n" % number for number in range(1, 10)))
    workflow, _producer, changed = build()
    try:
        workflow.run(resume_checkpoint_file=checkpoint)
        changed_error = None
    except Exception as exc:  # reported as a check failure
        changed_error = exc
    return [
        ("checkpoint: first run", error is None and first.status.name == "FINISHED", repr(error)),
        ("checkpoint: unchanged input is reused",
         resume_error is None and unchanged.fair_checkpoint_reused, repr(resume_error)),
        ("checkpoint: changed input runs the task again",
         changed_error is None and not changed.fair_checkpoint_reused and changed.status.name == "FINISHED",
         "%r %s" % (changed_error, changed.status.name)),
        ("checkpoint: the new run used the changed input",
         (read(changed.working_dir, "lines.txt") or "").strip() == "9", str(read(changed.working_dir, "lines.txt"))),
    ]


def scenario_traversal(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-prestage-traversal", config=site_config(scratch, partition), pre_stage=True)
    producer = DagonTask(TaskType.SLURM, "produce", "seq 1 7 > data.txt", partition=partition, ntasks=1)
    consumer = DagonTask(TaskType.SLURM, "consume", "cat workflow:///produce/../../outside.txt",
                         partition=partition, ntasks=1)
    workflow.add_task(producer)
    workflow.add_task(consumer)
    run(workflow)
    return [
        ("traversal: consumer failed in staging",
         consumer.status.name == "FAILED" and consumer.failure_phase == "staging",
         "%s %s" % (consumer.status.name, consumer.failure_phase)),
        ("traversal: no stage-in script", read(consumer.working_dir, ".dagon", "stage_in.sh") is None, ""),
        ("traversal: no compute launcher was submitted", read(consumer.working_dir, ".dagon", "launcher.sh") is None,
         ""),
    ]


def scenario_dry(scratch: str, partition: Optional[str]) -> List[Check]:
    base = os.path.join(scratch, "dry-run-scratch")
    workflow, producer, consumer = two_tasks("ci-prestage-dry", base, partition, True, "seq 1 7 > data.txt")
    workflow.set_dry(True)
    error = run(workflow)
    return [
        ("dry: workflow ran", error is None, repr(error)),
        ("dry: no scratch directory was created", not os.path.exists(base), base),
        ("dry: no working directory assigned", producer.working_dir is None and consumer.working_dir is None,
         "%s %s" % (producer.working_dir, consumer.working_dir)),
    ]


def scenario_mutation(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow, _producer, consumer = two_tasks("ci-prestage-mutation", scratch, partition, True, "seq 1 7 > data.txt")
    original = Slurm.on_execute

    def change_while_queued(task, script, script_name):
        if task is consumer and script_name == "launcher.sh":
            # Stage-in has verified and recorded the input; change it before sbatch.
            staged = os.path.join(task.working_dir, ".dagon", "inputs", workflow.name, "produce", "data.txt")
            with open(staged, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("".join("%d\n" % number for number in range(1, 8)).replace("7", "8"))
        return original(task, script, script_name)

    Slurm.on_execute = change_while_queued  # type: ignore[assignment]
    try:
        run(workflow)
    finally:
        Slurm.on_execute = original  # type: ignore[assignment]
    metadata = consumer.get_execution_metadata().get("pre_stage", {})
    return [
        ("mutation: consumer failed in execution",
         consumer.status.name == "FAILED" and consumer.failure_phase == "execution",
         "%s %s" % (consumer.status.name, consumer.failure_phase)),
        ("mutation: the job was accepted (job identifier)", str(metadata.get("scheduler_job_id") or "").isdigit(),
         json.dumps(metadata)),
        ("mutation: the command never ran", read(consumer.working_dir, "job_started_at") is None, ""),
    ]


def scenario_lock(scratch: str, partition: Optional[str]) -> List[Check]:
    held_dir = os.path.join(scratch, "ci-prestage-lock-held")
    lock = os.path.join(held_dir, ".dagon", LOCK_NAME)
    os.makedirs(lock, exist_ok=True)
    with open(os.path.join(lock, "owner"), "w", encoding="utf-8", newline="\n") as stream:
        stream.write("another-run\n")
    workflow = Workflow("ci-prestage-lock", config=site_config(scratch, partition), pre_stage=True)
    producer = DagonTask(TaskType.SLURM, "produce", "seq 1 7 > data.txt", partition=partition, ntasks=1)
    blocked = DagonTask(TaskType.SLURM, "consume", JOB, partition=partition, ntasks=1, working_dir=held_dir)
    workflow.add_task(producer)
    workflow.add_task(blocked)
    run(workflow)
    released_workflow, _producer, finished = two_tasks("ci-prestage-lock-free", scratch, partition, True,
                                                       "seq 1 7 > data.txt")
    error = run(released_workflow)
    return [
        ("lock: blocked task failed in staging",
         blocked.status.name == "FAILED" and blocked.failure_phase == "staging",
         "%s %s" % (blocked.status.name, blocked.failure_phase)),
        ("lock: no compute launcher was submitted", read(held_dir, ".dagon", "launcher.sh") is None, ""),
        ("lock: the other run's lock was left in place", (read(lock, "owner") or "").strip() == "another-run", ""),
        ("lock: a finished run released its own lock",
         error is None and finished.status.name == "FINISHED"
         and not os.path.exists(os.path.join(str(finished.working_dir), ".dagon", LOCK_NAME)),
         "%r %s" % (error, finished.status.name)),
    ]


def scenario_owner(scratch: str, partition: Optional[str]) -> List[Check]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("owner: skipped (file permissions do not bind root)", flush=True)
        return []
    # Seed what an earlier attempt would have left; it must survive.
    consumer_dir = os.path.join(scratch, "ci-prestage-owner-consume")
    workflow = Workflow("ci-prestage-owner", config=site_config(scratch, partition), pre_stage=True)
    producer = DagonTask(TaskType.SLURM, "produce", "seq 1 7 > data.txt", partition=partition, ntasks=1)
    consumer = DagonTask(TaskType.SLURM, "consume", JOB, partition=partition, ntasks=1, working_dir=consumer_dir)
    workflow.add_task(producer)
    workflow.add_task(consumer)
    earlier = os.path.join(consumer_dir, ".dagon", "inputs", "earlier.txt")
    os.makedirs(os.path.dirname(earlier), exist_ok=True)
    with open(earlier, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("earlier\n")
    original = PreparedTask.stage_in_script

    def unwritable_owner(prepared, lock_token=None):
        script = original(prepared, lock_token)
        if os.path.normpath(prepared.working_dir) != os.path.normpath(consumer_dir):
            return script
        first, _newline, rest = script.partition("\n")
        return first + "\numask 0277\n" + rest  # the lock directory is created read-only

    PreparedTask.stage_in_script = unwritable_owner  # type: ignore[method-assign]
    try:
        run(workflow)
    finally:
        PreparedTask.stage_in_script = original  # type: ignore[method-assign]
    return [
        ("owner: consumer failed in staging",
         consumer.status.name == "FAILED" and consumer.failure_phase == "staging",
         "%s %s" % (consumer.status.name, consumer.failure_phase)),
        ("owner: no ownerless lock was left", not os.path.exists(os.path.join(consumer_dir, ".dagon", LOCK_NAME)),
         ""),
        ("owner: earlier inputs were not removed and nothing was submitted",
         read(earlier) == "earlier\n" and read(consumer_dir, ".dagon", "launcher.sh") is None
         and read(consumer_dir, ".dagon", MARKER_NAME) is None, ""),
    ]


def scenario_cancelled(scratch: str, partition: Optional[str]) -> List[Check]:
    name = "ci-prestage-cancelled-%d" % os.getpid()
    workflow = Workflow("ci-prestage-cancelled", config=site_config(scratch, partition), pre_stage=True)
    producer = DagonTask(TaskType.SLURM, "produce", "seq 1 7 > data.txt", partition=partition, ntasks=1)
    consumer = DagonTask(TaskType.SLURM, name, JOB, partition=partition, ntasks=1,
                         sbatch_options=["--begin=now+600"])
    workflow.add_task(producer)
    workflow.add_task(consumer)
    cancelled: Dict[str, str] = {}

    def cancel_when_pending() -> None:
        deadline = time.time() + 180
        while time.time() < deadline:
            job = subprocess.run(["squeue", "-h", "-t", "PD", "-n", name, "-o", "%i"],
                                 capture_output=True, text=True).stdout.strip()
            if job:
                subprocess.run(["scancel", job], check=False)
                cancelled["job"] = job
                return
            time.sleep(2)

    watcher = threading.Thread(target=cancel_when_pending, daemon=True)
    watcher.start()
    run(workflow)
    watcher.join(timeout=5)
    metadata = consumer.get_execution_metadata().get("pre_stage", {})
    checkpoint = workflow.checkpoints.get(consumer.checkpoint_key(), {})
    return [
        ("cancelled: the pending job was cancelled", bool(cancelled.get("job")), json.dumps(cancelled)),
        ("cancelled: an execution failure, not a completed task",
         consumer.status.name == "FAILED" and consumer.failure_phase == "execution"
         and str(metadata.get("scheduler_job_id")) == cancelled.get("job"),
         "%s %s %s" % (consumer.status.name, consumer.failure_phase, metadata.get("scheduler_job_id"))),
        ("cancelled: no completion record, checkpoint not reusable, command never ran",
         not (read(consumer.working_dir, ".dagon", COMPUTE_RECORD_NAME) or "").strip()
         and checkpoint.get("code") != 0
         and read(consumer.working_dir, "job_started_at") is None, json.dumps(checkpoint.get("code"))),
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
        for scenario in (scenario_order, scenario_legacy, scenario_gate, scenario_beeond, scenario_stager,
                         scenario_checkpoint, scenario_traversal, scenario_dry, scenario_mutation, scenario_lock,
                         scenario_owner, scenario_cancelled):
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
