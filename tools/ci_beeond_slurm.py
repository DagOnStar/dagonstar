"""BeeOND integration check against a live Slurm cluster (CI helper).

Usage (from the repository root, on a host where ``sbatch`` works)::

    python tools/ci_beeond_slurm.py [--scratch DIR] [--partition NAME] [--nodes N] [--skip-signal]

The CI job ``beeond-slurm`` runs it on a single-node Slurm cluster configured by
``tools/ci/slurm/setup-slurm-beeond.sh``.  That cluster emulates a BeeOND site:
a Slurm Prolog creates ``/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}``
for jobs submitted with ``--comment=beeond-fs`` and the Epilog deletes it when
the job ends.  Only data that DAGonStar persisted before the job ended
survives, so the checks below exercise the real persistence path:

* ``task``: a per-task volume is persisted to ``<working_dir>/beeond`` and a
  downstream task reads it through ``workflow://``;
* ``failure``: a failing command still has its volume persisted;
* ``workflow``: two tasks share a per-workflow holder volume through
  ``srun --jobid`` steps, and the holder persists it when the workflow ends;
* ``stream``: a producer and a consumer step of one holder allocation stream
  items through the volume (``workflow:///produce/items?stream``);
* ``export``: an ad-hoc BeeOND resource created with ``export="JOBFS"`` gives
  both of its tasks ``$JOBFS``, equal to ``$DAGON_BEEOND`` in the task and in
  ``dagon_beeond_srun`` steps on every node of the volume;
* ``signal``: Slurm's ``--signal=B:USR1@<grace>`` warning before the time limit
  stops the command and persists the volume (takes about two minutes).

When ``--site-log`` exists (the emulated site writes it), the script also
checks that every volume created by the site was destroyed again.  The script
exits non-zero when any check fails.
"""
import argparse
import os
import sys
import tempfile
import time
from typing import Callable, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dagon import Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

Check = Tuple[str, bool, str]

# Nodes per BeeOND job (``--nodes``); the CI site has a single node.
NODES = 1


def site_config(scratch: str, partition: Optional[str]) -> Dict[str, Dict[str, str]]:
    beeond = {"comment": "beeond-fs", "verify": "checksum", "mount_timeout": "60",
              "start_timeout": "300", "stop_timeout": "300", "poll_interval": "1"}
    if partition:
        beeond["partition"] = partition
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "4"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": partition or ""},
        "beeond": beeond,
    }


def read(*parts: Optional[str]) -> Optional[str]:
    if any(part is None for part in parts):
        return None  # the task never got a working directory
    filepath = os.path.join(*[str(part) for part in parts])
    if not os.path.isfile(filepath):
        return None
    with open(filepath, encoding="utf-8") as stream:
        return stream.read()


def status_code(*parts: Optional[str]) -> Optional[str]:
    content = read(*parts) or ""
    for line in content.splitlines():
        if line.startswith("persist_code="):
            return line.split("=", 1)[1]
    return None


def run_workflow(workflow: Workflow) -> Optional[BaseException]:
    try:
        workflow.run()
    except Exception as exc:  # reported as a check failure
        return exc
    return None


def scenario_task(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-beeond-task", config=site_config(scratch, partition))
    nodes = DagonTask(
        TaskType.SLURM, "nodes",
        "dagon_beeond_srun --nodes=$DAGON_BEEOND_NODES --ntasks-per-node=1 bash -c "
        "'echo \"node $(hostname)\" > \"$DAGON_BEEOND/node_$(hostname).txt\"'; "
        "for i in 1 2 3; do echo \"part $i\" > \"$DAGON_BEEOND/part_$i.txt\"; done; "
        "cat \"$DAGON_BEEOND\"/*.txt > \"$DAGON_BEEOND/out\"",
        partition=partition, nodes=NODES, ntasks_per_node=1, beeond="task")
    show = DagonTask(TaskType.SLURM, "show", "cp workflow:///nodes/beeond/out out",
                     partition=partition, ntasks=1)
    workflow.add_task(nodes)
    workflow.add_task(show)
    workflow.make_dependencies()
    error = run_workflow(workflow)
    persisted = os.path.join(nodes.working_dir or "", "beeond")
    names = sorted(os.listdir(persisted)) if nodes.working_dir and os.path.isdir(persisted) else []
    out = read(show.working_dir, "out") or ""
    return [
        ("task: workflow ran", error is None, repr(error)),
        ("task: tasks finished", [nodes.status.name, show.status.name] == ["FINISHED", "FINISHED"],
         "%s %s" % (nodes.status.name, show.status.name)),
        ("task: volume persisted", {"out", "part_1.txt", "part_2.txt", "part_3.txt"} <= set(names), str(names)),
        ("task: persistence verified", status_code(nodes.working_dir, ".dagon", "beeond_persist.status") == "0",
         str(read(nodes.working_dir, ".dagon", "beeond_persist.status"))),
        ("task: downstream read persisted data", "part 3" in out and "node " in out, out),
        ("task: every node wrote into the volume",
         len([name for name in names if name.startswith("node_")]) == NODES, str(names)),
    ]


def scenario_failure(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-beeond-failure", config=site_config(scratch, partition))
    task = DagonTask(TaskType.SLURM, "fails",
                     "echo partial > \"$DAGON_BEEOND/partial.txt\"; exit 3",
                     partition=partition, nodes=NODES, ntasks_per_node=1, beeond="task")
    workflow.add_task(task)
    run_workflow(workflow)
    return [
        ("failure: task failed", task.status.name == "FAILED", task.status.name),
        ("failure: volume still persisted",
         (read(task.working_dir, "beeond", "partial.txt") or "").strip() == "partial",
         str(read(task.working_dir, "beeond", "partial.txt"))),
        ("failure: persistence verified",
         status_code(task.working_dir, ".dagon", "beeond_persist.status") == "0",
         str(read(task.working_dir, ".dagon", "beeond_persist.status"))),
    ]


def scenario_workflow(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-beeond-workflow", config=site_config(scratch, partition))
    volume = workflow.create_beeond_volume("shared", nodes=NODES, ntasks_per_node=1, time="00:20:00")
    stage = DagonTask(TaskType.SLURM, "stage",
                      "dagon_beeond_srun --nodes=$DAGON_BEEOND_NODES --ntasks-per-node=1 "
                      "bash -c 'hostname > \"$DAGON_BEEOND/host_$(hostname).txt\"' && "
                      "seq 1 5 > \"$DAGON_BEEOND/input.txt\"",
                      beeond="workflow:shared")
    analyse = DagonTask(TaskType.SLURM, "analyse",
                        "wc -l < \"$DAGON_BEEOND/input.txt\" > \"$DAGON_BEEOND/lines.txt\"; "
                        "cp \"$DAGON_BEEOND/lines.txt\" lines.txt",
                        beeond="workflow:shared")
    workflow.add_task(stage)
    workflow.add_task(analyse)
    workflow.make_dependencies()
    analyse.add_dependency_to(stage)
    error = run_workflow(workflow)
    persisted = volume.persist_dir()
    names = sorted(os.listdir(persisted)) if os.path.isdir(persisted) else []
    lines = (read(analyse.working_dir, "lines.txt") or "").strip()
    return [
        ("workflow: workflow ran", error is None, repr(error)),
        ("workflow: tasks finished", [stage.status.name, analyse.status.name] == ["FINISHED", "FINISHED"],
         "%s %s" % (stage.status.name, analyse.status.name)),
        ("workflow: holder confirmed persistence", volume.persist_code == 0 and volume.job_id is not None,
         "code=%s job=%s" % (volume.persist_code, volume.job_id)),
        ("workflow: steps shared the volume", lines == "5", lines),
        ("workflow: volume persisted",
         [name for name in names if not name.startswith("host_")] == ["input.txt", "lines.txt"], str(names)),
        ("workflow: every node of the holder wrote into the volume",
         len([name for name in names if name.startswith("host_")]) == NODES, str(names)),
    ]


def scenario_stream(scratch: str, partition: Optional[str]) -> List[Check]:
    """Producer and consumer steps of one holder allocation stream through BeeOND."""
    workflow = Workflow("ci-beeond-stream", config=site_config(scratch, partition))
    volume = workflow.create_adhoc_filesystem("beeond", name="shared", nodes=NODES, ntasks_per_node=1,
                                              time="00:20:00")
    now = '"$DAGON_PYTHON" -c "import time; print(time.time())"'
    producer = DagonTask(TaskType.SLURM, "produce",
                         "for i in 1 2 3 4; do echo \"item $i\" > item-$i.txt; "
                         "\"$DAGON_PYTHON\" -m dagon.adhoc stream publish \"$DAGON_STREAM_OUT\" item-$i.txt "
                         "> /dev/null || exit 1; sleep 1; done; " + now + " > finished.txt")
    consumer = DagonTask(TaskType.SLURM, "consume",
                         "set -o pipefail; \"$DAGON_PYTHON\" -m dagon.adhoc stream items "
                         "workflow:///produce/items?stream --into in | while read -r item; do "
                         "cat \"$item\" >> received.txt; " + now + " >> arrivals.txt; done")
    for task in (producer, consumer):
        workflow.add_task(task)
        volume.bind(task)
    error = run_workflow(workflow)
    received = (read(consumer.working_dir, "received.txt") or "").splitlines()
    try:
        early = float(read(producer.working_dir, "finished.txt") or "") - \
            float((read(consumer.working_dir, "arrivals.txt") or "").split()[0])
    except (ValueError, IndexError):
        early = float("nan")
    return [
        ("stream: workflow ran", error is None, repr(error)),
        ("stream: tasks finished", [producer.status.name, consumer.status.name] == ["FINISHED", "FINISHED"],
         "%s %s" % (producer.status.name, consumer.status.name)),
        ("stream: only produce -> consume streams", consumer.stream_prevs == [producer],
         str([task.name for task in consumer.stream_prevs])),
        ("stream: items arrived verified and in order", received == ["item %d" % i for i in range(1, 5)],
         str(received)),
        ("stream: first item consumed while the producer ran", early > 0, "%.2f s early" % early),
        ("stream: stream persisted with the volume",
         os.path.isdir(os.path.join(volume.volume.persist_dir(), ".dagon-streams")),
         str(volume.volume.persist_dir())),
    ]


def scenario_export(scratch: str, partition: Optional[str]) -> List[Check]:
    """A developer-chosen variable (``export=``) names the allocation's BeeOND mount."""
    workflow = Workflow("ci-beeond-export", config=site_config(scratch, partition))
    volume = workflow.create_adhoc_filesystem("beeond", name="jobfs", export="JOBFS", nodes=NODES,
                                              ntasks_per_node=1, time="00:20:00")
    write = DagonTask(TaskType.SLURM, "write",
                      'test -n "$JOBFS" && test "$JOBFS" = "$DAGON_BEEOND" && '
                      'test "$JOBFS" = "$DAGON_ADHOC_JOBFS_PATH" && '
                      'dagon_beeond_srun --nodes="$DAGON_BEEOND_NODES" --ntasks-per-node=1 '
                      'bash -c \'test "$JOBFS" = "$DAGON_BEEOND" && echo "$JOBFS" > "$JOBFS/node-$(hostname).txt"\'')
    read_back = DagonTask(TaskType.SLURM, "read",
                          'echo workflow:///write/ > /dev/null; test "$JOBFS" = "$DAGON_BEEOND" && '
                          'ls "$JOBFS"/node-*.txt | wc -l | tr -d " " > count.txt && '
                          'cat "$JOBFS"/node-*.txt | sort -u > paths.txt && echo "$JOBFS" > seen.txt')
    for task in (write, read_back):
        workflow.add_task(task)
        volume.bind(task)
    workflow.make_dependencies()
    error = run_workflow(workflow)
    paths = (read(read_back.working_dir, "paths.txt") or "").split()
    seen = (read(read_back.working_dir, "seen.txt") or "").strip()
    count = (read(read_back.working_dir, "count.txt") or "").strip()
    return [
        ("export: workflow ran", error is None, repr(error)),
        ("export: tasks finished", [write.status.name, read_back.status.name] == ["FINISHED", "FINISHED"],
         "%s %s" % (write.status.name, read_back.status.name)),
        ("export: every node wrote through $JOBFS", count == str(NODES), "count=%r nodes=%d" % (count, NODES)),
        ("export: $JOBFS named the same mount on every node and task", len(paths) == 1 and paths == [seen],
         "paths=%s seen=%r" % (paths, seen)),
        ("export: $JOBFS is the allocation mount, not a host path", seen.startswith("/") and "beeond" in seen,
         repr(seen)),
        ("export: metadata records the name only",
         [item.get("export") for item in write.get_execution_metadata()["adhoc_filesystems"]] == ["JOBFS"],
         str(write.get_execution_metadata()["adhoc_filesystems"])),
    ]


def scenario_signal(scratch: str, partition: Optional[str]) -> List[Check]:
    workflow = Workflow("ci-beeond-signal", config=site_config(scratch, partition))
    task = DagonTask(TaskType.SLURM, "long",
                     "echo before > \"$DAGON_BEEOND/before.txt\"; sleep 900",
                     partition=partition, nodes=NODES, ntasks_per_node=1, time="00:03:00",
                     beeond={"scope": "task", "signal_grace": 100})
    workflow.add_task(task)
    started = time.monotonic()
    run_workflow(workflow)
    elapsed = time.monotonic() - started
    return [
        ("signal: task stopped before its time limit", task.status.name == "FAILED" and elapsed < 175,
         "%s after %.0f s" % (task.status.name, elapsed)),
        ("signal: volume persisted on USR1",
         (read(task.working_dir, "beeond", "before.txt") or "").strip() == "before",
         str(read(task.working_dir, "beeond", "before.txt"))),
        ("signal: persistence verified",
         status_code(task.working_dir, ".dagon", "beeond_persist.status") == "0",
         str(read(task.working_dir, ".dagon", "beeond_persist.status"))),
    ]


def site_checks(site_log: str, timeout: float = 120.0) -> List[Check]:
    """Every volume the emulated site created must have been destroyed."""
    if not os.path.isfile(site_log):
        return []
    deadline = time.monotonic() + timeout
    while True:
        with open(site_log, encoding="utf-8") as stream:
            events = [line.split() for line in stream if line.strip()]
        created = {event[1] for event in events if event[0] == "create"}
        destroyed = {event[1] for event in events if event[0] == "destroy"}
        if created <= destroyed or time.monotonic() >= deadline:
            break
        time.sleep(2)
    return [
        ("site: BeeOND volumes were created", len(created) >= 1, str(sorted(created))),
        ("site: every volume was destroyed at job end", created <= destroyed,
         "left: %s" % sorted(created - destroyed)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="shared scratch directory (default: temporary)")
    parser.add_argument("--partition", default=None)
    parser.add_argument("--nodes", type=int, default=1, help="nodes per BeeOND job (default: 1)")
    parser.add_argument("--skip-signal", action="store_true", help="skip the two-minute signal check")
    parser.add_argument("--site-log", default="/var/log/slurm/beeond-ci.log")
    args = parser.parse_args()
    global NODES
    NODES = args.nodes

    with tempfile.TemporaryDirectory(prefix="dagon-beeond-ci-") as temporary:
        scratch = os.path.abspath(args.scratch or temporary)
        os.makedirs(scratch, exist_ok=True)
        scenarios: List[Callable[[str, Optional[str]], List[Check]]] = [
            scenario_task, scenario_failure, scenario_workflow, scenario_stream, scenario_export]
        if not args.skip_signal:
            scenarios.append(scenario_signal)
        checks: List[Check] = []
        for scenario in scenarios:
            print("== %s" % scenario.__name__, flush=True)
            checks.extend(scenario(scratch, args.partition))
        checks.extend(site_checks(args.site_log))

    failed = 0
    for name, ok, detail in checks:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else " -> " + detail))
        failed += 0 if ok else 1
    print("BeeOND Slurm checks: %d passed, %d failed" % (len(checks) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
