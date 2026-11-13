"""BeeOND on a live Slurm cluster, per task or per workflow (infrastructure-dependent).

This is the DAGonStar version of a site batch script that uses
``--comment=beeond-fs`` and ``/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}``.
Every node of the job writes a file into the BeeOND volume, then one task
combines them, and DAGonStar persists the volume before Slurm destroys it.

Run on the cluster login node, with a ``dagon.ini`` whose ``scratch_dir_base``
is on a file system shared with the compute nodes::

    python beeond_slurm.py --scope task
    python beeond_slurm.py --scope workflow --time 00:30:00

Or from a workstation, submitting through SSH (``RemoteSlurm``)::

    python beeond_slurm.py --scope task --ip login.example.org --ssh-user alice

Adjust ``--partition``, ``--nodelist``, ``--comment`` and ``--mount-template``
to your site.  See ``docs/beeond.md``.
"""
import argparse

from dagon import Workflow
from dagon.task import DagonTask, TaskType

# dagon_beeond_srun starts a parallel step on every node of the BeeOND job (task
# scope) or of the holder allocation (workflow scope); see docs/beeond.md.
NODE_COMMAND = ("dagon_beeond_srun --nodes=$DAGON_BEEOND_NODES --ntasks-per-node=1 bash -c "
                "'echo \"This is node $(hostname) writing its own output.\" > \"$DAGON_BEEOND/node_$(hostname).txt\"'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a BeeOND workflow on Slurm.")
    parser.add_argument("--scope", choices=("task", "workflow"), default="task")
    parser.add_argument("--partition", default="xxcpu")
    parser.add_argument("--nodelist", default="wn[01-04]")
    parser.add_argument("--nodes", type=int, default=4)
    parser.add_argument("--comment", default="beeond-fs")
    parser.add_argument("--mount-template", default="/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}")
    parser.add_argument("--time", default=None, help="holder wall time for --scope workflow")
    parser.add_argument("--signal-grace", type=int, default=120)
    parser.add_argument("--ip", help="login node for RemoteSlurm submission")
    parser.add_argument("--ssh-user")
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--keypath")
    parser.add_argument("--config", default="dagon.ini")
    args = parser.parse_args()

    remote = {}
    if args.ip:
        remote = {"ip": args.ip, "ssh_username": args.ssh_user, "ssh_port": args.ssh_port,
                  "keypath": args.keypath}

    workflow = Workflow("BeeOND-Slurm-" + args.scope, config_file=args.config)
    site = {"comment": args.comment, "mount_template": args.mount_template,
            "signal_grace": args.signal_grace}

    if args.scope == "task":
        beeond = dict(site, scope="task")
        nodes = DagonTask(TaskType.SLURM, "nodes",
                          NODE_COMMAND + " && "
                          "cat \"$DAGON_BEEOND\"/node_*.txt > \"$DAGON_BEEOND/out\"",
                          partition=args.partition, nodelist=args.nodelist, nodes=args.nodes, ntasks_per_node=1,
                          beeond=beeond, **remote)
        # Reads the persisted copy of the task volume from persistent storage.
        show = DagonTask(TaskType.SLURM, "show", "cat workflow:///nodes/beeond/out > out",
                         partition=args.partition, ntasks=1, **remote)
        workflow.add_task(nodes)
        workflow.add_task(show)
        workflow.make_dependencies()
    else:
        workflow.create_beeond_volume("default", partition=args.partition, nodelist=args.nodelist,
                                      nodes=args.nodes, ntasks_per_node=1, time=args.time, **site)
        nodes = DagonTask(TaskType.SLURM, "nodes", NODE_COMMAND,
                          beeond="workflow", **remote)
        combine = DagonTask(TaskType.SLURM, "combine",
                            "cat \"$DAGON_BEEOND\"/node_*.txt > \"$DAGON_BEEOND/out\" && "
                            "cp \"$DAGON_BEEOND/out\" out",
                            beeond="workflow", **remote)
        workflow.add_task(nodes)
        workflow.add_task(combine)
        workflow.make_dependencies()
        combine.add_dependency_to(nodes)

    workflow.run()
    for task in workflow.tasks:
        print(task.name, task.status.name, task.working_dir)
    for name, volume in workflow.beeond_volumes.items():
        print("workflow volume", name, "persisted to", volume.persist_dir(), "code", volume.persist_code)


if __name__ == "__main__":
    main()
