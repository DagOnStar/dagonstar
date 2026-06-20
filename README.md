# DAGonStar

DAGonStar, also written as DAGon\*, is a lightweight Python workflow engine for
running directed acyclic graph (DAG) workflows across local machines, remote
servers, HPC clusters, containers, and cloud infrastructure.

![The DAGonStar logo](figures/DAGonStar_Logo01.png)

DAGonStar workflows are ordinary Python programs. Tasks can depend explicitly on
other tasks, or implicitly through `workflow://` data references that DAGonStar
resolves into task dependencies and staging operations.

## What DAGonStar supports

- Python-defined workflows.
- Explicit task graphs and data-driven dependency discovery.
- Local batch tasks.
- Remote SSH tasks.
- Slurm tasks.
- Docker tasks, locally or over SSH.
- Cloud-backed tasks through Apache Libcloud providers.
- Data staging by link, copy, SCP, Globus, and SKYCDS.
- Checkpoint/resume support.
- Meta-workflows that coordinate multiple workflows.

## Project status and quality assessment

The codebase is usable for its original research and production workflows, but it
is still a research-oriented Python package rather than a fully polished modern
library. The strongest parts are the compact workflow model and broad execution
target coverage. The main areas to keep improving are automated tests, typed
interfaces, shell-command safety, and clearer separation between optional
integration dependencies.

Recent cleanup in this repository:

- Removed committed sample credentials and token-like defaults from source files.
- Made optional configuration sections safer by using defaults where possible.
- Fixed package metadata so all DAGonStar packages are included.
- Removed an unnecessary Python 2 compatibility dependency.
- Replaced deprecated thread-name usage in checkpoint keys.
- Avoided silently swallowing task start/join errors.
- Fixed cloud task constructor argument ordering.
- Added this documentation and the contributor guidance in `AGENTS.md`.

## Installation

Use Python 3.8 or newer.

```bash
git clone https://github.com/DagOnStar/dagonstar.git
cd dagonstar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For editable development installs:

```bash
python -m pip install -e .
```

## Configuration

Copy the sample configuration before running examples:

```bash
cp dagon.ini.sample dagon.ini
```

Important sections:

- `[batch]`: local scratch directory and staging thread settings.
- `[dagon_service]`: optional DAGon service registration.
- `[slurm]`: default Slurm partition for Slurm staging or tasks.
- `[ec2]`, `[digitalocean]`, `[gce]`: optional cloud credentials.

Never commit real cloud keys, Globus tokens, SKYCDS tokens, SSH private keys, or
site-specific passwords. SKYCDS values are read from these environment variables:

```bash
export DAGON_SKYCDS_CLIENT_TOKEN=...
export DAGON_SKYCDS_CATALOG_TOKEN=...
export DAGON_SKYCDS_API_TOKEN=...
export DAGON_SKYCDS_IP=...
```

## Quick start

This example creates a four-task local workflow. Task `D` consumes outputs from
tasks `B` and `C`; the `workflow://` references are used to infer dependencies
and stage files.

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


if __name__ == "__main__":
    workflow = Workflow("DataFlow-Demo")

    task_a = DagonTask(TaskType.BATCH, "A", "mkdir -p output; hostname > output/f1.txt")
    task_b = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")
    task_c = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")
    task_d = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt")

    for task in (task_a, task_b, task_c, task_d):
        workflow.add_task(task)

    workflow.make_dependencies()
    workflow.run()
```

## Running examples

Most examples expect a `dagon.ini` file in the current working directory or in
the example directory.

```bash
cp dagon.ini.sample examples/dagon.ini
cd examples/taskflow
python taskflow-demo.py
```

Example groups:

- `examples/taskflow`: explicit task dependencies.
- `examples/dataflow/batch`: local data-driven workflows and checkpointing.
- `examples/dataflow/slurm`: Slurm and remote Slurm workflows.
- `examples/dataflow/docker`: Docker-backed workflows.
- `examples/dataflow/cloud`: cloud-backed task examples.
- `examples/transversal`: meta-workflow and transversal processing examples.
- `examples/hipes-tutorial`: tutorial material for HiPES workflows.
- `examples/envapp`: environmental application workflows and utilities.

## Development

Useful checks:

```bash
python -m unittest discover -s tests -v
python -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py
python -m pip install -e .
```

The repository includes a lightweight unit test suite under `tests/`. The tests
focus on behavior that should remain stable while features evolve: configuration
loading, workflow defaults, dependency discovery, cycle validation, JSON
serialization, and runtime-secret validation.

GitHub Actions runs the unit tests and source compilation checks on pushes to
`master`/`main` and on pull requests.

When changing workflow execution behavior, add a targeted unit test where
possible. If the behavior depends on Docker, Slurm, SSH, Globus, or a cloud
provider, add the smallest safe test for local logic and record any manual
integration command used in your change notes.

Recommended maintenance priorities:

1. Add tests for checkpoint/resume behavior and staging command generation.
2. Add integration tests for local batch workflows.
3. Replace shell string concatenation with safer quoting helpers where practical.
4. Split optional integrations into extras such as `dagonstar[docker]`, `dagonstar[cloud]`, and `dagonstar[globus]`.
5. Add type hints to public workflow and task APIs.

## Troubleshooting

### Missing `dagon.ini`

Create one from the sample:

```bash
cp dagon.ini.sample dagon.ini
```

### Docker examples cannot connect to Docker

Check that Docker is running and that your user can access the Docker socket:

```bash
docker info
```

### Remote tasks fail over SSH

Verify key-based SSH manually first:

```bash
ssh -i /path/to/key user@host hostname
```

### Globus or SKYCDS staging fails

Confirm the integration-specific credentials and endpoint IDs are configured.
SKYCDS values must be supplied through environment variables, not committed in
source files.

## Citation

If you use DAGonStar in academic work, please cite the workflow-engine paper:

Sánchez-Gallegos, Dante Domizzi, Diana Di Luccio, Sokol Kosta,
J. L. Gonzalez-Compean, and Raffaele Montella. “An efficient pattern-based
approach for workflow supporting large-scale science: The DagOnStar experience.”
Future Generation Computer Systems 122 (2021): 187–203.

Additional DAGonStar-related publications are listed in the older project
documentation and example material.

## License

DAGonStar is distributed under the Apache License 2.0. See `LICENSE`.

## Acknowledgments

DAGonStar development has been supported by research initiatives including
MytilX, MytilEx, and the EuroHPC H2020 ADMIRE project, and is used in production
environmental workflow applications at the University of Naples “Parthenope”.
