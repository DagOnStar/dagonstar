"""A deterministic, scheduler-free stand-in for ``sbatch -W`` (demonstrations and tests).

This module is *not* a Slurm emulator.  It replaces only the submission
command that :meth:`dagon.batch.Slurm.generate_command` builds: the job script
runs immediately with the local bash, in the ``-D`` directory, and the process
exits with the script's status, which is what ``sbatch -W`` reports.  There is
no queue, no allocation, and no resource accounting.

Every submission is recorded with a wall-clock timestamp and two
observations taken *at submission time*: whether the task's stage-in
completion marker already existed and whether ``.dagon/inputs`` was already
populated.  That is how the pre-staging examples and tests show that staging
finished before resources were requested.

Independent tasks submit concurrently, so each submission is written to its
own file in ``<log>.d/`` with an atomic rename, rather than appended to one
shared file: concurrent appends from several processes are not reliable on
every platform (records were observed to go missing on Windows).
:func:`read_log` returns the records ordered by time.

Usage::

    with mock_sbatch(log_path):
        workflow.run()
    submissions = read_log(log_path)

Run as a script, it behaves as the fake ``sbatch`` itself::

    python mock_scheduler.py LOG [--reject] [sbatch options] -D DIR -W SCRIPT

With ``--parsable`` (used for pre-staged submissions) it prints only the job
identifier, as ``sbatch --parsable`` does.
"""
import contextlib
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Iterator, List, Optional
from unittest import mock

MARKER = os.path.join(".dagon", "stage-in-complete.json")


def _inputs_populated(directory: str) -> bool:
    inputs = os.path.join(directory, ".dagon", "inputs")
    for _root, _dirs, files in os.walk(inputs):
        if files:
            return True
    return False


def _record_dir(log_path: str) -> str:
    return log_path + ".d"


def _write_record(log_path: str, record: Dict[str, Any]) -> None:
    """Write *record* to its own file with an atomic rename (safe under concurrency)."""
    directory = _record_dir(log_path)
    os.makedirs(directory, exist_ok=True)
    name = "%020d-%d.json" % (time.time_ns(), os.getpid())
    temporary = os.path.join(directory, "." + name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record))
    os.replace(temporary, os.path.join(directory, name))


def main(argv: List[str]) -> int:
    log_path, arguments = argv[0], argv[1:]
    reject = "--reject" in arguments
    arguments = [item for item in arguments if item != "--reject"]
    directory = arguments[arguments.index("-D") + 1]
    script = arguments[arguments.index("-W") + 1]
    name = arguments[arguments.index("-J") + 1] if "-J" in arguments else os.path.basename(directory)
    record: Dict[str, Any] = {
        "event": "sbatch", "time": time.time(), "job_name": name, "script": os.path.basename(script),
        "marker_present": os.path.isfile(os.path.join(directory, MARKER)),
        "inputs_populated": _inputs_populated(directory), "rejected": reject,
        "parsable": "--parsable" in arguments,
    }
    _write_record(log_path, record)
    if reject:
        sys.stderr.write("sbatch: error: Batch job submission failed: Invalid partition name specified\n")
        return 1
    # ``--parsable`` prints only the job identifier, like the real sbatch.
    sys.stdout.write("4242\n" if "--parsable" in arguments else "Submitted batch job 4242\n")
    sys.stdout.flush()
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    from dagon.platform_support import bash_executable
    completed = subprocess.run([bash_executable(), script], cwd=directory)
    return completed.returncode


@contextlib.contextmanager
def mock_sbatch(log_path: str, reject: bool = False) -> Iterator[None]:
    """Replace ``sbatch`` in generated Slurm submissions with this module."""
    from dagon.batch import Slurm
    from dagon.shell import join_command
    original = Slurm.generate_command

    def generate_command(self: Any, script_name: str) -> str:
        command = original(self, script_name)
        assert command.startswith("sbatch ")
        prefix = [sys.executable, os.path.abspath(__file__), log_path] + (["--reject"] if reject else [])
        return join_command(prefix) + command[len("sbatch"):]

    with mock.patch.object(Slurm, "generate_command", generate_command):
        yield


def read_log(log_path: str) -> List[Dict[str, Any]]:
    """Return the recorded submissions, ordered by submission time."""
    directory = _record_dir(log_path)
    if not os.path.isdir(directory):
        return []
    records = []
    for name in os.listdir(directory):
        if name.endswith(".json") and not name.startswith("."):
            with open(os.path.join(directory, name), encoding="utf-8") as stream:
                records.append(json.load(stream))
    return sorted(records, key=lambda item: item["time"])


def submission_for(log_path: str, job_name: str) -> Optional[Dict[str, Any]]:
    """Return the last recorded submission of *job_name*, if any."""
    matches = [item for item in read_log(log_path) if item["job_name"] == job_name]
    return matches[-1] if matches else None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
