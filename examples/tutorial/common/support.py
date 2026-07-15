"""Shared configuration and task helpers for local tutorial examples."""
from pathlib import Path
from dagon import Workflow


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
