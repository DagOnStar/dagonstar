# DAGonStar Tutorial Sequence

This tutorial contains twenty-one incremental lessons. The lessons are designed to be
read in order and to remain consistent with the current DAGonStar implementation.

For an executable Colab-ready companion covering the core local sequence, open
[`DAGonStar_tutorial.ipynb`](DAGonStar_tutorial.ipynb). Later integration
lessons use the linked repository scripts and service-specific instructions.

Most lessons use local batch workflows so they can be verified on a normal
developer machine. Lessons involving Docker, SSH, Slurm, or cloud execution are
explicitly marked as optional integration exercises.

## Lessons

1. [Create a local workflow](lesson_01_local_workflow.md)
2. [Add explicit task dependencies](lesson_02_explicit_dependencies.md)
3. [Use `workflow://` data dependencies](lesson_03_data_dependencies.md)
4. [Inspect scratch directories and generated launchers](lesson_04_scratch_and_launchers.md)
5. [Detect and fix dependency cycles](lesson_05_cycle_detection.md)
6. [Use checkpoint files](lesson_06_checkpointing.md)
7. [Choose data staging modes](lesson_07_data_staging.md)
8. [Run Docker-backed tasks](lesson_08_docker_tasks.md)
9. [Prepare remote and Slurm workflows](lesson_09_remote_and_slurm.md)
10. [Compose meta-workflows](lesson_10_meta_workflows.md)
11. [Launch a workflow asynchronously](lesson_11_asynchronous_launch.md)
12. [Run an LLM task locally](lesson_12_llm_tasks.md)
13. [Execute a web task locally](lesson_13_web_tasks.md)
14. [Execute native Python tasks](lesson_14_native_tasks.md)
15. [Record FAIR metadata and provenance](lesson_15_fair_by_design.md)
16. [Use DynoStore with DAGonStar](lesson_16_using_dynostore.md)
17. [Interoperate with Common Workflow Language](lesson_17_cwl_interoperability.md)
18. [Run a local mock FaaS task](lesson_18_faas_mock.md)
19. [Connect workflow artifacts to FaaS](lesson_19_faas_artifacts.md)
20. [Inspect FaaS FAIR and exports](lesson_20_faas_fair_exports.md)
21. [Configure cloud FaaS profiles safely](lesson_21_faas_cloud_profiles.md)

## Google Colab compatibility

The following is the Colab compatibility statement for every tutorial lesson.
Hosted Colab is a local, ephemeral runtime: use it for the supported lessons,
and treat remote services as separately configured backends.

| Lesson | Colab compatibility | Notes |
|---|---|---|
| 01 Local workflow | Supported | Local batch task. |
| 02 Explicit dependencies | Supported | Local batch tasks. |
| 03 Data dependencies | Supported | `workflow://` works within the runtime. |
| 04 Scratch and launchers | Supported | Use `/content` or Drive for persistence. |
| 05 Cycle detection | Supported | Local structural behavior. |
| 06 Checkpointing | Supported with care | Store checkpoints in Drive to survive resets. |
| 07 Data staging | Partially supported | Local copy works; remote movers need their service. |
| 08 Docker tasks | Not supported in hosted Colab | Requires a Docker daemon. |
| 09 Remote and Slurm | Partially supported | Colab can be an SSH client, not a cluster. |
| 10 Meta-workflows | Supported | Local workflow composition. |
| 11 Asynchronous launch | Supported with care | The runtime can disconnect or reset. |
| 12 Local LLM task | Supported | Uses the included local mock provider. |
| 13 Local web task | Supported | Starts its local service in the runtime. |
| 14 Native Python tasks | Supported | Local Python functions. |
| 15 FAIR metadata and provenance | Supported | Standard-library local metadata exports. |
| 16 DynoStore | Structural example supported | A live run requires a reachable DynoStore deployment and client. |
| 17 CWL interoperability | Export supported | Generation is local; running needs a CWL v1.2 runner. |
| 18–20 Local FaaS and exports | Supported | Credential-free mock provider and local exports. |
| 21 Cloud FaaS profiles | Supported with care | Requires an external deployment, optional SDK, identity, and may incur cost. |

For supported lessons, first choose one installation method in a Colab cell:

```python
!pip install dagonstar                 # packaged stable release
# or
!pip install git+https://github.com/DagOnStar/dagonstar.git  # latest main
```

Clone the repository and use `pip install -e .` when a lesson needs repository
files. See [the Colab guide](../colab.md) for persistence, security, and backend
limitations.

## Verification convention

Each lesson includes a self-contained, copy-pasteable source example, as well as:

- objective;
- concept;
- code;
- expected behavior;
- verification command;
- scientific practice note.

If a lesson requires an external service, verification is split into a local
structural check and an optional live integration check.
