# Examples Documentation

This directory documents the runnable and research-oriented examples under
[`examples/`](../../examples). It is a guided catalog rather than a replacement
for the source files. Each page explains the scientific/computational purpose,
the DAGonStar mechanisms exercised, prerequisites, execution model, and expected
verification strategy.

## Example families

- [`fair_local.py`](../../examples/fair/fair_local.py): local two-task FAIR metadata,
  checksum, RO-Crate, and provenance export without external services.

- [Taskflow examples](taskflow.md): explicit dependency graphs.
- [Asynchronous launch](../asynch_launch.md): local background execution and
  lifecycle callbacks; source: `examples/async/asynchronous_launch.py`.
- [Batch dataflow examples](dataflow_batch.md): local and remote dataflow,
  checkpointing, and `workflow://` file references.
- [Docker dataflow examples](dataflow_docker.md): container-backed tasks.
- [Slurm dataflow examples](dataflow_slurm.md): HPC scheduler-backed tasks.
- [Cloud dataflow examples](dataflow_cloud.md): Apache Libcloud-backed virtual
  machine tasks.
- [Globus dataflow example](dataflow_globus.md): endpoint-based scientific data
  movement.
- [Transversal and meta-workflow examples](transversal.md): cross-workflow
  dependencies and legacy transversal scripts.
- [HiPES tutorial examples](hipes_tutorial.md): staged scientific tutorial from
  configuration to map rendering.
- [Environmental application examples](environmental_application.md): WRF/ROMS/
  WaComM++-oriented demonstration material.
- [LLM task example](llm.md): a local OpenAI-compatible mock and a real-provider
  skeleton.
- [Native Python task example](native.md): staged files, scalar parameters, and declared outputs.
- [Web task example](web_tasks.md): local HTTP execution, staged uploads, and response outputs.
- [Tutorial source programs](../../examples/tutorial/README.md): runnable local
  sources for the advanced LLM and web lessons.
- [Colab notebook authoring](colab_notebooks.md): how to pair DAGonStar Python
  scripts with fresh-runtime Google Colab notebooks; source examples:
  [`examples/colab/`](../../examples/colab/README.md).

## How to use this catalog

Start with local examples:

1. [Taskflow](taskflow.md)
2. [Batch dataflow](dataflow_batch.md)
3. [Checkpointing](../checkpoints.md)
4. [Docker](dataflow_docker.md), if Docker is available

Then move to site-dependent examples:

1. [Slurm](dataflow_slurm.md)
2. [Remote batch](dataflow_batch.md#remote-batch-workflows)
3. [Cloud](dataflow_cloud.md)
4. [Globus](dataflow_globus.md)
5. [Environmental application](environmental_application.md)

## Consistency rule

The examples include legacy research material. This documentation describes the
current repository contents and distinguishes between:

- locally verifiable examples;
- examples requiring external software;
- examples requiring remote services or site-specific credentials;
- historical scripts retained for reproducibility context.
