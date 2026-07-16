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

## Run the complete tutorial notebook

Open [`docs/tutorial/DAGonStar_tutorial.ipynb`](tutorial/DAGonStar_tutorial.ipynb)
from a repository checkout. Its Lesson 00 cell discovers the checkout, installs
it into the active kernel with the Docker client extra needed by structural
tests, and defines subprocess helpers that always use the kernel's interpreter.
The notebook contains an executable verification cell for every Lesson 00–18.

Lessons 01–11 run credential-free local examples. Lessons 12–14 run mocked or
structural verification and therefore work without Docker, SSH, or Slurm; they
do not claim those backends executed. Lessons 15–17 run local FAIR,
meta-workflow, and CWL checks. Lesson 18 runs a bounded IoT mock and its local
contract tests. The web and LLM lessons bind only short-lived loopback mock
servers; the IoT mock contacts no broker or device.

For a notebook-native lesson, split the script into cells for configuration,
workflow and task creation, `workflow.run()`, and output inspection. The
examples in [`examples/colab/`](../examples/colab/README.md) use that shape.

Verify every task factory in one mixed workflow with:

```python
!python3 -m unittest tests.test_tasktype_interoperability -v
```

See [Task-type interoperability](tasktype_interoperability.md) for the backend
matrix. Jupyter can execute any backend installed and configured on its host;
otherwise it can still construct, validate, checkpoint, and export the graph.
Set `portable_emulation=True` to execute every task type locally when its real
backend is intentionally unavailable.

## Persistent outputs and scratch directories

By default, DAGonStar uses `batch.scratch_dir_base` from `dagon.ini` (normally
`/tmp`). Set it to a project directory when outputs must survive cleanup or a
machine restart. Keep `remove_dir=False` while inspecting results, and use an
explicit, writable directory for notebook experiments.

## Troubleshooting

- Install the optional package and system service required by the selected
  backend; a notebook does not provide Docker, Graphviz, Slurm, or SSH access.
- Run Lesson 00 first; later cells depend on its discovered `ROOT` and helpers.
- Check that the scratch directory is writable and that cleanup has not removed
  an output.
- Configure remote credentials outside the notebook source; never embed keys.
