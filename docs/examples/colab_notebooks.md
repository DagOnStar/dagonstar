# Creating Python and Colab notebook examples for DAGonStar

This document targets Google Colab notebooks (sometimes informally called
"Codelab"), alongside ordinary Python examples.

## Layout and pattern

Keep the script and notebook paired:

```text
examples/<topic>/example_name.py
examples/<topic>/example_name.ipynb
```

Use `examples/colab/` for Colab-specific material. Put reusable construction in
the script:

```python
def build_workflow(workdir):
    ...

def main():
    workflow = build_workflow(workdir)
    workflow.run()
```

Then a notebook can import `build_workflow`, choose `WORKDIR`, run the workflow,
and inspect its outputs.

## Authoring rules

- Keep examples deterministic, small, and free of secrets.
- Recreate tiny input data and use a temporary or explicit output directory.
- Give every script a `main()` function and keep notebook cells short and ordered.
- Make notebooks runnable from a fresh runtime. Include commented Colab install
  alternatives: `!pip install dagonstar` and
  `!pip install git+https://github.com/DagOnStar/dagonstar.git`.
- Mark Docker, Slurm, credentials, and remote services as optional; do not make
  them mandatory in a general Colab example.
- Document persistence when artifacts should outlive a Colab runtime.

## Colab compatibility checklist

| Question | Required answer |
|---|---|
| Runs without private credentials? | Yes |
| Avoids Docker unless explicitly marked? | Yes |
| Avoids Slurm unless explicitly marked? | Yes |
| Recreates tiny input data? | Yes |
| Documents persistence? | Yes |
| Works after a runtime reset? | Yes, after rerunning setup cells |
