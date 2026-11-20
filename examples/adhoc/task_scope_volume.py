"""Two task-scope ad-hoc volumes, each under a variable chosen by the developer.

The workflow is A -> B -> C.  Only B gets volumes: two DAGonFS volumes that are
started right before B runs and stopped right after it, whatever the outcome.
``export=`` names the variable that carries each volume's path in B
(``MYVOLUME_1``, ``MYVOLUME_2``), in addition to the generated
``DAGON_ADHOC_<NAME>_PATH``.  A and C see neither volume.  B keeps its result
by copying it into its own task directory, where C reads it through
``workflow:///B/``.

By default DAGonFS is emulated by local directories (portable emulation); this
demonstrates binding, scopes, and variables, not that DAGonFS ran.  With
``--live`` the DAGonFS options must name a real installation, for example
``--option executable=/path/to/dagonfs``.
"""

import argparse
import json
import os
import tempfile

from dagon import Workflow
from dagon.task import DagonTask, TaskType

B_COMMAND = ('cp workflow:///A/numbers.txt "$MYVOLUME_1/in.txt" && '
             'sort -rn "$MYVOLUME_1/in.txt" > "$MYVOLUME_2/sorted.txt" && '
             'head -n 10 "$MYVOLUME_2/sorted.txt" > top10.txt && '
             'printf "%s\\n%s\\n" "$MYVOLUME_1" "$MYVOLUME_2" > volumes.txt')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="start real DAGonFS volumes")
    parser.add_argument("--option", action="append", default=[], metavar="KEY=VALUE",
                        help="DAGonFS option for both volumes (JSON values accepted)")
    parser.add_argument("--scratch", help="scratch directory (default: a temporary directory)")
    arguments = parser.parse_args()
    options = {}
    for item in arguments.option:
        key, _, value = item.partition("=")
        try:
            options[key] = json.loads(value)
        except ValueError:
            options[key] = value

    with tempfile.TemporaryDirectory(dir=arguments.scratch) as scratch:
        config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
                  "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}
        workflow = Workflow("task-scope-volume", config=config, portable_emulation=not arguments.live)
        a = DagonTask(TaskType.BATCH, "A", "seq 1 100000 > numbers.txt")
        b = DagonTask(TaskType.BATCH, "B", B_COMMAND)
        c = DagonTask(TaskType.BATCH, "C",
                      'test -z "${MYVOLUME_1-}" && cat workflow:///B/top10.txt > result.txt')
        for task in (a, b, c):
            workflow.add_task(task)

        volumes = []
        for index in (1, 2):
            per_volume = dict(options)
            if "mountpoint" in per_volume:
                per_volume["mountpoint"] = "%s-%d" % (str(per_volume["mountpoint"]).rstrip("/"), index)
            volumes.append(b.create_adhoc_filesystem("dagonfs", name="b-scratch-%d" % index,
                                                     export="MYVOLUME_%d" % index, **per_volume))

        workflow.make_dependencies()
        workflow.run()

        assert all(task.result.get("code") == 0 for task in workflow.tasks)
        assert not any(volume.started for volume in volumes), "B's volumes must be stopped after B"
        for task in workflow.tasks:
            bound = ["%s as $%s" % (item["name"], item["export"])
                     for item in task.get_execution_metadata().get("adhoc_filesystems", [])]
            print("%s: %s" % (task.name, ", ".join(bound) or "no volume"))
        with open(os.path.join(b.working_dir, "volumes.txt")) as stream:
            paths = stream.read().split()
        assert len(set(paths)) == 2, paths
        with open(os.path.join(c.working_dir, "result.txt")) as stream:
            top = stream.read().split()
        assert top[:3] == ["100000", "99999", "99998"], top
        print("C read the top 10 computed on B's volumes")
        print("Verification: ok")


if __name__ == "__main__":
    main()
