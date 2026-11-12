# Platform support and CI/CD

This page states which operating systems the DAGonStar core is tested on, how
local execution works on each, and what the CI/CD workflow
(`.github/workflows/ci.yml`) does.

## Tested platforms

| Platform | CI environment | Python | What runs |
| --- | --- | --- | --- |
| Ubuntu Linux | GitHub-hosted `ubuntu-24.04`, `ubuntu-latest` (x86-64) | 3.8 (24.04), 3.10, 3.12, 3.13 | unit tests, compile, local examples |
| macOS | GitHub-hosted `macos-latest` (Apple silicon) | 3.10, 3.13 | unit tests, compile, local examples |
| Windows | GitHub-hosted `windows-latest` (x86-64) with Git Bash | 3.10, 3.13 | unit tests, compile, local examples |
| Rocky Linux 9 | `rockylinux/rockylinux:9` container | 3.9 (system), 3.12 (AppStream) | unit tests, local examples |
| Raspberry Pi (64-bit) | `debian:bookworm` container on a native arm64 runner | 3.11 (system) | unit tests, local examples |

"Local examples" are the self-contained scripts run by
`python tools/run_local_examples.py`: tutorial lessons 01–11 and the FAIR,
FaaS, IoT, and LLM mock examples. They use only local processes, temporary
scratch directories, and loopback mock services.

The Raspberry Pi job exercises the userland of 64-bit Raspberry Pi OS, which is
Debian bookworm for arm64 (aarch64). It runs on an arm64 server CPU, not on
Raspberry Pi hardware, and does not cover 32-bit (armhf) Raspberry Pi OS.
Rocky Linux runs as root in a container on an Ubuntu kernel.

Not covered by CI on any platform: live Docker, Apptainer, Kubernetes, Nomad,
SSH, multi-node Slurm, real BeeGFS/BeeOND, Globus, SKYCDS, DynoStore, or cloud
services. Those paths are tested through command generation and mocks only (see
the [developer guide](developer_guide.md)). The one exception is the
`beeond-slurm` job described below, which runs single-node Slurm with an
emulated BeeOND site.

### BeeOND on Slurm (emulated site)

The `beeond-slurm` job installs Ubuntu's `slurm-wlm` and `munge` on an
`ubuntu-24.04` runner and configures a single-node cluster with
`tools/ci/slurm/setup-slurm-beeond.sh`. Its Slurm Prolog
(`tools/ci/slurm/beeond-prolog.sh`) creates a job-owned directory at
`/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}` for jobs whose comment
contains `beeond-fs`, and its Epilog (`beeond-epilog.sh`) deletes it when the job
ends, as a BeeOND site does. `tools/ci_beeond_slurm.py` then checks, with real
`sbatch`, `srun --jobid` steps, and `--signal`:

- a per-task volume is persisted and read downstream through `workflow://`;
- a failing command's volume is still persisted;
- a per-workflow holder volume is shared by two steps and persisted at the end;
- the `signal_grace` warning stops a long command and persists its volume;
- every volume the site created was destroyed at job end.

The emulated mount is an ordinary local directory: BeeGFS performance, striping,
and multi-node sharing are not tested. The setup scripts are for CI runners only.
To run the checks on a cluster you control:

```bash
python tools/ci_beeond_slurm.py --partition <partition> --scratch <shared-dir>
```

## Local execution on each platform

DAGonStar launchers are POSIX `bash` scripts. The interpreter is chosen by
`dagon.platform_support.bash_executable()`:

1. the `DAGON_BASH` environment variable, if set, on every platform;
2. on Linux, macOS, and other POSIX systems: the first `bash` on `PATH`
   (for example Homebrew's bash 5 on macOS), otherwise `/bin/bash`;
3. on Windows: the `bash.exe` of Git for Windows (located from `git` on
   `PATH` or the standard install folders), then MSYS2
   (`C:\msys64\usr\bin\bash.exe`), Cygwin (`C:\cygwin64\bin\bash.exe`), and
   finally `bash` on `PATH`. The WSL launcher under `C:\Windows` is skipped
   because it runs in a separate Linux filesystem namespace.

If no interpreter is found, local tasks fail with an error that names
`DAGON_BASH`.

On Windows, DAGonStar also:

- converts scratch and working directories to forward-slash form
  (`C:/Users/me/scratch/...`), which both Python and the bash variants above
  accept;
- writes launcher scripts with LF line endings so bash does not see `\r`;
- resolves `workflow://` producer paths with `/` separators.

Task commands still run inside bash, so they must use POSIX shell syntax and
tools available in that bash environment (Git Bash ships `mkdir`, `cp`, `cat`,
`printf`, `sed`, and similar). Windows-only commands are not translated.
The `LINK` data mover uses `ln -s`. DAGonStar starts Windows launchers with
`MSYS` and `CYGWIN` set to `winsymlinks:native` unless you set them yourself, so
real symbolic links are created when Windows permits it (developer mode or an
elevated shell); otherwise `ln -s` falls back to copying. Producer paths in
`workflow://` references are POSIX paths relative to the producer's scratch
directory on every platform.

### Windows quick start

```powershell
winget install --id Git.Git -e
py -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
python tools/run_local_examples.py
```

To use a specific bash, for example MSYS2:

```powershell
$env:DAGON_BASH = "C:\msys64\usr\bin\bash.exe"
```

### Raspberry Pi quick start (64-bit Raspberry Pi OS)

```bash
sudo apt-get install -y git python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python tools/run_local_examples.py
```

### Rocky Linux quick start

```bash
sudo dnf install -y git python3.12 python3.12-pip
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python tools/run_local_examples.py
```

## CI/CD workflow

The workflow runs on pushes to `main`, `master`, and `development`, on pull
requests, on `v*` tags, and on manual dispatch.

| Job | Purpose |
| --- | --- |
| `quality` | Ruff and mypy on the typed helper modules, tutorial validation, notebook JSON check, `bash -n` on the CI shell scripts. |
| `test` | Unit tests, `compileall`, and local examples on Ubuntu, macOS, and Windows. |
| `rocky-linux` | Unit tests and local examples on Rocky Linux 9. |
| `raspberry-pi` | Unit tests and local examples on Debian bookworm arm64. |
| `beeond-slurm` | BeeOND unit tests and live per-task, per-workflow, failure, and signal persistence checks on single-node Slurm with an emulated BeeOND site. |
| `build` | Builds sdist and wheel, runs `twine check --strict`, imports the wheel in a clean virtual environment, and uploads `dist/` as an artifact. On a tag, it checks that the tag equals `v` + the `setup.cfg` version. |
| `release` | On a `v*` tag only: creates a GitHub release with generated notes and attaches the distributions. |
| `publish-pypi` | On a `v*` tag only, and only when the repository variable `PYPI_PUBLISH` is `true`: publishes to PyPI with trusted publishing (no stored token). |

### Publishing a release

1. Set `version` in `setup.cfg`, for example `1.0.3`, and merge to `main`.
2. Tag and push: `git tag v1.0.3 && git push origin v1.0.3`.
3. The workflow tests every platform, builds, and creates the GitHub release.

PyPI publishing is off until a maintainer sets it up once: add a trusted
publisher on PyPI for this repository, workflow `ci.yml`, and environment
`pypi`; create the `pypi` environment in the repository settings; then set the
repository variable `PYPI_PUBLISH=true`. No PyPI token is stored in the
repository.
