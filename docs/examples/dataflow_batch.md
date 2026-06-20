# Batch Dataflow Examples

Source directory: [`examples/dataflow/batch`](../../examples/dataflow/batch)

## Files

- `dataflow-demo.py`
- `dataflow-checkpoint-demo.py`
- `dataflow-demo-remote.py`
- `dataflow-demo-remote-checkpoint.py`
- `README.md`

## Purpose

These examples demonstrate the core DAGonStar dataflow model. Tasks produce
files in scratch directories, and downstream tasks consume those files through
the `workflow://` schema.

## Local batch workflow

`dataflow-demo.py` creates a four-task workflow:

- task `A` creates `output/f1.txt`;
- tasks `B` and `C` consume `workflow:///A/output/f1.txt`;
- task `D` consumes outputs from `B` and `C`.

This produces a diamond-shaped graph:

```text
A
├── B
├── C
└── D depends on B and C
```

The important implementation behavior is:

1. `Workflow.make_dependencies()` scans task commands.
2. `workflow://` references are converted into dependencies.
3. The stager creates local staged inputs.
4. Each command is rewritten to use local staged paths.

## Checkpoint workflow

`dataflow-checkpoint-demo.py` demonstrates checkpoint metadata. Checkpoint files
record task working directories and exit codes. If a task completed successfully
and its working directory still exists, a later run can reuse it.

For detailed checkpoint documentation, see [Checkpoints](../checkpoints.md).

## Remote batch workflows

`dataflow-demo-remote.py` and `dataflow-demo-remote-checkpoint.py` run tasks over
SSH. They require:

- reachable remote host;
- SSH user;
- private key path;
- key-based authentication;
- compatible scratch directory assumptions on the remote host.

Before running:

```bash
ssh -i /path/to/key user@host hostname
```

Remote data staging paths are more site-sensitive than local examples. Validate
remote-to-remote and remote-to-local transfer assumptions with small files before
running large scientific products.

## Verification

Local:

```bash
cp dagon.ini.sample dagon.ini
cd examples/dataflow/batch
python dataflow-demo.py
```

Checkpoint:

```bash
python dataflow-checkpoint-demo.py
```

Remote:

```bash
python dataflow-demo-remote.py
```

after editing SSH settings in the script.

## Scientific interpretation

This example family is the best model for external scientific software that
communicates through files. For each scientific step, identify:

- command to run;
- files it produces;
- files it consumes;
- task that produced each consumed file.

Then encode cross-task file use with `workflow://`.
