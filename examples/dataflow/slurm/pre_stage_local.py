"""Scheduler-aware pre-staging on a local Slurm installation (requires ``sbatch``).

Run on a Slurm login (submission) node, from any directory::

    python3 pre_stage_local.py --scratch /shared/scratch/$USER/dagon [--partition NAME] [--cores N]
    python3 pre_stage_local.py --scratch DIR --legacy      # same workflow, stage-in inside the jobs

``--scratch`` must be a file system that is visible, at the same absolute
path, from the submission node *and* the compute nodes, and that persists
while the job waits in the queue (a shared parallel file system, not
node-local or job-local storage such as BeeOND).  DAGonStar cannot always
detect this; see ``docs/scheduler_prestaging.md``.

The workflow is the coastal-forecast workflow of ``pre_stage_mock.py``.  With
pre-staging enabled (the default here), ``simulate`` stages its inputs on the
submission node before ``sbatch`` is called.  The script reports when stage-in
finished and when the allocation started running the compute launcher, and
checks that the former precedes the latter.  The two clocks belong to
different hosts, so the comparison has one-second resolution and assumes
synchronised clocks.

This example submits real jobs: run it only where you are authorised to.
"""
import argparse
import calendar
import json
import os
import sys
import time

from pre_stage_mock import build_workflow


def epoch(iso: str) -> int:
    return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))


def report(task) -> bool:
    """Print the pre-staging evidence of *task* and return whether the order holds."""
    marker_text = task.read_scratch_file(task.working_dir + "/.dagon/stage-in-complete.json")
    started_text = task.read_scratch_file(task.working_dir + "/.dagon/allocation_started_at")
    if not marker_text or not started_text:
        print("%s: no pre-staging evidence (marker=%s, allocation stamp=%s)"
              % (task.name, bool(marker_text), bool(started_text)))
        return False
    marker = json.loads(marker_text)
    allocation_started = int(started_text.strip())
    finished = epoch(marker["staging_finished_at"])
    print("%s: stage-in of %d inputs finished at %s; allocation started at %s (%+d s)"
          % (task.name, len(marker["inputs"]), marker["staging_finished_at"],
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(allocation_started)), allocation_started - finished))
    print("%s: pre-staging metadata %s" % (task.name, json.dumps(task.get_execution_metadata().get("pre_stage"),
                                                               sort_keys=True)))
    return allocation_started >= finished


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", required=True, help="shared scratch directory (same path on all nodes)")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--cores", type=int, default=1, help="cores (ntasks) requested by 'simulate'")
    parser.add_argument("--legacy", action="store_true", help="disable pre-staging (stage inside the jobs)")
    args = parser.parse_args()
    scratch = os.path.abspath(args.scratch)
    os.makedirs(scratch, exist_ok=True)
    workflow = build_workflow(scratch, pre_stage=not args.legacy, cores=args.cores, partition=args.partition,
                              name="Coastal-Forecast-Slurm")
    workflow.run()
    tasks = {task.name: task for task in workflow.tasks}
    failed = [name for name, task in tasks.items() if task.status.name != "FINISHED"]
    if failed:
        for name in failed:
            print("%s failed (phase: %s)" % (name, tasks[name].failure_phase or "legacy"))
        return 1
    with open(os.path.join(tasks["analyse"].working_dir, "extremes.txt")) as stream:
        print("Highest sea levels:\n" + stream.read(), end="")
    ok = True if args.legacy else report(tasks["simulate"])
    print("Verification:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
