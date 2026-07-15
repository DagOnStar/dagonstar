"""Inspect the workflow graph and generated DynoStore commands offline."""

import tempfile

from dynostore_workflow import build_workflow


with tempfile.TemporaryDirectory(prefix="dagon-dynostore-inspect-") as scratch:
    workflow = build_workflow(scratch, "example-catalog")
    for task in workflow.tasks:
        print(task.name, "depends on", [dependency.name for dependency in task.prevs])
        print(task.command)
