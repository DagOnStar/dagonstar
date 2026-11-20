"""Volume tasks: create an ad-hoc volume, share it through workflow://, release it.

Two workflows run one after the other.

``shared-volume`` (explicit destroy)::

    Prep -> Abc (create volume "xyz", stage in workflow:///Prep/data)
    Abc  -> Square, Cube          both write into workflow:///Abc/xyz/results/
    Abc  -> Emit ~~stream~~> Sum  Emit publishes numbers, Sum reads them while Emit runs
                                  (workflow:///Emit/numbers?stream=xyz)
    all  -> Del (destroy "xyz", stage out results/ into Del's scratch directory)
    Del  -> Report                reads workflow:///Del/results/... like any scratch file

``collected-volume`` (no destroy task): the volume is released by reference
counting as soon as its last user has finished, before the workflow ends.

By default the volumes are served by the ``local-directory`` adapter of
``custom_adapter.py`` (a real local resource, registered outside the ``dagon``
package).  ``--emulate PROVIDER`` runs a built-in provider under portable
emulation (a local directory stands in for the volume; this is not evidence
that the provider ran).  ``--live PROVIDER --option KEY=VALUE`` starts a
deployed provider (values are decoded as JSON)::

    python examples/adhoc/volume_task.py
    python examples/adhoc/volume_task.py --emulate capio
    python examples/adhoc/volume_task.py --live dagonfs --option executable=/path/to/dagonfs
"""

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import custom_adapter  # noqa: E402,F401  (registers "local-directory")
from dagon import Status, Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

EMIT = ('for i in $(cat workflow:///Abc/xyz/inputs/data/n.txt); do echo $i > item-$i; '
        '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i; done')
SUM = ('total=0; for item in $("$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///Emit/numbers?stream=xyz '
       '--into got); do total=$((total + $(cat "$item"))); done; echo $total > sum.txt')


def config(scratch):
    return {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "8"},
            "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}


def shared_volume(scratch, provider, options, emulate):
    workflow = Workflow("shared-volume", config=config(scratch), portable_emulation=emulate)
    prep = DagonTask(TaskType.BATCH, "Prep", "mkdir -p data; seq 1 5 > data/n.txt")
    abc = DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz", options=options,
                    stage_in={"inputs/data": "workflow:///Prep/data"})
    square = DagonTask(TaskType.BATCH, "Square",
                       "mkdir -p workflow:///Abc/xyz/results ; "
                       "for i in $(cat workflow:///Abc/xyz/inputs/data/n.txt); do echo $((i * i)); done "
                       "> workflow:///Abc/xyz/results/square.txt")
    cube = DagonTask(TaskType.BATCH, "Cube",
                     "mkdir -p workflow:///Abc/xyz/results ; "
                     "for i in $(cat workflow:///Abc/xyz/inputs/data/n.txt); do echo $((i * i * i)); done "
                     "> workflow:///Abc/xyz/results/cube.txt")
    emit = DagonTask(TaskType.BATCH, "Emit", EMIT)
    total = DagonTask(TaskType.BATCH, "Sum", SUM)
    destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                        stage_out={"results": {"path": "workflow:///Abc/xyz/results", "type": "directory"}})
    report = DagonTask(TaskType.BATCH, "Report",
                       "paste workflow:///Del/results/square.txt workflow:///Del/results/cube.txt > report.txt")
    for task in (prep, abc, square, cube, emit, total, destroy, report):
        workflow.add_task(task)
    workflow.make_dependencies()
    print("Del waits for: %s" % ", ".join(sorted(task.name for task in destroy.prevs)))
    print("bound to xyz: %s" % ", ".join(sorted(task.name for task in abc.filesystem.tasks)))
    workflow.run()
    failed = [task.name for task in workflow.tasks if task.status is not Status.FINISHED]
    assert not failed, "failed tasks: %s" % failed
    with open(os.path.join(report.working_dir, "report.txt"), encoding="utf-8") as stream:
        rows = [line.split() for line in stream.read().splitlines()]
    assert rows == [[str(i * i), str(i * i * i)] for i in range(1, 6)], rows
    with open(os.path.join(total.working_dir, "sum.txt"), encoding="utf-8") as stream:
        assert stream.read().strip() == "15"
    assert abc.released == "destroyed by Del", abc.released
    assert total.stream_prevs == [emit], "Sum streams from Emit"
    print("Report: %s rows from the volume; Sum read %s while Emit ran; volume %s"
          % (len(rows), "15", abc.released))


def collected_volume(scratch, provider, options, emulate):
    workflow = Workflow("collected-volume", config=config(scratch), portable_emulation=emulate)
    ended = []
    workflow.add_listener("on_task_end", lambda task: ended.append(task.name))
    abc = DagonTask(TaskType.VOLUME, "Tmp", provider=provider, volume="tmp", options=options)
    write = DagonTask(TaskType.BATCH, "Write", "seq 1 3 > workflow:///Tmp/tmp/numbers.txt")
    read = DagonTask(TaskType.BATCH, "Read", "wc -l < workflow:///Tmp/tmp/numbers.txt > count.txt")
    later = DagonTask(TaskType.BATCH, "Later", "cat workflow:///Read/count.txt > final.txt")
    for task in (abc, write, read, later):
        workflow.add_task(task)
    read.add_dependency_to(write)
    released_after = []
    original = abc.release_volume

    def release(reason, raise_errors=False):
        released_after.append(list(ended))
        return original(reason, raise_errors)

    abc.release_volume = release
    workflow.run()
    assert all(task.status is Status.FINISHED for task in workflow.tasks)
    assert abc.released == "no task refers to it", abc.released
    assert "Later" not in released_after[0], "released before the workflow ended"
    print("Tmp released when its last user finished (tasks ended before: %s)" % ", ".join(released_after[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--emulate", metavar="PROVIDER", help="portable emulation of a built-in provider")
    mode.add_argument("--live", metavar="PROVIDER", help="start a deployed provider")
    parser.add_argument("--option", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--scratch", help="scratch directory (default: a temporary directory)")
    arguments = parser.parse_args()
    options = {}
    for item in arguments.option:
        key, _, value = item.partition("=")
        try:
            options[key] = json.loads(value)
        except ValueError:
            options[key] = value
    provider = arguments.emulate or arguments.live or "local-directory"
    emulate = arguments.emulate is not None
    if emulate and provider == "hercules":
        options.setdefault("config", "hercules.conf")
    with tempfile.TemporaryDirectory(dir=arguments.scratch) as scratch:
        shared_volume(os.path.join(scratch, "shared"), provider, dict(options), emulate)
        second = dict(options)
        if "mountpoint" in second:
            second["mountpoint"] = str(second["mountpoint"]).rstrip("/") + "-tmp"
        collected_volume(os.path.join(scratch, "collected"), provider, second, emulate)
    print("Provider: %s (%s)" % (provider, "portable emulation" if emulate else
                                 "live" if arguments.live else "local adapter"))
    print("Verification: ok")


if __name__ == "__main__":
    main()
