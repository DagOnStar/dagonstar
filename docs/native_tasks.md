# Native Tasks

`TaskType.NATIVE` turns an importable Python function into a DAGonStar task. It
is a good fit when the work is naturally Python—data transformation, analysis,
or a small library call—rather than a shell command. A native task retains the
workflow features that matter for reproducibility: an isolated task directory,
declared file inputs and outputs, `workflow://` dependencies, and JSON result
metadata.

Native tasks are local by default. They can also submit a runner to Slurm, but
the selected Python environment, DAGonStar, and the function's code and
dependencies must be available to the compute node.

## The execution model

A task names a callable as `"package.module:function"`. Before execution,
DAGonStar validates and imports that target. During execution it:

1. creates the task scratch directory;
2. copies declared file inputs into `inputs/<parameter>/`;
3. creates declared output parent directories below `outputs/`;
4. starts a separate Python runner, passing the callable keyword arguments;
5. verifies that every declared output file was created; and
6. writes the callable's JSON-serializable return value to
   `.dagon/native_result.json`.

The function receives absolute paths for file inputs and declared outputs. It
does not receive `workflow://` strings. This deliberately keeps scientific code
independent of DAGonStar's staging syntax.

## Constructor and bindings

```python
DagonTask(
    TaskType.NATIVE,
    name,
    function,
    inputs=None,
    outputs=None,
    executor="local",
    resources=None,
    python=sys.executable,
    working_dir=None,
    environment=None,
)
```

`function` can be a `module:function` string or a module-level named Python
callable. `inputs` maps function parameter names to values. A value is either a
JSON-serializable scalar, a path to an existing local file, or a
`workflow://` file reference. Existing local files and workflow references are
staged as files; other strings are scalar values. `outputs` maps an output
parameter to a relative path below `outputs/`. Absolute paths and paths
containing `..` are rejected.

All binding names must match the callable's signature. Required parameters must
therefore be supplied through either `inputs` or `outputs`. The function return
value also must be JSON-serializable; use a declared output for large, binary,
or tabular results.

## Regular function: transform a staged file

Keep the callable in an importable module. For example, place this in
`analysis_functions.py` next to `workflow.py`:

```python
def scale_values(input_file: str, factor: float, output_file: str) -> dict:
    """Read numbers, write scaled numbers, and return small provenance metadata."""
    with open(input_file, encoding="utf-8") as source:
        values = [float(line) for line in source if line.strip()]

    with open(output_file, "w", encoding="utf-8") as destination:
        for value in values:
            destination.write(f"{value * factor}\n")

    return {"input_count": len(values), "factor": factor}
```

Then define a three-task workflow:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("native-example")
workflow.add_task(DagonTask(
    TaskType.BATCH,
    "produce",
    "mkdir -p data; printf '2\\n4\\n' > data/values.txt",
))
workflow.add_task(DagonTask(
    TaskType.NATIVE,
    "scale",
    "analysis_functions:scale_values",
    inputs={
        "input_file": "workflow:///produce/data/values.txt",
        "factor": 1.5,
    },
    outputs={"output_file": "scaled-values.txt"},
))
workflow.add_task(DagonTask(
    TaskType.BATCH,
    "consume",
    "cat workflow:///scale/outputs/scaled-values.txt",
))
workflow.run()
```

The reference creates the `produce -> scale` dependency. The native task stages
the producer's file to `inputs/input_file/values.txt`, passes that staged path
to `scale_values`, and exposes the generated file at
`workflow:///scale/outputs/scaled-values.txt`. Its return value is available in
the scale task directory at `.dagon/native_result.json`.

## Lambdas: why they are rejected

The following concise-looking form is **not** a valid native task:

```python
DagonTask(
    TaskType.NATIVE,
    "double",
    lambda value: {"result": value * 2},
    inputs={"value": 21},
)
```

It raises `ValueError`: a lambda has no stable importable function name for the
separate runner. Assigning it to a module variable does not change this; its
function name is still `<lambda>`. Nested functions are rejected for the same
reason. This restriction is intentional: it makes a workflow portable to a
fresh Python process and to Slurm.

Use a module-level regular function instead. It is just as small and has a
clearer name in workflow metadata:

```python
# native_math.py
def double(value: int) -> dict:
    return {"result": value * 2}
```

```python
DagonTask(
    TaskType.NATIVE,
    "double",
    "native_math:double",
    inputs={"value": 21},
)
```

This task writes `{ "result": 42 }` to `.dagon/native_result.json`; it has no
declared files because it only consumes and returns JSON data.

## Function dependencies and `requirements.txt`

DAGonStar does not install packages automatically for each native task. Create
and install the intended environment before starting the workflow, then run the
workflow with that environment's Python interpreter. This makes the same
interpreter available to both workflow construction (when DAGonStar validates
the import) and the separate native runner.

For a small NumPy-based project, use this layout:

```text
native-numpy-example/
├── requirements.txt
├── statistics_functions.py
└── workflow.py
```

`requirements.txt` declares the function dependency:

```text
numpy>=1.24
```

`statistics_functions.py` imports the dependency inside the importable module:

```python
import json

import numpy as np


def summarize_measurements(input_file: str, output_file: str) -> dict:
    values = np.loadtxt(input_file, dtype=float, ndmin=1)
    summary = {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }
    with open(output_file, "w", encoding="utf-8") as destination:
        json.dump(summary, destination, indent=2, sort_keys=True)
        destination.write("\n")
    return summary
```

`workflow.py` declares the staged input and output:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("native-numpy")
workflow.add_task(DagonTask(
    TaskType.BATCH,
    "produce",
    "mkdir -p data; printf '1.0\\n2.5\\n4.0\\n' > data/measurements.txt",
))
workflow.add_task(DagonTask(
    TaskType.NATIVE,
    "summarize",
    "statistics_functions:summarize_measurements",
    inputs={"input_file": "workflow:///produce/data/measurements.txt"},
    outputs={"output_file": "summary.json"},
))
workflow.run()
```

From the project root, create an isolated environment, install DAGonStar and
the project requirements, and run with that same interpreter:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e /path/to/dagonstar
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python workflow.py
```

The default `python=sys.executable` makes the runner use the interpreter that
started `workflow.py`. If the workflow is started by a different interpreter,
pass the environment explicitly, for example
`python="/absolute/path/to/.venv/bin/python"`; that environment must contain
DAGonStar as well as the dependencies in `requirements.txt`.

## Environment variables, local files, and Slurm

Use `environment` only for non-secret runtime settings needed by the callable:

```python
DagonTask(
    TaskType.NATIVE,
    "analyze",
    "analysis_functions:scale_values",
    inputs={"input_file": "data/values.txt", "factor": 2.0},
    outputs={"output_file": "result.txt"},
    environment={"OMP_NUM_THREADS": "1"},
)
```

Here `data/values.txt` must already exist when the task is created; it is copied
into the scratch directory. Do not put credentials in `environment`, function
arguments, return values, or output metadata. Supply secrets through a
user-controlled runtime configuration or a secret manager.

For Slurm, use `executor="slurm"` and scheduler keyword arguments in
`resources`, for example `resources={"partition": "compute", "ntasks": 2}`.
The scheduler launches `python -m dagon.native_runner` from the task directory.
Ensure the chosen `python`, the callable's import root, and all requirements
are available on the compute node; DAGonStar does not stage source packages or
install `requirements.txt` as part of submission.

## Troubleshooting checklist

- **"Native function is not importable"**: run the workflow from an environment
  that can import the module, and use `module:function` notation.
- **Binding incompatibility**: make the `inputs` and `outputs` keys match the
  function signature, including every required parameter.
- **Missing declared output**: the function must create each output path passed
  to it before returning.
- **Result is not JSON-serializable**: return ordinary dictionaries, lists,
  strings, numbers, booleans, or `None`; write richer objects to an output file.
- **Dependency unavailable in the runner**: install it in the interpreter named
  by `python`, not merely in another shell or virtual environment.

See the concise API summary in the [Reference Guide](reference_guide.md), the
[native example](../examples/native/README.md), and the
[native-task tutorial](tutorial/lesson_14_native_tasks.md).
