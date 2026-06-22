# DAGonStar Tutorial Sequence

This tutorial contains fourteen incremental lessons. The lessons are designed to be
read in order and to remain consistent with the current DAGonStar implementation.

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
