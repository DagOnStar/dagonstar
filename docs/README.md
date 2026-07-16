# DAGonStar documentation

Start with the [academic tutorial syllabus](tutorial/README.md). It presents the curriculum by module rather than as a feature catalogue:

- orientation and setup;
- workflow graph construction;
- execution, staging, checkpointing, and lifecycle;
- native Python, web, and LLM task models;
- optional Docker, SSH, and Slurm infrastructure;
- FAIR metadata, meta-workflows, and CWL interoperability;
- [optional integrations](tutorial/integrations/README.md).

The locally runnable [tutorial notebook](tutorial/DAGonStar_tutorial.ipynb) covers the core and task-model path. Use the [glossary](tutorial/resources/glossary.md) and [troubleshooting guide](tutorial/resources/troubleshooting.md) while working through it.

## Guides

- [Getting started](getting_started.md)
- [User guide](user_guide.md)
- [Reference guide](reference_guide.md)
- [Developer guide](developer_guide.md)
- [Scientific workflows](introduction_to_scientific_workflow.md)
- [Workflow schema](the_workflow_schema.md)
- [Checkpointing](checkpoints.md)
- [Asynchronous launch](asynch_launch.md)
- [Native tasks](native_tasks.md)
- [Web tasks](web_tasks.md)
- [LLM tasks](llm_tasks.md)
- [FAIR principles](fair_principles.md)
- [IoT tasks and compute-continuum operations](iot_tasks.md)
- [IoT providers](iot_providers.md)
- [IoT checkpointing](iot_checkpointing.md)
- [IoT CWL representation](iot_cwl.md)
- [Compute continuum](compute_continuum.md)
- [CWL export](cwl_export.md)
- [Examples](examples/README.md)

Documentation follows the implementation-first rule: source and passing tests define supported behavior. Infrastructure and experimental integrations are labelled explicitly and are never prerequisites for the local core track.
