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

Client and object volumes (DAGonFS ``frontend=native``, DynoStore) have no path
a command could open, so references such as ``workflow:///Abc/xyz/results`` are
refused for them.  With such a provider the example uses only what they
support: ``stage_in``, the stream through the volume, ``stage_out`` (``Report``
compares the round-tripped file with ``Prep``'s), and attached tasks.

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
import shlex
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import custom_adapter  # noqa: E402,F401  (registers "local-directory")
from dagon import Status, Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

# Files inside the volume are read and written by a program (this Python interpreter), not by
# shell redirections or system tools: preload providers (CAPIO, Hercules, DAGonFS preload)
# intercept the calls of the programs they are loaded into, and macOS removes the preload
# variable from system binaries such as /bin/cat and /bin/bash.
PYTHON = shlex.quote(sys.executable)
READ = PYTHON + ' -c "import sys; sys.stdout.write(open(sys.argv[1]).read())" '
WRITE = PYTHON + ' -c "import sys; open(sys.argv[1], \'w\').write(sys.stdin.read())" '

EMIT = ('for i in $(' + READ + 'workflow:///Abc/xyz/inputs/data/n.txt ); do echo $i > item-$i; '
        '"$DAGON_PYTHON" -m dagon.adhoc stream publish "$DAGON_STREAM_OUT" item-$i; done')
SUM = ('total=0; for item in $("$DAGON_PYTHON" -m dagon.adhoc stream items workflow:///Emit/numbers?stream=xyz '
       '--into got); do total=$((total + $(cat "$item"))); done; echo $total > sum.txt')


def config(scratch):
    return {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "8"},
            "dagon_service": {"use": "False"}, "ftp_pub": {"ip": "localhost"}}


def has_paths(task, emulate):
    """True when tasks can open paths inside the volume (POSIX or preload access, or emulation)."""
    return emulate or task.filesystem.access in ("posix", "preload")


def shared_volume(scratch, provider, options, emulate):
    workflow = Workflow("shared-volume", config=config(scratch), portable_emulation=emulate)
    prep = DagonTask(TaskType.BATCH, "Prep", "mkdir -p data results; seq 1 5 > data/n.txt; touch results/.keep")
    abc = DagonTask(TaskType.VOLUME, "Abc", provider=provider, volume="xyz", options=options,
                    stage_in={"inputs/data": "workflow:///Prep/data", "results": "workflow:///Prep/results"})
    workflow.add_task(prep)
    workflow.add_task(abc)
    paths = has_paths(abc, emulate)
    if paths:
        # results/ was staged in, so both writers find it without creating it.
        square = DagonTask(TaskType.BATCH, "Square",
                           "for i in $(" + READ + "workflow:///Abc/xyz/inputs/data/n.txt ); do echo $((i * i)); "
                           "done | " + WRITE + "workflow:///Abc/xyz/results/square.txt")
        cube = DagonTask(TaskType.BATCH, "Cube",
                         "for i in $(" + READ + "workflow:///Abc/xyz/inputs/data/n.txt ); do echo $((i * i * i)); "
                         "done | " + WRITE + "workflow:///Abc/xyz/results/cube.txt")
        emit = DagonTask(TaskType.BATCH, "Emit", EMIT)
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"results": {"path": "workflow:///Abc/xyz/results", "type": "directory"}})
        report = DagonTask(TaskType.BATCH, "Report",
                           "paste workflow:///Del/results/square.txt workflow:///Del/results/cube.txt > report.txt")
        tasks = (square, cube, emit, DagonTask(TaskType.BATCH, "Sum", SUM), destroy, report)
    else:
        # Client (DAGonFS native) and object (DynoStore) volumes have no path a command can
        # open: data enters through stage_in, crosses tasks as a stream, and leaves through
        # stage_out, all through the provider's own client.
        emit = DagonTask(TaskType.BATCH, "Emit", EMIT.replace("workflow:///Abc/xyz/inputs/data/n.txt",
                                                              "workflow:///Prep/data/n.txt"))
        destroy = DagonTask(TaskType.VOLUME, "Del", action="destroy", volume="workflow:///Abc/xyz",
                            stage_out={"data": {"path": "inputs/data", "type": "directory"}})
        report = DagonTask(TaskType.BATCH, "Report",
                           "for i in $(cat workflow:///Del/data/n.txt ); do echo $((i * i)) $((i * i * i)); "
                           "done > report.txt; cmp workflow:///Del/data/n.txt workflow:///Prep/data/n.txt")
        tasks = (emit, DagonTask(TaskType.BATCH, "Sum", SUM), destroy, report)
    for task in tasks:
        workflow.add_task(task)
    total = workflow.find_task_by_name("shared-volume", "Sum")
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
    print("Report: %s rows %s; Sum read %s while Emit ran; volume %s"
          % (len(rows), "from the volume" if paths else "from data staged in and out of the volume",
             "15", abc.released))


def collected_volume(scratch, provider, options, emulate):
    workflow = Workflow("collected-volume", config=config(scratch), portable_emulation=emulate)
    ended = []
    workflow.add_listener("on_task_end", lambda task: ended.append(task.name))
    seed = DagonTask(TaskType.BATCH, "Seed", "seq 1 3 > numbers.txt")
    tmp = DagonTask(TaskType.VOLUME, "Tmp", provider=provider, volume="tmp", options=options,
                    stage_in={"numbers.txt": "workflow:///Seed/numbers.txt"})
    workflow.add_task(seed)
    workflow.add_task(tmp)
    if has_paths(tmp, emulate):
        write = DagonTask(TaskType.BATCH, "Write", "seq 1 3 | " + WRITE + "workflow:///Tmp/tmp/copy.txt")
        read = DagonTask(TaskType.BATCH, "Read", READ + "workflow:///Tmp/tmp/copy.txt | wc -l > count.txt")
        workflow.add_task(write)
        workflow.add_task(read)
        read.add_dependency_to(write)
    else:
        # Attached tasks hold the volume through its client environment, not through paths.
        write = DagonTask(TaskType.BATCH, "Write", 'test -n "$DAGON_ADHOC_TMP_PATH"')
        read = DagonTask(TaskType.BATCH, "Read", "wc -l < workflow:///Seed/numbers.txt > count.txt")
        workflow.add_task(write)
        workflow.add_task(read)
        tmp.attach(write, read)
        read.add_dependency_to(write)
    later = DagonTask(TaskType.BATCH, "Later", "cat workflow:///Read/count.txt > final.txt")
    workflow.add_task(later)
    released_after = []
    original = tmp.release_volume

    def release(reason, raise_errors=False):
        released_after.append(list(ended))
        return original(reason, raise_errors)

    tmp.release_volume = release
    workflow.run()
    assert all(task.status is Status.FINISHED for task in workflow.tasks)
    assert tmp.released == "no task refers to it", tmp.released
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
