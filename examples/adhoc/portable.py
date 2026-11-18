"""Exercise the common ad-hoc interface for every provider without external runtimes.

One workflow binds a producer and a consumer to each provider under portable
emulation: DAGonFS (FUSE3 and native), CAPIO, Hercules, and DynoStore run as
local directories, and BeeOND is bound to a Slurm task whose volume is emulated
by DAGonStar's existing BeeOND support.  The tasks write and read through
``$DAGON_ADHOC_PATH`` (or the object-store emulation directory), so the run
verifies binding, environment injection, per-resource variables, ordering, and
cleanup.  It is not evidence that any external file system ran.
"""

import os
import tempfile

from dagon import Workflow
from dagon.task import DagonTask, TaskType

WRITE = ('test "$DAGON_ADHOC_EMULATED" = 1 && test -z "$LD_PRELOAD" && '
         'printf "%s\\n" "$DAGON_ADHOC_PROVIDER" > "$TARGET/$DAGON_ADHOC_NAME.txt"')
READ = 'grep -qx "$DAGON_ADHOC_PROVIDER" "$TARGET/$DAGON_ADHOC_NAME.txt"'


def main():
    with tempfile.TemporaryDirectory() as scratch:
        config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "4"},
                  "slurm": {"partition": ""},
                  "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
        workflow = Workflow("adhoc-portable", config=config, portable_emulation=True)
        resources = {
            "dagonfs": workflow.create_adhoc_filesystem("dagonfs", name="ram"),
            "dagonfs-native": workflow.create_adhoc_filesystem("dagonfs", name="ram-socket",
                                                               frontend="native"),
            "capio": workflow.create_adhoc_filesystem("capio", name="stream"),
            "hercules": workflow.create_adhoc_filesystem("hercules", name="tiered",
                                                         config="site-hercules.conf"),
            "dynostore": workflow.create_adhoc_filesystem("dynostore", name="objects",
                                                          catalog="adhoc-portable"),
            "beeond": workflow.create_adhoc_filesystem("beeond", name="job"),
        }
        for label, resource in resources.items():
            task_type = TaskType.SLURM if label == "beeond" else TaskType.BATCH
            target = '"$DYNOSTORE_EMULATED_DIR"' if label == "dynostore" else '"$DAGON_ADHOC_PATH"'
            producer = DagonTask(task_type, "write-" + label, "TARGET=%s; %s" % (target, WRITE))
            consumer = DagonTask(task_type, "read-" + label,
                                 "echo workflow:///write-%s/ >/dev/null; TARGET=%s; %s" % (label, target, READ))
            workflow.add_task(producer)
            workflow.add_task(consumer)
            resource.bind(producer)
            resource.bind(consumer)
        workflow.make_dependencies()
        workflow.run()
        failed = [task.name for task in workflow.tasks if task.result.get("code")]
        assert not failed, failed
        assert not any(resource.started for resource in resources.values())
        for task in workflow.tasks:
            providers = [item["provider"] for item in task.get_execution_metadata()["adhoc_filesystems"]]
            assert len(providers) == 1, providers
        print("Verified %d providers through %d tasks" % (len(resources), len(workflow.tasks)))
        print("Verification: ok")


if __name__ == "__main__":
    main()
