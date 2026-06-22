# DAGonStar Colab examples

These small local workflows demonstrate DAGonStar in Google Colab and Jupyter:

- `hello_colab.py` creates a three-task DAG and passes a file with `workflow://`.
- `workflow_files_colab.py` creates, transforms, and summarizes a tiny CSV.
- The paired notebooks provide the same workflows in ordered cells.

Run locally from the repository root after `pip install -e .`:

```bash
python examples/colab/hello_colab.py
python examples/colab/workflow_files_colab.py
```

In Colab, clone the repository and run the same commands:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!python examples/colab/hello_colab.py
```

See [the Colab guide](../../docs/colab.md) and [the Jupyter guide](../../docs/jupyter_notebook.md).
The notebooks deliberately contain no secrets. Use Google Drive if generated
artifacts must survive a Colab runtime reset.
