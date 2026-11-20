"""Shared configuration and task helpers for local tutorial examples."""
import contextlib
import shutil
import tempfile
import time
from pathlib import Path
from dagon import Workflow


@contextlib.contextmanager
def scratch_directory(prefix):
    """Temporary scratch directory, removed with a short retry.

    On Windows a task's shell can keep a scratch file open for a moment after
    the workflow has ended, and removing the directory then fails with
    WinError 32; the removal is retried for up to two seconds.
    """
    path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        for attempt in range(20):
            try:
                shutil.rmtree(path)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.1)


def config(scratch, extra=None):
    value = {
        "batch": {"scratch_dir_base": str(scratch), "run_base": "", "threads": "2"},
        "dagon_service": {"use": "False", "route": "http://127.0.0.1:57000"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }
    value.update(extra or {})
    return value


def workflow(name, scratch, extra=None, **kwargs):
    return Workflow(name, config=config(scratch, extra), **kwargs)


def observation_command():
    rows = "station,time_utc,temperature_c,wind_m_s\\nSYN001,2025-01-01T00:00:00Z,12.0,3.0\\nSYN001,2025-01-01T01:00:00Z,14.0,5.0\\n"
    return "mkdir -p outputs; printf '" + rows + "' > outputs/observations.csv"


def require_text(path, expected):
    actual = Path(path).read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError("unexpected content in %s: %r" % (path, actual))
