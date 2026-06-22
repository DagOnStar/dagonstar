# Using DAGonStar from Jupyter Notebook

## Scope

This guide covers notebooks running on a workstation, VM, or server. A notebook
is an interactive front end for DAGonStar; backend requirements still apply to
Docker, SSH, Slurm, cloud, and staging integrations.

## Prerequisites

- Python 3.8 or later, Git, and a shell environment.
- Optional: Graphviz if an example renders a graph.
- Optional, per example: Docker, SSH access, Slurm, or cloud credentials.

## Create an environment and install DAGonStar

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

For the packaged stable release:

```bash
pip install dagonstar
```

For the latest `main` branch without a checkout:

```bash
pip install git+https://github.com/DagOnStar/dagonstar.git
```

For development or repository examples, use an editable checkout instead:

```bash
git clone https://github.com/DagOnStar/dagonstar.git
cd dagonstar
pip install -e .
```

## Install and start Jupyter

```bash
pip install notebook jupyterlab ipykernel
python -m ipykernel install --user --name dagonstar --display-name "Python (DAGonStar)"
jupyter lab
```

`jupyter notebook` is also supported. Select the **Python (DAGonStar)** kernel,
then verify it in a cell:

```python
import dagon
print("DAGonStar import OK")
```

## Run tutorial scripts from a notebook

Run commands from the repository root so relative paths resolve consistently:

```python
%cd /path/to/dagonstar
!python examples/tutorial/lesson_12_llm_tasks.py
!python examples/tutorial/lesson_13_web_tasks.py
```

For a notebook-native lesson, split the script into cells for configuration,
workflow and task creation, `workflow.run()`, and output inspection. The
examples in [`examples/colab/`](../examples/colab/README.md) use that shape.

## Persistent outputs and scratch directories

By default, DAGonStar uses `batch.scratch_dir_base` from `dagon.ini` (normally
`/tmp`). Set it to a project directory when outputs must survive cleanup or a
machine restart. Keep `remove_dir=False` while inspecting results, and use an
explicit, writable directory for notebook experiments.

## Troubleshooting

- Install the optional package and system service required by the selected
  backend; a notebook does not provide Docker, Graphviz, Slurm, or SSH access.
- Use `%cd` to the repository root before running an example with relative
  paths.
- Check that the scratch directory is writable and that cleanup has not removed
  an output.
- Configure remote credentials outside the notebook source; never embed keys.
