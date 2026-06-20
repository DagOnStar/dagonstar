# Developer Guide

This guide is for contributors and agents modifying DAGonStar.

## Ground rule: implementation first

Documentation, examples, and tests must describe the current implementation in
this repository. If intended behavior differs from current behavior, either
implement and test it or label it explicitly as future work.

## Development setup

```bash
git clone https://github.com/DagOnStar/dagonstar.git
cd dagonstar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Install optional integration dependencies only when needed:

```bash
python -m pip install -e ".[docker]"
python -m pip install -e ".[cloud]"
python -m pip install -e ".[globus]"
python -m pip install -e ".[api]"
python -m pip install -e ".[all]"
```

## Test commands

Run unit tests:

```bash
python -m unittest discover -s tests -v
```

Compile source and tests:

```bash
python -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py tests/*.py
```

When packaging metadata changes:

```bash
python -m pip install -e .
```

## Test strategy

The current unit tests deliberately avoid external services. They verify stable
core behavior:

- configuration parsing;
- workflow defaults;
- dependency discovery;
- cycle detection;
- serialization;
- runtime-secret validation.

When adding features:

1. Add a unit test for local deterministic behavior.
2. Mock external services where useful.
3. Keep Docker/Slurm/SSH/Globus/cloud tests separate from generic CI unless the
   environment is explicitly provisioned.
4. Document manual integration verification commands in the change notes.

The test suite is intentionally a starting point, not a complete quality gate.
It now includes checkpoint reuse, staging command generation, and packaging
extras checks. Priority areas for further expansion are command rewriting for
`workflow://` references, local batch integration workflows, failure-mode tests,
and mocked boundaries for Docker, Slurm, SSH, Globus, cloud, and API
integrations.

## Adding a new task type

To add a task type:

1. Add a value to `TaskType`.
2. Add a mapping in `tasks_types`.
3. Implement a concrete task class.
4. Ensure the class initializes the base `Task` correctly.
5. Override `on_execute()` or other environment-specific hooks.
6. Add unit tests for construction and dependency behavior.
7. Update [reference_guide.md](reference_guide.md), [architecture.md](architecture.md),
   and relevant tutorials.

## Modifying dependency resolution

Dependency resolution is implemented primarily in `Task.pre_run()` and
`Task.pre_process_command()`.

Be careful with:

- parsing `workflow://` references;
- same-workflow versus transversal references;
- reference counts used by garbage collection;
- recursive calls to `workflow.make_dependencies()` for parallel modes;
- service-backed task lookup when the DAGon service is enabled.

Any change here should include tests for:

- same-workflow references;
- missing references;
- cycles;
- command rewriting;
- reference counts.

## Modifying staging

Staging logic lives in `Stager.stage_in()` and `Stager.generate_command()`.

Risks:

- shell quoting;
- remote/local path distinction;
- external command availability;
- differences between files, directories, and glob patterns;
- service-specific credentials.

Prefer adding helpers and unit tests before broad rewrites.

New staging or command-generation code should avoid raw string concatenation for
paths or user-controlled values. Prefer explicit quoting helpers and tests that
cover spaces, special characters, missing files, directories, and glob patterns.

## Security expectations

- Never add real credentials to source files, docs, sample config, tests, or CI.
- Use placeholders in examples.
- Read runtime secrets from environment variables or local ignored files.
- Avoid logging secrets.
- Quote shell arguments defensively in new code.

## Documentation expectations

When changing implementation:

- update the relevant documentation file in `docs/`;
- update `README.md` if the change affects onboarding;
- update `AGENTS.md` if contributor policy changes;
- add or update tests.

Scientific documentation should be precise enough for a researcher to reproduce
the computational method and honest about operational assumptions.

## Current technical debt

- Automated tests cover core local behavior plus initial checkpoint, staging,
  and packaging-extra behavior; broader integration and failure-mode coverage is
  still needed.
- Public APIs have initial annotations in workflow, task, configuration, and
  staging code; continue extending type coverage when touching public methods.
- Shell command construction has initial staging quoting helpers but should be
  progressively hardened throughout task and integration code.
- Optional integrations now have package extras, while `requirements.txt` remains
  a full development/demo environment. Continue preserving lazy imports and
  explicit extras for Docker, cloud, Globus, API, and other service-specific
  requirements.
- Some legacy examples require site-specific data or services.
