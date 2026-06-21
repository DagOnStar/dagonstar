# Native Python Tasks

`TaskType.NATIVE` runs an importable module-level Python function while preserving DAG dependencies, checkpoints, scratch isolation, and `workflow://` dataflow.

```python
DagonTask(TaskType.NATIVE, "transform", "myworkflow.tasks:transform", inputs={"input_file": "workflow:///prepare/data.csv", "scale": 0.7}, outputs={"output_file": "clean.csv"})
```

Files are copied below `inputs/`; output parameters are safe relative paths below `outputs/` that the function must create. Scalars and results must be JSON-serializable; results are saved as `.dagon/native_result.json`. Downstream tasks can reference `workflow:///transform/outputs/clean.csv`.

Use `module:function`, not lambdas or nested functions. Missing parameters, unknown producers, and escaping paths fail validation. Local is default; use `executor="slurm"` and scheduler options in `resources` at a configured site where the module is importable.
