# Lesson 14: Execute Native Python Tasks

> Colab compatibility: supported. Native Python tasks run in the Colab runtime.

## Run in Google Colab

Create the two files from the **Complete local example** in separate cells
using `%%writefile native_functions.py` and `%%writefile lesson_14_native_tasks.py`.
Then install and run them from the same directory:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!python3 lesson_14_native_tasks.py
```

Keeping both files together makes `native_functions:transform` importable to
the separate native task runner.

## Objective

Use an importable Python function as a workflow task while preserving DAGonStar
dependencies, scratch isolation, staged files, declared outputs, and checkpoint
metadata. Native tasks are appropriate when scientific logic is naturally Python
code and should not be encoded as a shell command.

## Concept

`TaskType.NATIVE` records a `module:function` reference and JSON-compatible
parameter bindings. Input files are staged below `inputs/`; declared output
parameters are paths below `outputs/`. The runner imports the function in the
task environment, so functions must be module-level and importable. Lambdas and
nested functions are deliberately rejected because they are not portable across
executors.

## Complete local example

Create the following two files in the same directory. This small two-file
layout is essential: it makes the function importable by the separate runner.

Save as `native_functions.py`:

```python
def transform(input_file: str, scale: float, output_file: str) -> dict:
    with open(input_file, encoding="utf-8") as source:
        values = [float(line.strip()) for line in source if line.strip()]
    with open(output_file, "w", encoding="utf-8") as destination:
        for value in values:
            destination.write(f"{value * scale}\n")
    return {"count": len(values), "scale": scale}
```

Save as `lesson_14_native_tasks.py`, then run
`python3 lesson_14_native_tasks.py` from that directory:

```python
import json
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def config(scratch):
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


with tempfile.TemporaryDirectory(prefix="dagon-native-lesson-") as scratch:
    workflow = Workflow("Lesson14", config=config(scratch))
    produce = DagonTask(
        TaskType.BATCH, "produce", "mkdir -p data; printf '2\\n4\\n' > data/input.txt"
    )
    transform = DagonTask(
        TaskType.NATIVE,
        "transform",
        "native_functions:transform",
        inputs={"input_file": "workflow:///produce/data/input.txt", "scale": 1.5},
        outputs={"output_file": "scaled.txt"},
    )
    consume = DagonTask(
        TaskType.BATCH, "consume", "cat workflow:///transform/outputs/scaled.txt"
    )
    for task in (produce, transform, consume):
        workflow.add_task(task)
    workflow.run()
    print(Path(transform.working_dir, "outputs", "scaled.txt").read_text())
    print(json.loads(Path(transform.working_dir, ".dagon", "native_result.json").read_text()))
```

## Interpretation and extension

The reference creates `produce -> transform`; the runner passes a scratch-local
file path to `input_file` and a scratch-local output path to `output_file`.
The declared output is therefore available to the downstream task through
`workflow:///transform/outputs/scaled.txt`. The function result is retained as
JSON metadata in `.dagon/native_result.json`.

Scalars and return values must be JSON-serializable. Output paths must be
relative and cannot escape scratch. For a configured cluster, use
`executor="slurm"` with scheduler settings in `resources`; install the function
module and DAGonStar where the compute node can import them. The
[native example](../../examples/native/README.md) and
`python3 -m unittest tests.test_native -v` provide further verification.
