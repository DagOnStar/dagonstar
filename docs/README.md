# DAGonStar documentation

Start with the [academic tutorial syllabus](tutorial/README.md). It presents the curriculum by module rather than as a feature catalogue:

- orientation and setup;
- workflow graph construction;
- execution, staging, checkpointing, and lifecycle;
- native Python, web, LLM, FaaS, IoT, and agentic task models;
- optional Docker, Apptainer, Kubernetes, Nomad, SSH, cloud, Slurm, BeeOND,
  pre-staging, and data-mover infrastructure (taught with mocks and emulation);
- FAIR metadata, meta-workflows, CWL interoperability, the compute continuum,
  operations, and an all-task-type capstone;
- [optional integrations](tutorial/integrations/README.md).

The locally runnable [tutorial notebook](tutorial/DAGonStar_tutorial.ipynb) has a verification cell for each of the 33 lessons, and [`coverage.json`](tutorial/coverage.json) maps every task type and inventoried feature to lessons, examples, and tests. Use the [glossary](tutorial/resources/glossary.md) and [troubleshooting guide](tutorial/resources/troubleshooting.md) while working through it.

## Guides

- [Getting started](getting_started.md)
- [User guide](user_guide.md)
- [Reference guide](reference_guide.md)
- [Developer guide](developer_guide.md)
- [Platform support and CI/CD](platform_support.md)
- [Scientific workflows](introduction_to_scientific_workflow.md)
- [Workflow schema](the_workflow_schema.md)
- [Checkpointing](checkpoints.md)
- [BeeOND on-demand file systems](beeond.md)
- [Scheduler-aware pre-staging](scheduler_prestaging.md)
- [Asynchronous launch](asynch_launch.md)
- [Native tasks](native_tasks.md)
- [Web tasks](web_tasks.md)
- [LLM tasks](llm_tasks.md)
- [Agentic tasks](agentic_tasks.md), with [configuration](agentic_configuration.md),
  [tools and guardrails](agentic_guardrails.md), and
  [evaluation, publication, and checkpoints](agentic_evaluation.md)
- [FAIR principles](fair_principles.md)
- [IoT tasks and compute-continuum operations](iot_tasks.md)
- [IoT providers](iot_providers.md)
- [IoT checkpointing](iot_checkpointing.md)
- [IoT CWL representation](iot_cwl.md)
- [Compute continuum](compute_continuum.md)
- [CWL export](cwl_export.md)
- [Examples](examples/README.md)

Documentation follows the implementation-first rule: source and passing tests define supported behavior. Infrastructure and experimental integrations are labelled explicitly and are never prerequisites for the local core track.
