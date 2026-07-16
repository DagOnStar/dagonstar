# DAGonStar academic tutorial

This tutorial teaches DAGonStar as a scientific-workflow system: graph construction, execution and recovery, structured task models, distributed infrastructure, then FAIR composition and interoperability. It is intended for graduate students, research software engineers, computational scientists, and advanced undergraduates who know basic Python and shell usage but may be new to workflow semantics.

## Complete-course learning outcomes

After the course you can construct and validate a DAG, distinguish control from data dependencies, inspect staging and execution evidence, select task and backend models, reason about recovery and asynchronous lifecycle, record supported FAIR metadata, compose workflows, and evaluate a CWL v1.2 export's portability boundary.

## Prerequisites

Python 3, a command shell, and a repository checkout are sufficient for the local path. Start with Lesson 00. Docker, SSH, Slurm, DynoStore, cloud, and real web or LLM providers are optional and never required for the core conceptual sequence.

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
| [12](lesson_12_run_a_task_in_docker.md) | Container execution | Docker | Docker daemon | No | Infrastructure |
| [13](lesson_13_run_a_task_on_a_remote_host_with_ssh.md) | Remote execution | SSH | SSH host | No | Infrastructure |
| [14](lesson_14_submit_a_task_through_slurm.md) | Scheduled execution | Slurm | Cluster | No | Infrastructure |
| [15](lesson_15_make_a_workflow_fair_by_design.md) | FAIR metadata and provenance | Local | No | Supported | Advanced |
| [16](lesson_16_compose_meta_workflows.md) | Workflow composition | Local | No | Limited | Advanced |
| [17](lesson_17_export_and_validate_common_workflow_language.md) | CWL v1.2 capstone | Local | Optional validator | Supported | Advanced |
| [18](lesson_18_compute_continuum_operations.md) | IoT and compute continuum synthesis | Local mock | No | Supported | Advanced |

### Modules and effort

- Module 0, orientation: Lesson 00, about 20 minutes.
- Module 1, constructing the graph: Lessons 01–04, about 95 minutes.
- Module 2, execution and data movement: Lessons 05–08, about 110 minutes.
- Module 3, structured task models: Lessons 09–11, about 90 minutes.
- Module 4, distributed infrastructure: Lessons 12–14, about 115 minutes plus site setup.
- Module 5, FAIR composition and interoperability: Lessons 15–18, about 160 minutes.
- [Optional integrations](integrations/README.md) are selected by research need and maturity.

The [course notebook](DAGonStar_tutorial.ipynb) includes executable verification
for every Lesson 00–18 in local Jupyter and Google Colab. For infrastructure
Lessons 12–14 it runs deterministic construction, quoting, and command-generation
tests; live Docker, SSH, and Slurm claims still require their real backends.
Lesson 18 uses the bounded, credential-free IoT mock and focused contract tests.

[Open the complete course notebook in Google Colab](https://colab.research.google.com/github/DagOnStar/dagonstar/blob/main/docs/tutorial/DAGonStar_tutorial.ipynb).

## Run and verify examples

From the repository root, install as described in Lesson 00, then run `python examples/tutorial/lesson_NN_....py`. Local scripts create isolated temporary scratch directories, make exact assertions, and exit nonzero on failure. Run `python tools/validate_tutorial.py` for structure and internal-link checks.

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
