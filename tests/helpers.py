"""Shared helpers for unit tests."""

from dagon import Workflow


def minimal_config():
    """Return a small in-memory config that avoids filesystem logging setup."""
    return {
        "batch": {
            "scratch_dir_base": "/tmp",
            "run_base": "",
            "threads": "1",
        },
        "dagon_service": {
            "use": "False",
            "route": "http://localhost:57000",
        },
        "ftp_pub": {
            "ip": "localhost",
        },
        "slurm": {
            "partition": "",
        },
    }


def make_workflow(name="TestWorkflow"):
    """Create a workflow using only in-memory configuration."""
    return Workflow(name, config=minimal_config())


# -- Scheduler-aware pre-staging helpers --------------------------------------

CANNED_CONTEXT_INFO = {
    "type": "cluster-frontend", "public_ip": "none", "ip": "127.0.0.1", "user": "user",
    "SCP": "none", "FTP": "none", "GRIDFTP": "none", "SKYCDS": "none",
}


def canned_context_script(self=None):
    """Replacement for ``Task.get_how_im_script``: no network, no ssh-keygen."""
    import json
    import shlex
    return "echo " + shlex.quote(json.dumps(CANNED_CONTEXT_INFO)) + "\n"


def scratch_config(scratch):
    """Return an in-memory configuration whose scratch base is *scratch*."""
    config = minimal_config()
    config["batch"]["scratch_dir_base"] = scratch
    return config


def load_mock_scheduler():
    """Import ``examples/dataflow/slurm/mock_scheduler.py`` by path."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "examples" / "dataflow" / "slurm" / "mock_scheduler.py"
    spec = importlib.util.spec_from_file_location("dagon_mock_scheduler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
