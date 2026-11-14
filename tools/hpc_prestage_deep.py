"""Deeper scheduler-aware pre-staging validation on a real Slurm site (manual tool).

This is not part of CI.  It submits real jobs, some of which stay queued on
purpose for a minute or more, so run it only where you are authorised to and
on a partition where that is acceptable.

On the cluster's login (submission) node::

    python tools/hpc_prestage_deep.py --scratch /shared/path --partition NAME [--size-mib 1024]

From a workstation, for the RemoteSlurm checkpoint scenario over real SSH::

    python tools/hpc_prestage_deep.py --remote-scratch /shared/path --host LOGIN_HOST --user USER \\
        --key ~/.ssh/id_rsa [--port 22] --partition NAME

No host, user, or key is embedded here.  ``--scratch`` must be visible at the
same absolute path from the login node and from the compute nodes.  Scenarios
run on the login node:

* ``volume``: a large single file (``--size-mib``) and many small files are
  staged, content-verified, and seen intact by the job; the legacy lifecycle
  runs the same workflow for a timing comparison;
* ``multinode``: a two-node allocation checks with ``srun`` that every node
  sees the same staged content;
* ``queue``: a job held in the queue by ``--begin`` (a real pending state)
  starts with its staged inputs, and the allocation wait is reported;
* ``queued-change``: a staged input changed while the job is pending (as seen
  by ``squeue``) stops the job before the command runs;
* ``cancel``: a pending job cancelled with ``scancel`` is an execution failure
  with a job identifier, its lock is released, and a resumed run stages and
  completes it;
* ``contention``: a second process using the same working directory while
  the first holds the stage-in lock (its job pending) fails in staging and
  does not disturb the first, which completes;
* ``node-local``: scratch on the login node's local disk, invisible to the
  compute nodes, fails in the execution phase and the command never runs.

The script prints one PASS/FAIL line per check and a JSON block of measured
timings, and exits non-zero when any check fails.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dagon import Workflow  # noqa: E402
from dagon.prestage import LOCK_NAME  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

Check = Tuple[str, bool, str]
METRICS: Dict[str, Any] = {}
TAG = "dgdeep%d" % os.getpid()  # unique job names, so squeue polling only sees this run's jobs


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


def run(workflow: Workflow, **kwargs: Any) -> Tuple[Optional[BaseException], float]:
    started = time.time()
    try:
        workflow.run(**kwargs)
        error = None
    except Exception as exc:  # reported as a check failure
        error = exc
    return error, round(time.time() - started, 3)


def pre_stage_metadata(task: Any) -> Dict[str, Any]:
    return dict(task.get_execution_metadata().get("pre_stage", {}))


def job_runtime_seconds(task: Any) -> Optional[int]:
    """Return the job's ``RunTime`` from ``scontrol show job`` (no accounting needed), or ``None``.

    ``sbatch -W`` returns on its own polling schedule, so its duration cannot
    resolve the allocated time; Slurm's job record can, while it is retained.
    """
    match = re.search(r"(\d+)", str((getattr(task, "result", None) or {}).get("output") or ""))
    if not match:
        return None
    shown = subprocess.run(["scontrol", "show", "job", match.group(1)], capture_output=True, text=True).stdout
    runtime = re.search(r"RunTime=(?:(\d+)-)?(\d+):(\d+):(\d+)", shown)
    if not runtime:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in runtime.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def pending_job(name: str, timeout: float = 120.0) -> Optional[Tuple[str, str]]:
    """Wait until a job called *name* is pending; return its identifier and reason."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = subprocess.run(["squeue", "-h", "-t", "PD", "-n", name, "-o", "%i %r"],
                             capture_output=True, text=True).stdout.split()
        if len(out) >= 2:
            return out[0], out[1]
        time.sleep(2)
    return None


def while_pending(name: str, action: Callable[[str, str], None]) -> threading.Thread:
    def watch() -> None:
        found = pending_job(name)
        if found:
            action(*found)
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


def two(name: str, scratch: str, partition: Optional[str], produce: str, consume: str, pre_stage: bool = True,
        consumer: Optional[Dict[str, Any]] = None) -> Tuple[Workflow, Any, Any]:
    workflow = Workflow(name, config=site_config(scratch, partition), pre_stage=pre_stage)
    producer = DagonTask(TaskType.SLURM, TAG + "p", produce, partition=partition, ntasks=1)
    options: Dict[str, Any] = {"partition": partition, "ntasks": 1}
    options.update(consumer or {})
    consuming = DagonTask(TaskType.SLURM, options.pop("name", TAG + "c"), consume, **options)
    workflow.add_task(producer)
    workflow.add_task(consuming)
    return workflow, producer, consuming


def scenario_volume(scratch: str, partition: Optional[str], size_mib: int) -> List[Check]:
    produce = ("head -c %dM /dev/urandom > big.bin && cksum < big.bin > big.cksum && mkdir many && "
               "for i in $(seq 1 5000); do echo $i > many/f$i.txt; done" % size_mib)
    consume = ("cksum < workflow:///%sp/big.bin > seen.cksum && "
               "find workflow:///%sp/many -type f | wc -l > many.count" % (TAG, TAG))
    results = {}
    for label, pre_stage in (("pre-staged", True), ("legacy", False)):
        workflow, producer, consumer = two("deep-volume-" + label, scratch, partition, produce, consume, pre_stage)
        error, wall = run(workflow)
        results[label] = (error, wall, producer, consumer)
    error, wall, producer, consumer = results["pre-staged"]
    legacy_error, legacy_wall, _legacy_producer, legacy_consumer = results["legacy"]
    metadata = pre_stage_metadata(consumer)
    METRICS["volume"] = {
        "size_mib": size_mib, "small_files": 5000,
        "pre_staged": {key: metadata.get(key) for key in (
            "staging_seconds", "allocation_wait_seconds", "execution_seconds", "scheduler_wall_seconds",
            "inputs", "inputs_content_verified")},
        # Whole workflow (producer and consumer), as seen by this process.
        "pre_staged_workflow_wall_seconds": wall,
        "legacy_workflow_wall_seconds": legacy_wall,
        # Allocated time of the consumer's job (Slurm RunTime). In the legacy
        # lifecycle it includes staging inside the allocation.
        "pre_staged_consumer_job_runtime_seconds": job_runtime_seconds(consumer),
        "legacy_consumer_job_runtime_seconds": job_runtime_seconds(legacy_consumer),
    }
    return [
        ("volume: pre-staged run finished", error is None and consumer.status.name == "FINISHED", repr(error)),
        ("volume: both inputs content-verified at stage-in", metadata.get("inputs_content_verified") == 2,
         json.dumps(metadata)),
        ("volume: the job saw the large file intact",
         (read(consumer.working_dir, "seen.cksum") or "x") == read(producer.working_dir, "big.cksum"), ""),
        ("volume: the job saw all small files", (read(consumer.working_dir, "many.count") or "").strip() == "5000",
         str(read(consumer.working_dir, "many.count"))),
        ("volume: legacy run of the same workflow finished",
         legacy_error is None and legacy_consumer.status.name == "FINISHED", repr(legacy_error)),
    ]


def scenario_multinode(scratch: str, partition: Optional[str]) -> List[Check]:
    # A workflow:// reference ends at whitespace, so it is passed to srun as an argument.
    consume = ("staged=workflow:///%sp/data.txt ; srun --nodes=2 --ntasks=2 --ntasks-per-node=1 sh -c "
               "'echo $(hostname) $(cksum < \"$0\")' \"$staged\" | sort > nodes.txt" % TAG)
    workflow, _producer, consumer = two("deep-multinode", scratch, partition, "seq 1 100000 > data.txt", consume,
                                        consumer={"nodes": 2, "ntasks_per_node": 1, "ntasks": None})
    error, _wall = run(workflow)
    lines = [line.split(" ", 1) for line in (read(consumer.working_dir, "nodes.txt") or "").splitlines() if line]
    METRICS["multinode"] = {"nodes": sorted(line[0] for line in lines)}
    return [
        ("multinode: finished", error is None and consumer.status.name == "FINISHED", repr(error)),
        ("multinode: two distinct nodes ran", len({line[0] for line in lines}) == 2, str(lines)),
        ("multinode: every node saw the same staged content",
         len(lines) == 2 and len({line[1] for line in lines}) == 1, str(lines)),
    ]


def scenario_queue(scratch: str, partition: Optional[str]) -> List[Check]:
    name = TAG + "q"
    seen: Dict[str, str] = {}
    workflow, _producer, consumer = two(
        "deep-queue", scratch, partition, "seq 1 7 > data.txt",
        "wc -l < workflow:///%sp/data.txt > lines.txt" % TAG,
        consumer={"name": name, "sbatch_options": ["--begin=now+60"]})
    watcher = while_pending(name, lambda job, reason: seen.update(job=job, reason=reason))
    error, _wall = run(workflow)
    watcher.join(timeout=5)
    metadata = pre_stage_metadata(consumer)
    METRICS["queue"] = {"squeue_reason": seen.get("reason"),
                        "allocation_wait_seconds": metadata.get("allocation_wait_seconds"),
                        "scheduler_wall_seconds": metadata.get("scheduler_wall_seconds")}
    return [
        ("queue: the job was pending in squeue", bool(seen.get("job")), json.dumps(seen)),
        ("queue: finished after the wait", error is None and consumer.status.name == "FINISHED", repr(error)),
        ("queue: allocation wait of at least 45 s recorded",
         float(metadata.get("allocation_wait_seconds") or 0) >= 45, json.dumps(metadata)),
        ("queue: the job read its staged input", (read(consumer.working_dir, "lines.txt") or "").strip() == "7", ""),
    ]


def scenario_queued_change(scratch: str, partition: Optional[str]) -> List[Check]:
    name = TAG + "m"
    seen: Dict[str, str] = {}
    workflow, _producer, consumer = two(
        "deep-queued-change", scratch, partition, "seq 1 7 > data.txt",
        "date +%%s > started && wc -l < workflow:///%sp/data.txt > lines.txt" % TAG,
        consumer={"name": name, "sbatch_options": ["--begin=now+45"]})

    def change(job: str, reason: str) -> None:
        staged = os.path.join(consumer.working_dir, ".dagon", "inputs", workflow.name, TAG + "p", "data.txt")
        with open(staged, "a", encoding="utf-8", newline="\n") as stream:
            stream.write("8\n")
        seen.update(job=job, reason=reason)

    watcher = while_pending(name, change)
    run(workflow)
    watcher.join(timeout=5)
    metadata = pre_stage_metadata(consumer)
    return [
        ("queued-change: input changed while the job was pending", bool(seen.get("job")), json.dumps(seen)),
        ("queued-change: execution failure with that job identifier",
         consumer.failure_phase == "execution" and str(metadata.get("scheduler_job_id")) == seen.get("job"),
         "%s %s" % (consumer.failure_phase, metadata.get("scheduler_job_id"))),
        ("queued-change: the command never ran", read(consumer.working_dir, "started") is None, ""),
    ]


def scenario_cancel(scratch: str, partition: Optional[str]) -> List[Check]:
    checkpoint = os.path.join(scratch, "deep-cancel-checkpoint.json")
    name = TAG + "x"
    cancelled: Dict[str, str] = {}

    def build(begin: Optional[str]) -> Tuple[Workflow, Any, Any]:
        workflow, producer, consumer = two(
            "deep-cancel", scratch, partition, "seq 1 7 > data.txt",
            "wc -l < workflow:///%sp/data.txt > lines.txt" % TAG,
            consumer={"name": name, "sbatch_options": [begin] if begin else []})
        workflow.checkpoint_file = checkpoint
        return workflow, producer, consumer

    def cancel(job: str, reason: str) -> None:
        subprocess.run(["scancel", job], check=False)
        cancelled.update(job=job, reason=reason)

    workflow, _producer, consumer = build("--begin=now+300")
    watcher = while_pending(name, cancel)
    run(workflow)
    watcher.join(timeout=5)
    metadata = pre_stage_metadata(consumer)
    lock_left = os.path.exists(os.path.join(str(consumer.working_dir), ".dagon", LOCK_NAME))
    resumed, _producer, again = build(None)
    error, _wall = run(resumed, resume_checkpoint_file=checkpoint)
    return [
        ("cancel: the pending job was cancelled", bool(cancelled.get("job")), json.dumps(cancelled)),
        ("cancel: execution failure with that job identifier",
         consumer.failure_phase == "execution" and str(metadata.get("scheduler_job_id")) == cancelled.get("job"),
         "%s %s" % (consumer.failure_phase, metadata.get("scheduler_job_id"))),
        ("cancel: the stage-in lock was released", not lock_left, ""),
        ("cancel: a resumed run did not reuse it and completed",
         error is None and again.status.name == "FINISHED" and not again.fair_checkpoint_reused
         and (read(again.working_dir, "lines.txt") or "").strip() == "7", "%r %s" % (error, again.status.name)),
    ]


def contention_child(scratch: str, partition: Optional[str], shared: str) -> int:
    workflow, _producer, consumer = two(
        "deep-contention-first", scratch, partition, "seq 1 7 > data.txt",
        "wc -l < workflow:///%sp/data.txt > lines.txt" % TAG,
        consumer={"working_dir": shared, "sbatch_options": ["--begin=now+45"], "name": TAG + "h"})
    error, _wall = run(workflow)
    return 0 if error is None and consumer.status.name == "FINISHED" else 1


def scenario_contention(scratch: str, partition: Optional[str]) -> List[Check]:
    shared = os.path.join(scratch, "deep-contention-shared")
    lock = os.path.join(shared, ".dagon", LOCK_NAME)
    first = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--contention-child", shared,
                              "--scratch", scratch, "--partition", partition or ""])
    deadline = time.time() + 120
    while time.time() < deadline and not read(lock, "owner"):
        time.sleep(1)
    held = os.path.isdir(lock)
    owner = read(lock, "owner")
    workflow, _producer, second = two(
        "deep-contention-second", scratch, partition, "seq 1 9 > data.txt",
        "wc -l < workflow:///%sp/data.txt > lines.txt" % TAG, consumer={"working_dir": shared})
    run(workflow)
    second_owner = read(lock, "owner")
    first_code = first.wait(timeout=600)
    return [
        ("contention: the first run held the lock", held and bool(owner), ""),
        ("contention: the second run failed in staging as lock-busy",
         second.failure_phase == "staging" and bool(pre_stage_metadata(second).get("stage_in_lock_busy")),
         str(second.failure_phase)),
        ("contention: the first run's lock was not touched", owner is not None and second_owner == owner, ""),
        ("contention: the first run completed with its own input",
         first_code == 0 and (read(shared, "lines.txt") or "").strip() == "7", "exit %s" % first_code),
    ]


def scenario_node_local(scratch: str, partition: Optional[str]) -> List[Check]:
    ran = os.path.join(scratch, "deep-node-local-command-ran")  # on shared storage
    with tempfile.TemporaryDirectory(prefix="dagon-deep-local-", dir="/tmp") as local:
        workflow = Workflow("deep-node-local", config=site_config(local, partition), pre_stage=True)
        producer = DagonTask(TaskType.BATCH, TAG + "p", "seq 1 7 > data.txt")
        consumer = DagonTask(TaskType.SLURM, TAG + "c", "date +%%s > %s && wc -l < workflow:///%sp/data.txt"
                             % (ran, TAG), partition=partition, ntasks=1)
        workflow.add_task(producer)
        workflow.add_task(consumer)
        run(workflow)
        metadata = pre_stage_metadata(consumer)
        return [
            ("node-local: staging succeeded on the login node", bool(metadata.get("staging_finished_at")),
             json.dumps(metadata)),
            ("node-local: the job failed in the execution phase", consumer.failure_phase == "execution",
             str(consumer.failure_phase)),
            ("node-local: the command never ran", not os.path.exists(ran), ""),
        ]


def scenario_remote_checkpoint(args: argparse.Namespace) -> List[Check]:
    remote = {"ip": args.host, "ssh_username": args.user, "keypath": os.path.expanduser(args.key),
              "ssh_port": args.port}
    scratch = args.remote_scratch
    with tempfile.TemporaryDirectory(prefix="dagon-deep-remote-") as local:
        checkpoint = os.path.join(local, "checkpoint.json")

        def build() -> Tuple[Workflow, Any, Any]:
            workflow = Workflow("deep-remote-checkpoint", config=site_config(scratch, args.partition), pre_stage=True)
            producer = DagonTask(TaskType.SLURM, TAG + "p", "seq 1 7 > data.txt", partition=args.partition,
                                 ntasks=1, **remote)
            consumer = DagonTask(TaskType.SLURM, TAG + "c", "wc -l < workflow:///%sp/data.txt > lines.txt" % TAG,
                                 partition=args.partition, ntasks=1, **remote)
            workflow.add_task(producer)
            workflow.add_task(consumer)
            workflow.checkpoint_file = checkpoint
            return workflow, producer, consumer

        workflow, producer, first = build()
        error, _wall = run(workflow)
        workflow, _producer, unchanged = build()
        reuse_error, _wall = run(workflow, resume_checkpoint_file=checkpoint)
        changed_ok = producer.ssh_connection.execute_command(
            "seq 1 9 > %s/data.txt" % producer.working_dir)["code"] == 0
        workflow, _producer, changed = build()
        changed_error, _wall = run(workflow, resume_checkpoint_file=checkpoint)
        lines = (changed.read_scratch_file(str(changed.working_dir) + "/lines.txt") or "").strip()
        return [
            ("remote-checkpoint: first run over SSH", error is None and first.status.name == "FINISHED", repr(error)),
            ("remote-checkpoint: unchanged input is reused after re-verification over SSH",
             reuse_error is None and unchanged.fair_checkpoint_reused, repr(reuse_error)),
            ("remote-checkpoint: changed input runs the task again",
             changed_ok and changed_error is None and not changed.fair_checkpoint_reused
             and changed.status.name == "FINISHED", repr(changed_error)),
            ("remote-checkpoint: the new run used the changed input", lines == "9", lines),
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="shared scratch path (on the login node)")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--size-mib", type=int, default=1024, help="size of the large input (MiB)")
    parser.add_argument("--only", nargs="*", help="run only these scenarios")
    parser.add_argument("--remote-scratch", help="shared scratch path on the cluster (RemoteSlurm mode)")
    parser.add_argument("--host")
    parser.add_argument("--user")
    parser.add_argument("--key")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--contention-child", help=argparse.SUPPRESS)
    args = parser.parse_args()
    partition = args.partition or None
    if args.contention_child:
        return contention_child(os.path.abspath(args.scratch), partition, args.contention_child)
    checks: List[Check] = []
    if args.remote_scratch:
        checks.extend(scenario_remote_checkpoint(args))
    else:
        scratch = os.path.abspath(args.scratch)
        os.makedirs(scratch, exist_ok=True)
        scenarios: Dict[str, Callable[[], List[Check]]] = {
            "volume": lambda: scenario_volume(scratch, partition, args.size_mib),
            "multinode": lambda: scenario_multinode(scratch, partition),
            "queue": lambda: scenario_queue(scratch, partition),
            "queued-change": lambda: scenario_queued_change(scratch, partition),
            "cancel": lambda: scenario_cancel(scratch, partition),
            "contention": lambda: scenario_contention(scratch, partition),
            "node-local": lambda: scenario_node_local(scratch, partition),
        }
        for name, scenario in scenarios.items():
            if args.only and name not in args.only:
                continue
            print("== %s" % name, flush=True)
            checks.extend(scenario())
    failed = 0
    for name, ok, detail in checks:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else " -> " + detail))
        failed += 0 if ok else 1
    print("METRICS " + json.dumps(METRICS, sort_keys=True))
    print("Deep pre-staging checks: %d passed, %d failed" % (len(checks) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
