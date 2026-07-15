# Lesson 15: FAIR by design

> Colab compatibility: supported. This lesson uses only local batch tasks and
> the Python standard library; it needs neither credentials nor an external
> metadata service.

## Objective

Construct a small, reproducible workflow whose computational result and
provenance are recorded together. The example distinguishes an input-producing
task from its consumer, declares the scientific artifacts intentionally, and
then inspects the local FAIR exports produced at workflow completion.

## Concept

FAIR recording is opt-in. `Workflow.enable_fair(FairProfile(...))` attaches a
recorder to the existing workflow lifecycle without changing task scheduling,
command execution, or staging. `Artifact` declarations describe the intended
role and properties of files, while `annotate()` captures task-level context.
A `workflow:///producer/path` reference remains DAGonStar's normal local
staging dependency and is additionally represented as producer/consumer
provenance.

The recorder writes local, machine-readable metadata under
`<scratch>/.dagon/fair/<workflow>/<run>/` unless `FairProfile.output_dir` is
set. The exports include `run.json`, RO-Crate JSON-LD, PROV-like JSON, DataCite
and CodeMeta records, checksums for existing local outputs, a validation report,
and Markdown/HTML reports. They do not publish data or metadata, copy outputs
to a repository, retrieve remote files, or replace a domain repository policy.

## Run in Google Colab

In a fresh Colab runtime, install the repository checkout and run the code in
the next section in a single cell. The temporary directory is removed when the
cell exits, so copy `fair_dir` to mounted Google Drive before the `with` block
ends if the generated metadata must persist.

```python
!git clone --branch development https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
```

## Complete local example

Save the following as `lesson_15_fair_by_design.py`, or run it in one notebook
cell. It supplies its own local configuration, so no `dagon.ini` is required.

```python
import json
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.fair import AccessPolicy, Agent, Artifact, FairProfile
from dagon.task import DagonTask, TaskType


def local_config(scratch: str) -> dict:
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


with tempfile.TemporaryDirectory(prefix="dagon-fair-lesson-") as scratch:
    workflow = Workflow("Lesson15", config=local_config(scratch))
    workflow.enable_fair(FairProfile(
        title="A local FAIR workflow",
        description="Creates and copies a small research message.",
        creators=[Agent(name="DAGonStar tutorial")],
        license="Apache-2.0",
        keywords=["FAIR", "provenance", "tutorial"],
        access_policy=AccessPolicy(metadata="public", data="local"),
    ))
    produce = DagonTask(
        TaskType.BATCH, "produce", "mkdir -p data; echo reproducible > data/message.txt"
    ).declare_outputs(Artifact(
        "data/message.txt", media_type="text/plain", license="Apache-2.0"
    )).annotate(description="Create the primary local artifact.")
    copy = DagonTask(
        TaskType.BATCH, "copy", "cat workflow:///produce/data/message.txt > copied.txt"
    ).declare_inputs(Artifact("workflow:///produce/data/message.txt")).declare_outputs(
        Artifact("copied.txt", media_type="text/plain", license="Apache-2.0")
    ).annotate(description="Create a derived artifact from the producer output.")
    workflow.add_task(produce)
    workflow.add_task(copy)
    workflow.run()

    fair_dir = next(Path(scratch, ".dagon", "fair", "Lesson15").iterdir())
    run = json.loads((fair_dir / "run.json").read_text(encoding="utf-8"))
    print("FAIR exports:", sorted(path.name for path in fair_dir.iterdir()))
    print("Recorded tasks:", list(run["tasks"]))
    print("Derived output:", Path(copy.working_dir, "copied.txt").read_text().strip())
```

## Interpretation and verification

The `workflow:///produce/data/message.txt` reference creates the execution
edge `produce -> copy`; its declaration gives the recorder an explicit artifact
description as well. The `copied.txt` output is hashed only after it exists
locally. Inspect `run.json` for task metadata, `ro-crate-metadata.json` for the
JSON-LD representation, `prov.json` for relationships, and
`fairness-report.json` for validation findings.

Run the maintained local example with `python3 examples/fair/fair_local.py`
after providing a suitable local configuration, or run the stable behavior
checks with `python3 -m unittest tests.test_fair -v`. Environment capture is
disabled by default. If enabled, it is allowlist-only and names resembling
secrets are excluded; never put credentials, tokens, or private keys in FAIR
annotations or notebook cells. See [FAIR principles](../fair_principles.md) for
the supported export boundary and validation semantics.
