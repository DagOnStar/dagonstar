# Asynchronous Workflow Launch

## FAIR recording

FAIR lifecycle capture works with `launch()` and `wait()` exactly as with
`run()`: exports are finalized by the workflow-end hook when the background
workflow actually ends, not when `launch()` returns.
`Workflow.run()` executes a workflow in the calling thread. Use `launch()` to
start it in a background thread, then use `wait()` when the caller needs its
completion.

```python
workflow.launch()
# Perform other work here.
workflow.wait()
```

`launch()` returns the background `threading.Thread`. Calling `launch()` while
that workflow is already running raises `RuntimeError`. `wait(timeout=...)`
returns `True` when the workflow completed and `False` when its timeout
expires. Calling `wait()` before `launch()` is a no-op and returns `True`.

Both `run()` and `launch()` automatically call `make_dependencies()` when the
workflow has not already had its dependencies built. Adding a task marks the
dependency graph as needing this rebuild.

## Lifecycle listeners

Each event is an event hook. Register a callable with `+=`, or use
`workflow.add_listener(event_name, callback)`. Workflow callbacks receive the
workflow object; task callbacks receive the task object. Listener exceptions
are logged and do not stop the workflow.

```python
def report_task(task):
    print(task.name, task.status.name)

workflow.on_task_start += report_task
workflow.add_listener("on_workflow_end", lambda wf: print("done", wf.name))
```

Remove a callback with `-=` or `remove_listener`.

| Event | Callback argument | When it fires |
| --- | --- | --- |
| `on_workflow_start` | workflow | Workflow execution begins. |
| `on_workflow_end` | workflow | Workflow execution ends. |
| `on_task_start` | task | A task thread begins. |
| `on_task_wait` | task | The task enters dependency waiting. |
| `on_task_staging_in_start` | task | The task begins preparing its staging-in launcher section. |
| `on_task_staging_in_end` | task | That staging-in launcher preparation completes. |
| `on_task_execute_start` | task | The task begins its executor phase. |
| `on_task_staging_out_start` | task | Post-execution output/reference cleanup begins. |
| `on_task_staging_out_end` | task | Post-execution output/reference cleanup completes. |
| `on_task_end` | task | A task thread ends, whether it finished or failed. |

DAGonStar currently generates staging-in commands as part of a task launcher
and has no separate data staging-out transfer phase; the corresponding hooks
accurately delimit the existing preparation and cleanup phases.

## Example

Run the local example after creating a local configuration:

```bash
cp dagon.ini.sample dagon.ini
python3 examples/asynchronous_launch.py
```
