# DAGonStar academic tutorial

This tutorial teaches DAGonStar as a scientific-workflow system: graph construction, execution and recovery, structured task models (including agentic tasks), distributed infrastructure, then FAIR composition, interoperability, and operations. It is intended for graduate students, research software engineers, computational scientists, and advanced undergraduates who know basic Python and shell usage but may be new to workflow semantics.

## Complete-course learning outcomes

After the course you can construct and validate a DAG, distinguish control from data dependencies, inspect staging and execution evidence, select task and backend models, configure and evaluate bounded agentic tasks, reason about recovery and asynchronous lifecycle, record supported FAIR metadata, compose workflows, evaluate a CWL v1.2 export's portability boundary, and operate the system with honest evidence labels.

## Prerequisites

Python 3, a command shell, and a repository checkout are sufficient for the local path. Start with Lesson 00. Docker, Apptainer, Kubernetes, Nomad, SSH, Slurm, BeeOND, Globus, DynoStore, cloud, and real web, LLM, FaaS, IoT, or agent providers are optional and never required for the core conceptual sequence.

## Curriculum map

| Lesson | Learning focus | Runtime | External service | Colab | Track |
|---|---|---|---|---|---|
| [00](lesson_00_set_up_dagonstar_and_understand_the_learning_model.md) | Environment and learning model | Local | No | Supported | Core |
| [01](lesson_01_create_and_run_the_first_local_task.md) | First local task | Local | No | Supported | Core |
| [02](lesson_02_build_a_directed_acyclic_graph.md) | Control-dependency DAG | Local | No | Supported | Core |
| [03](lesson_03_connect_tasks_with_workflow_data_references.md) | Data dependencies | Local | No | Supported | Core |
| [04](lesson_04_validate_the_graph_and_repair_dependency_cycles.md) | Cycle validation | Local | No | Supported | Core |
| [05](lesson_05_inspect_scratch_directories_launchers_and_logs.md) | Execution artifacts | Local | No | Supported | Execution |
| [06](lesson_06_choose_and_verify_data_staging_modes.md) | COPY and LINK staging | Local | No | Supported | Execution |
| [07](lesson_07_checkpoint_and_resume_workflow_execution.md) | Checkpoint and resume | Local | No | Supported | Execution |
| [08](lesson_08_launch_asynchronously_and_observe_lifecycle_events.md) | Lifecycle and background launch | Local | No | Limited | Execution |
| [09](lesson_09_execute_native_python_functions.md) | Native Python tasks | Local | No | Supported | Task models |
| [10](lesson_10_execute_a_web_service_task.md) | Structured HTTP tasks | Local mock | Local mock | Supported | Task models |
| [11](lesson_11_execute_an_llm_task_responsibly.md) | Auditable LLM tasks | Local mock | Local mock | Limited | Task models |
| [12](lesson_12_invoke_serverless_functions_with_faas_tasks.md) | FaaS invocation | Local mock | No | Supported | Task models |
| [13](lesson_13_observe_and_actuate_devices_with_iot_tasks.md) | Bounded IoT interaction | Local mock | No | Supported | Task models |
| [14](lesson_14_specify_and_configure_an_agentic_task.md) | Agentic contract and `dagon.ini` profiles | Local mock | No | Supported | Task models |
| [15](lesson_15_constrain_agent_tools_with_guardrails.md) | Agent tools and guardrails | Local mock | No | Supported | Task models |
| [16](lesson_16_evaluate_publish_and_checkpoint_agent_results.md) | Result fit, publication, checkpoints | Local mock | No | Supported | Task models |
| [17](lesson_17_run_a_task_in_docker.md) | Container execution | Mocked client; Docker optional | Docker daemon (live only) | Construction checks | Infrastructure |
| [18](lesson_18_run_a_task_with_apptainer.md) | HPC containers | Mocked; Apptainer optional | Apptainer (live only) | Construction checks | Infrastructure |
| [19](lesson_19_run_a_task_on_kubernetes.md) | Pod lifecycle | Mocked API; cluster optional | Cluster (live only) | Construction checks | Infrastructure |
| [20](lesson_20_run_a_task_on_nomad.md) | Nomad job lifecycle | Mocked API; Nomad optional | Nomad (live only) | Construction checks | Infrastructure |
| [21](lesson_21_run_a_task_on_a_remote_host_with_ssh.md) | Remote execution | Mocked SSH; host optional | SSH host (live only) | Construction checks | Infrastructure |
| [22](lesson_22_configure_cloud_tasks_without_provisioning.md) | Cloud task configuration | Local | Provider (live only) | Configuration checks | Infrastructure |
| [23](lesson_23_submit_a_task_through_slurm.md) | Scheduled execution | Mock `sbatch`; Slurm optional | Cluster (live only) | Limited | Infrastructure |
| [24](lesson_24_use_beeond_job_local_storage.md) | BeeOND job-local storage | Local emulation | BeeOND site (live only) | Supported | Infrastructure |
| [25](lesson_25_plug_in_adhoc_file_systems_and_stream_between_tasks.md) | Pluggable ad-hoc file systems and streams | Local adapter; providers emulated | Storage systems (live only) | Supported | Infrastructure |
| [26](lesson_26_share_and_release_volumes_with_volume_tasks.md) | Volume tasks: create, share, release | Local emulation | Storage systems (live only) | Supported | Infrastructure |
| [27](lesson_27_stage_inputs_before_scheduler_submission.md) | Scheduler-aware pre-staging | Mock `sbatch` | Cluster (live only) | Limited | Infrastructure |
| [28](lesson_28_select_data_movers_and_transfer_services.md) | Data movers and transfer services | Local mock | Transfer services (live only) | Supported | Infrastructure |
| [29](lesson_29_make_a_workflow_fair_by_design.md) | FAIR metadata and provenance | Local | No | Supported | Advanced |
| [30](lesson_30_compose_meta_workflows.md) | Workflow composition and meta-tasks over other engines | Local | Engines (optional) | Limited | Advanced |
| [31](lesson_31_run_other_engines_workflows_with_meta_tasks.md) | Meta-tasks: adapters, checkpoints, failure phases | Local | Engines (optional) | Supported | Advanced |
| [32](lesson_32_export_and_validate_common_workflow_language.md) | CWL v1.2 export and execution | Local | Optional validator | Supported | Advanced |
| [33](lesson_33_compute_continuum_operations.md) | Compute continuum synthesis | Local mock | No | Supported | Advanced |
| [34](lesson_34_operate_deploy_and_troubleshoot_dagonstar.md) | Operations, packaging, CI | Local | No | Limited | Advanced |
| [35](lesson_35_capstone_every_task_type_with_evidence.md) | Capstone: every task type | Local emulation | No | Supported | Advanced |

### Modules and effort

- Module 0, orientation: Lesson 00, about 20 minutes.
- Module 1, constructing the graph: Lessons 01–04, about 95 minutes.
- Module 2, execution and data movement: Lessons 05–08, about 110 minutes.
- Module 3, structured task models: Lessons 09–16 (native, web, LLM, FaaS, IoT, and three agentic lessons), about 270 minutes.
- Module 4, distributed infrastructure: Lessons 17–28 (Docker, Apptainer, Kubernetes, Nomad, SSH, cloud, Slurm, BeeOND, pluggable ad-hoc file systems and streams, volume tasks, pre-staging, data movers), about 430 minutes plus optional site setup.
- Module 5, FAIR composition, interoperability, and operations: Lessons 29–35 (including meta-tasks over other engines in Lesson 31), about 310 minutes.
- [Optional integrations](integrations/README.md) are selected by research need and maturity.

Every registered `TaskType` and every inventoried supported feature is mapped to a lesson, a runnable example,
and a test target in [`coverage.json`](coverage.json); `python tools/validate_tutorial_coverage.py` checks the
mapping, the evidence paths, and the notebook. Evidence levels distinguish local execution, mocked contracts,
portable emulation, and optional live integration.

The [course notebook](DAGonStar_tutorial.ipynb) includes executable verification
for every Lesson 00–35 in local Jupyter and Google Colab. For infrastructure
Lessons 17–28 it runs the lesson scripts, which mock Docker, Kubernetes, Nomad,
SSH, cloud, and scheduler clients or use portable emulation; live Docker,
Apptainer, Kubernetes, Nomad, SSH, cloud, Slurm, BeeOND, and transfer-service
claims still require their real backends. Lessons 14–16 use the deterministic
`mock` agent provider and never contact a model endpoint.

[Open the complete course notebook in Google Colab](https://colab.research.google.com/github/DagOnStar/dagonstar/blob/main/docs/tutorial/DAGonStar_tutorial.ipynb).

## Run and verify examples

From the repository root, install as described in Lesson 00, then run `python examples/tutorial/lesson_NN_....py`; every lesson from 00 to 35 has a script with the matching number, and `python tools/run_local_examples.py` runs them all. Local scripts create isolated temporary scratch directories, make exact assertions, and exit nonzero on failure. Run `python tools/validate_tutorial.py` for structure and internal-link checks and `python tools/validate_tutorial_coverage.py` for feature coverage.

Use the [glossary](resources/glossary.md), [troubleshooting guide](resources/troubleshooting.md), and [teaching notes](resources/teaching_notes.md) throughout.

## Assessment model

Each lesson asks the learner to make a prediction, run a deterministic check,
interpret the resulting evidence, and state a limitation. A successful command
is therefore necessary but not sufficient: assessment also requires a correct
causal explanation. The controlled experiments may be used as formative
exercises; a capstone submission should retain commands, versions, outputs, and
an explicit account of which claims were and were not tested.

Earlier experimental lesson numbers have been retired. Stable feature guides
and the [optional-integration case studies](integrations/README.md) preserve
advanced material without competing with the canonical sequence.

## Contributing

Documentation describes observed implementation, not desired behavior. Preserve the lesson template and ordering, keep external infrastructure out of the mandatory local path, update the notebook and indexes with lesson changes, and run repository tests plus tutorial validation. See [AGENTS.md](../../AGENTS.md).
