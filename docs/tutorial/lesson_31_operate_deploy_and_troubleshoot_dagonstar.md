# Lesson 31: Operate, Deploy, and Troubleshoot DAGonStar

> **Track:** Advanced
> **Runtime:** Local
> **Colab:** Limited
> **Estimated effort:** approximately 40 minutes

## Learning outcomes

After completing this lesson, you will be able to:

- register a workflow with the optional DAGon service using a mocked HTTP API;
- explain how runner subprocesses find the `dagon` package;
- check packaging, console scripts, platform helpers, and CI evidence.

## Prerequisites

- [Lesson 30](lesson_30_compute_continuum_operations.md), or equivalent concepts.
- No running DAGon service; HTTP calls are mocked.

## Scientific scenario

A laboratory moves from notebooks to a shared deployment with continuous integration. Operators need to know what each component requires and how to diagnose failures.

## Conceptual model

The optional service API (`[dagon_service] use = True`) registers workflows and tasks over HTTP. `runner_environment()` appends the package root to `PYTHONPATH` so native, FaaS, IoT, and agent runners work from scratch directories. `bash_executable()` and `shell_path()` keep launchers portable. `pip install -e .` installs the `dagon-agent-runner` console script. CI runs unit tests, examples, and tutorial validation on Linux, macOS, Windows, Rocky Linux, and Debian arm64.

New terms are collected in the [glossary](resources/glossary.md).

## Build the workflow

Read [`examples/tutorial/lesson_31_operations.py`](../../examples/tutorial/lesson_31_operations.py), [`tools/run_local_examples.py`](../../tools/run_local_examples.py), and the [platform support guide](../platform_support.md).

## Run the example

From the repository root:

~~~bash
python examples/tutorial/lesson_31_operations.py
python tools/run_local_examples.py
~~~

## Expected result

The mocked service assigns workflow id 7, the JSON round trip keeps the tasks and the explicit `hello → report` edge, the runner environment keeps user entries first, and the console script answers `--help` when installed. The example runner reports every listed example as `ok`.

## Verify

~~~bash
python examples/tutorial/lesson_31_operations.py
python -m unittest tests.test_runtime_env tests.test_platform_support tests.test_packaging -v
~~~

Local results are not CI results; consult the CI run for other platforms.

## What DAGonStar did

DAGonStar registered the workflow and task through the mocked API, serialized and restored the graph, and built a runner environment without shadowing user paths.

## Controlled experiment

Predict what happens when `use = True` but the route is unreachable; patch `requests.head` to raise `ConnectionError` and interpret the log. Then uninstall the console script in a virtual environment and observe the skip message.

## Common problems and diagnosis

`ModuleNotFoundError: dagon` in a runner means the environment was overridden. On Windows, set `DAGON_BASH` if Git Bash is not detected. See [troubleshooting](resources/troubleshooting.md).

## Scientific practice

Record package version, Python version, platform, installed extras, and CI run identifiers.

## Summary

Operations combine optional services, portable launchers, packaging, and CI evidence.

## Next lesson

Next, combine every task type and every evidence surface in the capstone. Return to the [syllabus](README.md) at any time.
