# Exporting workflows to CWL

`Workflow.saveAsCWL(filename)` writes the current DAG as a self-contained
[Common Workflow Language (CWL) v1.2](https://www.commonwl.org/v1.2/) document.
The file uses JSON syntax, which is also valid CWL, so the base DAGonStar
installation does not require a YAML library.

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("cwl-example")
prepare = DagonTask(TaskType.BATCH, "prepare", "echo sample > sample.txt")
analyze = DagonTask(TaskType.BATCH, "analyze", "wc -c sample.txt")
workflow.add_task(prepare)
workflow.add_task(analyze)
analyze.add_dependency_to(prepare)

workflow.saveAsCWL("cwl-example.cwl")
```

The exporter discovers `workflow://` dependencies if
`make_dependencies()` has not already run and retains explicit dependencies.
It converts names to portable CWL identifiers and resolves collisions. Each
task becomes an embedded `CommandLineTool` executing `/bin/sh -c <command>`.
Boolean completion values connect steps and expose the completion state of
terminal tasks as workflow outputs. A Docker task with an image adds a
`DockerRequirement` hint.

## Validate or run the export

Install the CWL reference runner separately, then validate the document:

```bash
python -m pip install cwltool
cwltool --validate cwl-example.cwl
cwltool cwl-example.cwl
```

## Portability boundary

The export describes commands and graph ordering; it is not a lossless
translation of every DAGonStar executor. CWL runs exported commands in its own
working directories. DAGonStar scratch management, checkpointing, remote SSH,
Slurm, cloud, Kubernetes, Nomad, service registration, and specialized staging
are not reproduced.

In particular, `workflow://` text in a command is retained verbatim. It creates
the correct step dependency in the exported graph, but a generic CWL runner
does not implement DAGonStar's URI staging. For a directly runnable portable
CWL export, write commands using paths available in the CWL working directory,
or adapt the exported document with explicit CWL `File`/`Directory` inputs and
outputs. Native, web, and LLM tasks are exported only when their task object
provides a non-empty shell command.

The exported file contains task commands and container image names. Review it
before sharing, and never place credentials in commands.
