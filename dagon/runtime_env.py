"""Environment helpers for runner subprocesses started by DAGonStar tasks."""

import os
from pathlib import Path
from typing import Mapping, Optional

#: Directory that contains the ``dagon`` package currently being imported.
PACKAGE_ROOT = str(Path(__file__).resolve().parent.parent)


def runner_environment(extra: Optional[Mapping[str, str]] = None,
                       base: Optional[Mapping[str, str]] = None) -> dict:
    """Return an environment in which ``python -m dagon.<runner>`` resolves.

    Local runner subprocesses execute inside a task scratch directory, so a
    source checkout that has not been installed with ``pip install -e .`` would
    otherwise fail with ``ModuleNotFoundError: No module named 'dagon'``.  The
    directory holding the parent process's ``dagon`` package is prepended to
    ``PYTHONPATH`` so the child imports the same implementation.  Existing
    ``PYTHONPATH`` entries and task-specific variables are preserved; task
    variables are applied last, as before.
    """
    environment = dict(os.environ if base is None else base)
    current = environment.get("PYTHONPATH", "")
    entries = [entry for entry in current.split(os.pathsep) if entry]
    if PACKAGE_ROOT not in entries:
        entries.insert(0, PACKAGE_ROOT)
    environment["PYTHONPATH"] = os.pathsep.join(entries)
    environment.update(dict(extra or {}))
    return environment
