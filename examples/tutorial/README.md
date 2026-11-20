# DAGonStar tutorial examples

These scripts are the authoritative runnable companions to the 36-lesson
curriculum (Lessons 00–35). Each script carries the number of its lesson. Run
them from the repository root after `python -m pip install -e .`:

~~~bash
python examples/tutorial/lesson_00_environment_check.py
python examples/tutorial/lesson_01_first_local_task.py
python examples/tutorial/lesson_02_build_a_dag.py
python examples/tutorial/lesson_03_workflow_data_dependencies.py
python examples/tutorial/lesson_04_validate_and_fix_cycles.py
python examples/tutorial/lesson_05_scratch_launchers_and_logs.py
python examples/tutorial/lesson_06_data_staging.py
python examples/tutorial/lesson_07_checkpoint_and_resume.py
python examples/tutorial/lesson_08_asynchronous_execution.py
python examples/tutorial/lesson_09_native_python_tasks.py
python examples/tutorial/lesson_10_web_tasks.py
python examples/tutorial/lesson_11_llm_tasks.py
python examples/tutorial/lesson_12_faas_tasks.py
python examples/tutorial/lesson_13_iot_tasks.py
python examples/tutorial/lesson_14_agentic_specification.py
python examples/tutorial/lesson_15_agentic_tools_and_guardrails.py
python examples/tutorial/lesson_16_agentic_evaluation_and_checkpoints.py
python examples/tutorial/lesson_17_docker_tasks.py
python examples/tutorial/lesson_18_apptainer_tasks.py
python examples/tutorial/lesson_19_kubernetes_tasks.py
python examples/tutorial/lesson_20_nomad_tasks.py
python examples/tutorial/lesson_21_ssh_remote_tasks.py
python examples/tutorial/lesson_22_cloud_tasks.py
python examples/tutorial/lesson_23_slurm_tasks.py
python examples/tutorial/lesson_24_beeond_storage.py
python examples/tutorial/lesson_25_adhoc_filesystems.py
python examples/tutorial/lesson_26_volume_tasks.py
python examples/tutorial/lesson_27_scheduler_prestaging.py
python examples/tutorial/lesson_28_data_movers.py
python examples/tutorial/lesson_29_fair_by_design.py
python examples/tutorial/lesson_30_meta_workflows.py
python examples/tutorial/lesson_31_meta_tasks.py
python examples/tutorial/lesson_32_cwl_export.py
python examples/tutorial/lesson_33_compute_continuum.py
python examples/tutorial/lesson_34_operations.py
python examples/tutorial/lesson_35_capstone.py
~~~

`python tools/run_local_examples.py` runs all of them, together with the other
self-contained examples, each in a fresh temporary working directory.

Every script uses an isolated temporary scratch directory and exact assertions,
and exits non-zero on failure. None needs `dagon.ini`, credentials, or public
network access:

- Lessons 00–09 use local files and processes.
- Lessons 10 and 11 bind short-lived deterministic mock services to `127.0.0.1`
  on an available port and close them cleanly.
- Lessons 12 and 13 use the built-in FaaS and IoT mock providers.
- Lessons 14–16 write a temporary `dagon.ini` (through
  [`examples/agentic/agentic_common.py`](../agentic/agentic_common.py)) whose
  agent profiles use the deterministic `mock` agent provider.
- Lessons 17–22 mock the Docker client, `subprocess` for Apptainer, the
  Kubernetes API, the Nomad HTTP API, `SSHManager`, and the cloud provider
  import. Lessons 17 and 19 print an explicit skip when the optional `docker`
  or `kubernetes` package is missing.
- Lessons 23 and 27 replace `sbatch` with
  [`mock_scheduler.py`](../dataflow/slurm/mock_scheduler.py); Lesson 24 uses
  portable emulation for BeeOND; Lesson 25 runs an ad-hoc file-system adapter
  defined in the script on a local directory (built-in providers only under
  emulation); Lesson 26 runs volume tasks under portable emulation; Lesson 28 mocks remote tasks and the Globus
  manager.
- Lessons 29–35 run local FAIR, meta-workflow, meta-task (Lesson 31 registers
  a toy engine adapter and emulates Nextflow with the mock engine), CWL, continuum, operations, and
  capstone checks. Lesson 32 runs `cwltool --validate` only when `cwltool` is
  installed, and Lesson 34 checks the `dagon-agent-runner` console script only
  when it is on `PATH`.

Live Docker, Apptainer, Kubernetes, Nomad, SSH, cloud, Slurm, BeeOND, Globus,
SKYCDS, DynoStore, LLM, FaaS, IoT, and agent-provider behaviour is not exercised
by these scripts. See the [tutorial syllabus](../../docs/tutorial/README.md) for
commands, evidence levels, and limitations.

The canonical Lesson 10 and 11 entry points reuse the detailed local mock
implementations in `common/web_mock_lesson.py` and `common/llm_mock_lesson.py`.
Shared helpers live in `common/`; they are not additional numbered lessons.
