# Meta-task examples (`TaskType.META`)

A meta-task runs a workflow written for another engine as one DAGonStar task,
through an adapter, without modifying the engine. See the
[meta-task guide](../../docs/meta_tasks.md) for the interface and for how to
write a new adapter.

| File | What it shows | Needs |
| --- | --- | --- |
| `meta_workflow_local.py` | `producer -> meta (command adapter) -> report`, verified checkpoint reuse, and portable emulation of a Nextflow meta-task | Python only |
| `meta_engines.py` | The same graph with Snakemake, Parsl, Nextflow, StreamFlow, and cwltool | Each engine is used only when installed |
| `workflows/Snakefile` | Unmodified Snakemake workflow (`config["text"]`) | Snakemake |
| `workflows/wordcount_parsl.py` | Unmodified Parsl program; `main(text, top)` returns futures | Parsl |
| `workflows/main.nf` | Unmodified Nextflow pipeline (`params.text`) | Nextflow, Java 17+ |
| `workflows/wordcount.cwl` | Unmodified CWL workflow for StreamFlow or any CWL runner | StreamFlow or cwltool |
| `workflows/tiny_engine.py` | Engine-free stand-in driven by the generic `command` adapter | Python only |

```bash
python examples/meta/meta_workflow_local.py
python examples/meta/meta_engines.py
python examples/meta/meta_engines.py --engine snakemake
python examples/meta/meta_engines.py --engine parsl --parsl-python /path/to/env/bin/python
```

Scratch data goes to a temporary directory (`--scratch DIR` keeps it). No
credentials or `dagon.ini` are needed. The CWL export of a meta-task is shown
by [`../cwl/export_meta_workflow.py`](../cwl/export_meta_workflow.py).
