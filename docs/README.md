# DAGonStar Documentation

This directory contains the full DAGonStar documentation set. The documentation
is authoritative only when it matches the current implementation in this
repository.

## Core documents

- [Introduction to Scientific Workflows](introduction_to_scientific_workflow.md)
- [Getting Started](getting_started.md)
- [Configuration](configuration.md)
- [Architecture](architecture.md)
- [User Guide](user_guide.md)
- [Reference Guide](reference_guide.md)
- [Developer Guide](developer_guide.md)
- [Running External Scientific Software](running_external_software.md)
- [The `workflow://` Schema](the_workflow_schema.md)
- [Checkpoints](checkpoints.md)
- [Asynchronous workflow launch](asynch_launch.md)
- [Examples Catalog](examples/README.md)

## Tutorials

- [Tutorial index](tutorial/README.md)
- [Lesson 01: Create a local workflow](tutorial/lesson_01_local_workflow.md)
- [Lesson 02: Add explicit task dependencies](tutorial/lesson_02_explicit_dependencies.md)
- [Lesson 03: Use `workflow://` data dependencies](tutorial/lesson_03_data_dependencies.md)
- [Lesson 04: Inspect scratch directories and generated launchers](tutorial/lesson_04_scratch_and_launchers.md)
- [Lesson 05: Detect and fix dependency cycles](tutorial/lesson_05_cycle_detection.md)
- [Lesson 06: Use checkpoint files](tutorial/lesson_06_checkpointing.md)
- [Lesson 07: Choose data staging modes](tutorial/lesson_07_data_staging.md)
- [Lesson 08: Run Docker-backed tasks](tutorial/lesson_08_docker_tasks.md)
- [Lesson 09: Prepare remote and Slurm workflows](tutorial/lesson_09_remote_and_slurm.md)
- [Lesson 10: Compose meta-workflows](tutorial/lesson_10_meta_workflows.md)
- [Lesson 11: Launch a workflow asynchronously](tutorial/lesson_11_asynchronous_launch.md)

## Example family documentation

- [Taskflow examples](examples/taskflow.md)
- [Batch dataflow examples](examples/dataflow_batch.md)
- [Docker dataflow examples](examples/dataflow_docker.md)
- [Slurm dataflow examples](examples/dataflow_slurm.md)
- [Cloud dataflow examples](examples/dataflow_cloud.md)
- [Globus dataflow example](examples/dataflow_globus.md)
- [Transversal and meta-workflow examples](examples/transversal.md)
- [HiPES tutorial examples](examples/hipes_tutorial.md)
- [Environmental application examples](examples/environmental_application.md)
