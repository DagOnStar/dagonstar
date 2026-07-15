"""Runnable structural example for the DynoStore integration documentation.

This file intentionally performs no network operation. It prints the safe
DynoStore commands and the explicit DAG edge used by the live example.
"""

import sys
import tempfile
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "dynostore"
sys.path.insert(0, str(EXAMPLE_DIR))

from dynostore_workflow import build_workflow  # noqa: E402


with tempfile.TemporaryDirectory(prefix="dagon-dynostore-docs-") as scratch:
    workflow = build_workflow(scratch, "lesson-16-catalog")
    for task in workflow.tasks:
        dependencies = ", ".join(item.name for item in task.prevs) or "none"
        print("{} (dependencies: {})".format(task.name, dependencies))
        print(task.command)
