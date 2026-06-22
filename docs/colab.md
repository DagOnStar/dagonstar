# Running DAGonStar demos in Google Colab

This guide targets [Google Colab](https://colab.research.google.com/), not
Google Codelabs. Colab is useful for teaching, demos, and lightweight local
workflows; it is not a durable production scheduler or replacement for HPC or
cloud backends.

## What works in Colab

| DAGonStar capability | Supported in Colab? | Notes |
|---|---:|---|
| Local Python and Bash tasks | Yes | Best-supported mode for examples. |
| Notebook-driven workflow creation | Yes | Build and run workflows interactively. |
| `workflow://` references | Yes | Keep files in the runtime workspace. |
| FAIR local metadata exports | Yes | Standard-library exports; copy scratch to Drive for persistence. |
| Web/REST examples | Usually | Depends on network and service availability. |
| Checkpointing | Yes, with care | Put persistent checkpoints in Google Drive. |
| SSH/remote execution | Possible | Needs reachable hosts and secure credentials. |
| Slurm/HPC | Possible as a client | Colab can submit remotely; it is not the cluster. |
| Docker/container tasks | Limited | Hosted Colab is not a normal Docker host. |
| Cloud execution | Possible | Requires credentials kept out of notebooks. |
| Long production workflows | Not recommended | Runtimes are ephemeral and may disconnect. |

## Quick start

Install the stable PyPI release:

```python
!python --version
!pip install -U pip
!pip install dagonstar
```

Or install the latest repository version:

```python
!pip install git+https://github.com/DagOnStar/dagonstar.git
```

Clone the repository when an example needs files from its tree:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!python examples/colab/hello_colab.py
```

The ready-to-use notebooks are in
[`examples/colab/`](../examples/colab/README.md). The local web and mock-LLM
tutorial scripts are also suitable for hosted Colab:

```python
!python examples/tutorial/lesson_12_llm_tasks.py
!python examples/tutorial/lesson_13_web_tasks.py
```

Lesson 15's FAIR workflow is also local and credential-free. Its complete
notebook-ready source and persistence notes are in
[the FAIR-by-design tutorial](tutorial/lesson_15_fair_by_design.md).

## Persistence and architecture

Mount Drive when artifacts must survive a runtime reset:

```python
from google.colab import drive
drive.mount('/content/drive')
WORKDIR = "/content/drive/MyDrive/dagonstar-colab"
```

```text
Google Colab notebook -> DAGonStar workflow -> local tasks in /content
                                            -> optional Drive artifacts
                                            -> optional remote SSH/Slurm/cloud backends
```

## Security and troubleshooting

Never commit secrets or paste permanent private keys into a notebook. Use Colab
Secrets or short-lived credentials where available. After a reset, reinstall
packages and recreate files or clone the repository again. Check `%pwd` for
working-directory mistakes. Docker is generally unavailable, and remote hosts
may be unreachable because of network or credential restrictions. See
[`docs/jupyter_notebook.md`](jupyter_notebook.md) for local-notebook setup.
