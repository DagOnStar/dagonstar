# DAGonStar tutorial examples

These scripts are authoritative runnable companions to the redesigned curriculum. Run them from the repository root after `python -m pip install -e .`.

~~~bash
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
~~~

Lessons 01–09 use local files and processes. Lessons 10 and 11 bind short-lived deterministic mock services to `127.0.0.1` on an available port and close them cleanly. They use no public service or real credential. Every script uses an isolated temporary scratch directory and exact assertions.

Lessons 12–14 use repository unit tests for deterministic structural verification; optional live Docker, SSH, and Slurm checks require site infrastructure. Lesson 15 uses FAIR tests, Lesson 16 uses the transversal-dependency test, and Lesson 17 uses the CWL example test. See the [tutorial syllabus](../../docs/tutorial/README.md) for commands and limitations.

The older `lesson_12_llm_tasks.py` and `lesson_13_web_tasks.py` remain as implementation sources for compatibility; canonical wrappers expose them as Lessons 11 and 10 respectively.
