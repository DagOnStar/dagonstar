"""Scheduler-aware pre-staging on a remote Slurm cluster through SSH (RemoteSlurm).

Run on your workstation::

    python3 pre_stage_remote.py --host LOGIN_HOST --user USER --key ~/.ssh/id_rsa \\
        --remote-scratch /shared/scratch/USER/dagon [--port 22] [--partition NAME] [--cores N] [--legacy]

No host names, user names, or keys are embedded in this file.  ``--remote-scratch``
is a path on the cluster that must be visible, at the same absolute path, from
the login node (where stage-in runs over SSH) and from the compute nodes, and
that persists while jobs are queued.

DAGonStar writes ``stage_in.sh`` on the login node over SSH and runs it there;
only after it succeeds and ``.dagon/stage-in-complete.json`` is in place does
it run the remote ``sbatch``.  Nothing is assumed to be mounted locally.  The
workflow and the reported evidence are those of ``pre_stage_local.py``.

This example submits real jobs: run it only where you are authorised to.
"""
import argparse
import os
import sys

from pre_stage_local import report
from pre_stage_mock import build_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, help="login (submission) host")
    parser.add_argument("--user", required=True)
    parser.add_argument("--key", required=True, help="private key used for SSH")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--remote-scratch", required=True, help="shared scratch path on the cluster")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--legacy", action="store_true", help="disable pre-staging (stage inside the jobs)")
    args = parser.parse_args()
    remote = {"ip": args.host, "ssh_username": args.user, "keypath": os.path.expanduser(args.key),
              "ssh_port": args.port}
    workflow = build_workflow(args.remote_scratch, pre_stage=not args.legacy, cores=args.cores,
                              partition=args.partition, remote=remote, name="Coastal-Forecast-RemoteSlurm")
    workflow.run()
    tasks = {task.name: task for task in workflow.tasks}
    failed = [name for name, task in tasks.items() if task.status.name != "FINISHED"]
    for name in failed:
        print("%s failed (phase: %s)" % (name, tasks[name].failure_phase or "legacy"))
    if failed:
        return 1
    extremes = tasks["analyse"].read_scratch_file(tasks["analyse"].working_dir + "/extremes.txt")
    print("Highest sea levels:\n" + (extremes or ""), end="")
    ok = True if args.legacy else report(tasks["simulate"])
    print("Verification:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
