# Slurm Dataflow Examples

Source directory: [`examples/dataflow/slurm`](../../examples/dataflow/slurm)

## Files

- `dataflow-demo-slurm.py`
- `dataflow-demo-slurm-remote.py`
- `README.md`

## Purpose

These examples show how DAGonStar submits workflow tasks through Slurm, the HPC
batch scheduler.

## Concepts exercised

- `TaskType.SLURM`
- `sbatch` command generation
- Slurm partition/resource parameters
- local and remote Slurm access
- dataflow dependencies through `workflow://`

## Prerequisites

- Slurm client tools installed.
- `sbatch` available in `PATH`.
- valid partition and account configuration for the site.
- shared or accessible scratch path appropriate for jobs.

Verify:

```bash
which sbatch
sinfo
squeue
```

## Local Slurm workflow

`dataflow-demo-slurm.py` constructs Slurm tasks with parameters such as:

- `partition`
- `ntasks`
- `memory`
- `time`
- `nodes`
- `ntasks_per_node`

The implementation generates an `sbatch` command and waits for completion with
`-W`.

## Remote Slurm workflow

`dataflow-demo-slurm-remote.py` combines SSH access and Slurm submission on a
remote machine. It requires both remote authentication and a valid Slurm
environment.

Verify SSH first:

```bash
ssh -i /path/to/key user@cluster-front-end hostname
```

Then verify Slurm on the remote host:

```bash
ssh -i /path/to/key user@cluster-front-end 'which sbatch && sinfo'
```

## Verification

After editing site-specific parameters:

```bash
cp dagon.ini.sample dagon.ini
cd examples/dataflow/slurm
python dataflow-demo-slurm.py
```

## Scientific interpretation

Slurm examples are appropriate for simulations and analyses requiring:

- many CPU cores;
- long wall-clock time;
- scheduler-managed queues;
- site accounting;
- access to HPC filesystems.

Document resource requests alongside scientific results, because they affect
runtime, reproducibility, and feasibility.
