# Lesson 09: Prepare Remote and Slurm Workflows

## Objective

Understand how to construct remote and Slurm tasks, and how to verify the
environment before running them.

## Concept

Remote task variants are selected by constructor arguments such as `ip`.
Slurm tasks use `TaskType.SLURM` and generate `sbatch` commands.

## Remote batch task

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("RemoteExample")

remote = DagonTask(
    TaskType.BATCH,
    "remote_hostname",
    "hostname > host.txt",
    ip="example.org",
    ssh_username="researcher",
    keypath="/home/researcher/.ssh/id_rsa",
)

workflow.add_task(remote)
workflow.make_dependencies()
workflow.run()
```

Before running, verify SSH:

```bash
ssh -i /home/researcher/.ssh/id_rsa researcher@example.org hostname
```

## Slurm task

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("SlurmExample")

task = DagonTask(
    TaskType.SLURM,
    "slurm_hostname",
    "hostname > host.txt",
    partition="compute",
    ntasks=1,
    time="00:05:00",
)

workflow.add_task(task)
workflow.make_dependencies()
workflow.run()
```

Before running, verify Slurm:

```bash
which sbatch
sinfo
```

## Local structural verification

You can verify construction without running external services:

```python
from dagon.task import DagonTask, TaskType

task = DagonTask(TaskType.SLURM, "check", "echo check", partition="debug", ntasks=1)
print(type(task).__name__)
print(task.generate_command("launcher.sh"))
```

## Scientific practice note

Remote and HPC workflows are reproducible only when resource requests,
environment modules, host configuration, and input data locations are recorded.
