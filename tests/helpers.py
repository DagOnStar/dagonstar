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
