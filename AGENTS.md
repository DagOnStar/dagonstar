# AGENTS.md

Guidance for AI agents and maintainers working in this repository.

## Repository purpose

DAGonStar is a Python workflow engine for orchestrating DAG-based jobs across
local, remote, Slurm, Docker, cloud, and data-staging environments.

## Working principles

- Preserve existing research examples unless a change is clearly required.
- Do not commit real credentials, tokens, host-specific passwords, SSH keys, or
  cloud secrets.
- Treat `dagon.ini.sample` as documentation, not as a private configuration file.
- Keep fixes conservative: many examples encode historical research workflows.
- Prefer small, reviewable changes with an explicit verification command.
- Keep `dagon/fair/` optional and dependency-free by default; FAIR metadata
  must never include credentials. Update FAIR tests, examples, tutorials, and
  affected documentation when its behavior changes.

## Important paths

- `dagon/`: core library code.
- `dagon/task.py`: base task model, dependency discovery, staging integration.
- `dagon/__init__.py`: `Workflow`, stager logic, shared enums.
- `dagon/batch.py`: local batch and Slurm tasks.
- `dagon/remote.py`: SSH and cloud-backed tasks.
- `dagon/docker_task.py`: local and remote Docker tasks.
- `dagon/communication/`: SSH/SCP/Globus/SKYCDS transfer helpers.
- `examples/`: runnable examples and tutorial material.
- `dagon.ini.sample`: safe sample configuration.

## Verification

At minimum, run:

```bash
python -m unittest discover -s tests -v
python -m py_compile dagon/*.py dagon/api/*.py dagon/communication/*.py dagon/ftp_publisher/*.py dagon/peer2peer/*.py
```

If packaging metadata changed, also run:

```bash
python -m pip install -e .
```

If behavior changed, run the smallest relevant example and document the command.

When adding or changing features, add a unit test under `tests/` for the expected
stable behavior. Prefer tests that do not require external services. For Docker,
Slurm, SSH, Globus, SKYCDS, or cloud providers, test local command generation or
configuration validation separately from live integration behavior.

## Security notes

- Credentials must come from environment variables, local ignored config, a
  secret manager, or user-provided runtime configuration.
- Never add token-looking defaults to Python modules or sample config.
- Be careful with shell command construction. Existing code builds many commands
  from strings; quote new path/user inputs defensively.

## Documentation standards

- Authoritative consistency clause: all repository documentation, including
  `README.md`, `AGENTS.md`, and every file under `docs/`, must remain consistent
  with the current software implementation. Do not document aspirational,
  planned, or preferred behavior as if it already exists. If behavior is not
  implemented, mark it explicitly as future work, an optional integration, or a
  manual/site-specific procedure.
- Authoritative maintenance clause: whenever implementation behavior, public
  APIs, configuration, packaging, dependencies, examples, tests, or operational
  assumptions change, update all affected examples and tutorials in `examples/`
  and `docs/tutorial/`.
- Authoritative documentation clause: update all involved documentation for the
  changed behavior, including relevant files in `docs/`, example READMEs, and
  contributor guidance when applicable.
- Authoritative README status clause: update the "Project status and quality
  assessment" section in `README.md` whenever a change materially affects test
  coverage, typed interfaces, shell-command safety, optional dependencies,
  security posture, packaging, or overall project quality.
- Keep `README.md` focused on installation, configuration, quick start, examples,
  development, and troubleshooting.
- Keep example-specific setup in the relevant `examples/**/README.md`.
- Mention optional integrations and credentials without embedding private values.

## Known quality gaps

- The project has a unit test suite and CI baseline, including initial
  checkpoint, staging, packaging-extra, and core workflow checks, but coverage is
  not comprehensive yet. Prioritize command rewriting, local batch integration,
  failure modes, and mocked external-service boundaries.
- Optional integrations have package extras, while `requirements.txt` remains a
  full development/demo environment. Preserve lazy imports and explicit extras
  for Docker, cloud, Globus, API, and other service-specific dependencies.
- Several shell command paths still need safer quoting and command construction
  helpers. Preserve and expand the existing staging quoting helpers.
- Public APIs have initial type annotations; add more when touching workflow,
  task, configuration, and staging interfaces.
- Some legacy examples may require external services or site-specific software.
