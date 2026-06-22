# Taskflow Examples

Source directory: [`examples/taskflow`](../../examples/taskflow)

## Files

- `taskflow-demo.py`
- `taskflow-demo-docker.py`
- `README.md`

## Purpose

The taskflow examples demonstrate explicit dependency construction. They are the
clearest starting point for understanding DAGonStar as a graph scheduler:
dependency edges are specified by calls such as:

```python
task_b.add_dependency_to(task_a)
```

This style is appropriate when a dependency is conceptual, procedural, or
resource-based rather than a direct file reference.

## Concepts exercised

- `Workflow`
- `DagonTask`
- `TaskType.BATCH`
- explicit predecessor/successor relationships
- cycle validation through `Workflow.Validate_WF()`
- Docker-backed task variants in `taskflow-demo-docker.py`

## Execution model

In the local taskflow demo, DAGonStar starts tasks as Python threads. Each task
waits for its declared predecessors before running its command. Since the
dependency relation is explicit, `workflow://` parsing is not the primary
mechanism in this example family.

## Verification

From the repository root:

```bash
cp dagon.ini.sample dagon.ini
cd examples/taskflow
python taskflow-demo.py
```

For the Docker variant, verify Docker first:

```bash
docker info
python taskflow-demo-docker.py
```

## Scientific interpretation

Taskflow is useful for workflows such as:

- quality control before model execution;
- parameter generation before simulation;
- validation before publication;
- sequential orchestration of tools whose data exchange is implicit or external.

For file-mediated scientific pipelines, prefer the dataflow examples because
`workflow://` references make data provenance explicit.
