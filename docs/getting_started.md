# Getting Started

This guide takes a new user from installation to a first local dataflow workflow.

## Requirements

- Python 3.8 or newer.
- A POSIX-like shell for the included command examples.
- Git.

Optional integrations require additional services:

- Docker for Docker tasks.
- SSH access for remote tasks.
- Slurm for Slurm tasks.
- Cloud provider credentials for cloud tasks.
- Globus or SKYCDS credentials for specialized data movement.

## Install DAGonStar from source

```bash
git clone https://github.com/DagOnStar/dagonstar.git
cd dagonstar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

For a smaller installation, install the package first and add only the optional
integrations you need:

```bash
python -m pip install -e .
python -m pip install -e ".[docker]"   # Docker tasks
python -m pip install -e ".[cloud]"    # cloud tasks
python -m pip install -e ".[globus]"   # Globus staging
python -m pip install -e ".[api]"      # Flask workflow service
```

## Create a configuration file

```bash
cp dagon.ini.sample dagon.ini
```

For a first local workflow, the sample defaults are sufficient. Confirm that:

```ini
[dagon_service]
use = False

[batch]
scratch_dir_base=/tmp/
```

## Write a first workflow

Create `first_workflow.py`:

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("FirstWorkflow")

    prepare = DagonTask(
        TaskType.BATCH,
        "prepare",
        "mkdir -p data; echo 'temperature,depth' > data/profile.csv; echo '18.5,12' >> data/profile.csv",
    )

    analyze = DagonTask(
        TaskType.BATCH,
        "analyze",
        "wc -l workflow:///prepare/data/profile.csv > summary.txt",
    )

    workflow.add_task(prepare)
    workflow.add_task(analyze)
    workflow.make_dependencies()
    workflow.run()
```

Run it:

```bash
python first_workflow.py
```

What happens:

1. `prepare` creates a CSV file in its scratch directory.
2. `analyze` references that file with `workflow:///prepare/data/profile.csv`.
3. `workflow.make_dependencies()` detects that `analyze` depends on `prepare`.
4. DAGonStar stages the referenced file into the `analyze` workspace.
5. `summary.txt` is produced by the `analyze` task.

## Inspect generated task directories

By default, task directories are created under `/tmp/`. Their names include a
timestamp and task name, for example:

```text
/tmp/1710000000000-prepare
/tmp/1710000000100-analyze
```

Each task directory contains:

- task outputs;
- a `.dagon/` directory;
- generated launcher scripts;
- captured standard output.

## Run the unit tests

```bash
python -m unittest discover -s tests -v
```

The tests verify important behavior that should remain stable while developing
new features.

## Next steps

- Read the [User Guide](user_guide.md) for task types and data movement.
- Follow the [tutorial sequence](tutorial/README.md) for incremental lessons.
- Learn how to wrap command-line models in
  [Running External Scientific Software](running_external_software.md).
- Read the [Architecture](architecture.md) document before modifying internals.
