# Configuration

## FAIR environment capture

FAIR mode has no required configuration key. Set `FairProfile.capture_environment`
to an explicit variable-name allowlist when needed. Secret-like names (token,
password, private key and cloud credential markers) are redacted even then;
raw configuration secrets are never exported.
DAGonStar reads configuration from an INI file, normally named `dagon.ini`.
The sample file [../dagon.ini.sample](../dagon.ini.sample) documents the
configuration keys currently recognized by the repository.

Configuration is loaded by `dagon.config.read_config()`, which returns a nested
dictionary of strings:

```python
from dagon.config import read_config

cfg = read_config("dagon.ini")
scratch = cfg["batch"]["scratch_dir_base"]
```

`Workflow` can also receive an in-memory dictionary:

```python
from dagon import Workflow

workflow = Workflow("Experiment", config={
    "batch": {"scratch_dir_base": "/tmp/", "run_base": "", "threads": "1"},
    "dagon_service": {"use": "False"},
    "slurm": {"partition": ""},
})
```

This is useful for tests or programmatic workflow construction.

## Minimal configuration

For local batch workflows, this is enough:

```ini
[dagon_service]
route = http://localhost:57000
use = False

[ftp_pub]
ip = localhost

[batch]
scratch_dir_base=/tmp/
run_base=
remove_dir=False
threads=1

[slurm]
partition=
```

The current implementation provides safe defaults for missing optional
`dagon_service` and `ftp_pub` values, but production workflows should keep these
sections explicit for clarity.

## `[dagon_service]`

```ini
[dagon_service]
route = http://localhost:57000
use = False
```

When `use = True`, `Workflow` attempts to register itself with the DAGon service
through `dagon.api.API`. The service is used for workflow/task registration,
status updates, and some transversal workflow lookups.

If the service is disabled, DAGonStar runs as a local in-process workflow engine.
This is the recommended mode for introductory examples and unit tests.

## `[ftp_pub]`

```ini
[ftp_pub]
ip = localhost
```

This section is used by transversal workflow handling when task data must be
downloaded from a host registered through the service. The current defaults are:

- host: `localhost`
- user: `anonymous`
- password: empty string

Do not store production passwords in the repository. Use local ignored config,
environment variables, or a site-specific secret management process.

## `[dagon_ip]`

```ini
[dagon_ip]
ip = localhost
```

This value is present in the sample configuration for service/node-related
workflows. It is not required for the basic local examples.

## `[batch]`

```ini
[batch]
scratch_dir_base=/tmp/
run_base=
remove_dir=False
threads=1
```

Keys:

- `scratch_dir_base`: base directory used to create task scratch directories.
- `run_base`: optional format for grouping a workflow run under a subdirectory.
  The implementation supports timestamp formatting and `__MILLIS__`.
- `remove_dir`: currently documented as a configuration intent; task garbage
  collection is controlled primarily by task reference counts and task flags.
- `threads`: used by staging command generation for parallel movement modes.

Example run grouping:

```ini
[batch]
scratch_dir_base=/tmp/dagon
run_base=%Y%m%d-%H%M%S-__MILLIS__
threads=4
```

## `[slurm]`

```ini
[slurm]
partition=
```

The `partition` value is used when generating Slurm staging commands. Slurm task
objects can also receive Slurm parameters directly:

```python
task = DagonTask(
    TaskType.SLURM,
    "model",
    "./run_model.sh",
    partition="compute",
    ntasks=16,
    time="02:00:00",
)
```

## Cloud provider sections

## LLM provider sections

`TaskType.LLM` reads an OpenAI-compatible provider from a section named `[llm.<name>]`; multiple provider sections are supported. See [LLM Tasks](llm_tasks.md) for the exact request and input-file behavior.

```ini
[llm.example]
endpoint=https://api.example.org
api_key_env=DAGON_LLM_EXAMPLE_API_KEY
model=example-chat-model
```

Keep keys out of committed configuration. `api_key_env` reads the named runtime environment variable; `api_key` is available only for a local ignored config.

## Cloud provider sections

The sample includes:

```ini
[ec2]
key=<aws_access_key_id>
secret=<aws_secret_access_key>
region=

[digitalocean]
key=

[gce]
key=
secret=
project=
```

Cloud tasks use Apache Libcloud through `dagon.cloud`. Values are provider
specific and should be treated as secrets. The sample placeholders must be
replaced only in local, non-committed configuration files.

Install cloud dependencies with:

```bash
python -m pip install "dagonstar[cloud]"
```

## Logging sections

The sample includes a standard Python `logging.config.fileConfig` setup:

```ini
[loggers]
keys=root

[handlers]
keys=stream_handler

[formatters]
keys=formatter

[logger_root]
level=DEBUG
handlers=stream_handler

[handler_stream_handler]
class=StreamHandler
level=DEBUG
formatter=formatter
args=(sys.stderr,)

[formatter_formatter]
format=%(asctime)s %(name)-12s %(levelname)-8s %(message)s
```

When `Workflow` is created without an explicit `config` dictionary, it calls
`fileConfig(config_file)`. Therefore, a file-based configuration should include
valid logging sections.

## Runtime environment variables

SKYCDS credentials are intentionally not hard-coded. The current implementation
reads:

```bash
export DAGON_SKYCDS_CLIENT_TOKEN=...
export DAGON_SKYCDS_CATALOG_TOKEN=...
export DAGON_SKYCDS_API_TOKEN=...
export DAGON_SKYCDS_IP=...
```

The Globus transfer token placeholder is read from:

```bash
export DAGON_GLOBUS_TRANSFER_TOKEN=...
```

Current Globus transfer setup primarily uses the OAuth flow in
`GlobusManager.__init__`, which prompts the user to authorize a native app.

Install optional integration dependencies as needed:

```bash
python -m pip install "dagonstar[docker]"
python -m pip install "dagonstar[globus]"
python -m pip install "dagonstar[api]"
python -m pip install "dagonstar[all]"
```

## Configuration rules for reproducible science

For scientific workflows, configuration should be versioned carefully:

- Commit safe templates such as `dagon.ini.sample`.
- Do not commit real secrets.
- Record the configuration values that affect scientific reproducibility:
  scratch layout, model parameters, container images, cloud instance types, and
  Slurm resource requests.
- Keep operational secrets separate from reproducibility metadata.
