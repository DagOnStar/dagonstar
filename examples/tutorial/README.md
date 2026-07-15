# Tutorial source programs

These scripts are the authoritative, runnable sources for the advanced tutorial
lessons. Run them from the repository root after installing DAGonStar:

```bash
python3 examples/tutorial/lesson_12_llm_tasks.py
python3 examples/tutorial/lesson_13_web_tasks.py
python3 examples/cwl/export_workflow.py --output /tmp/interoperable-workflow.cwl
```

The LLM and web scripts use a temporary scratch directory and a local
`127.0.0.1` service. The CWL lesson writes a deterministic document. None
requires credentials or an Internet connection.

## Google Colab

> Colab compatibility: supported. Both scripts use local execution only and can
> run in a hosted Colab runtime.

Install either the packaged release or the latest GitHub version:

```python
!pip install dagonstar
# or: !pip install git+https://github.com/DagOnStar/dagonstar.git
```

To run these repository scripts, clone the tree first:

```python
!git clone https://github.com/DagOnStar/dagonstar.git
%cd dagonstar
!pip install -e .
!python examples/tutorial/lesson_12_llm_tasks.py
!python examples/tutorial/lesson_13_web_tasks.py
!python examples/cwl/export_workflow.py --output /tmp/interoperable-workflow.cwl
```

Do not place provider keys or other credentials in a notebook. The bundled
examples use local mock services; real providers require secure configuration.
