# Native task with `requirements.txt`

This example runs `statistics_functions:summarize_measurements` as a
`TaskType.NATIVE` task. The function is defined in a separate module and imports
NumPy, which is declared in `requirements.txt`.

Run the setup and workflow from this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ../../..
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python workflow.py
```

Installing DAGonStar and NumPy in the same virtual environment is essential.
The workflow validates the function import before it runs, then the native
runner starts with the same `sys.executable` and imports the module again in the
task scratch directory.

The batch task generates three measurements. The native task stages that file,
writes `outputs/summary.json` in its task directory, and stores the same
JSON-serializable dictionary in `.dagon/native_result.json`. Inspect its task
directory according to the configured `batch.scratch_dir_base`.

For an explanation of native input/output bindings and interpreter selection,
see [Native Tasks](../../../docs/native_tasks.md).
