# Running External Scientific Software

Scientific workflows rarely consist only of Python functions. They often wrap
large external programs: compiled models, command-line preprocessors, domain
specific converters, visualization tools, and publication utilities. DAGonStar's
task model is designed for this style of file-oriented scientific computing.

This document explains how to prepare external software tasks, exchange data
between them, use the `workflow://` schema, and write launch scripts that make
external codes reproducible.

## External software prerequisites

Before placing a program inside a DAGonStar task, verify it outside DAGonStar.
For each external tool, record:

- executable path;
- version;
- build/compiler information, if compiled;
- required environment variables;
- required dynamic libraries;
- required input files;
- expected output files;
- working directory assumptions;
- license or access restrictions;
- expected runtime resources.

Example verification:

```bash
which wrf.exe
wrf.exe --help || true
ldd wrf.exe 2>/dev/null || otool -L wrf.exe 2>/dev/null
```

For Python tools:

```bash
python -V
python -m pip freeze
python script.py --help
```

For containerized tools:

```bash
docker run --rm image:tag command --help
```

## Execution environments

DAGonStar can launch external software through several task types:

- `TaskType.BATCH`: local shell command.
- `TaskType.SLURM`: scheduler-submitted shell command.
- `TaskType.DOCKER`: command wrapped in Docker execution.
- `TaskType.CLOUD`: command executed on a cloud-backed remote node.
- `TaskType.LLM`: OpenAI-compatible JSON request; use this for API-based text
  analysis rather than a locally installed command-line program.
- `TaskType.NATIVE`: importable Python function with scalar and staged file bindings.
- `TaskType.WEB`: scratch-local HTTP/HTTPS request with declared response outputs.
- remote batch/Slurm/Docker variants selected by SSH parameters.

Choose the backend according to the scientific software's operational needs:

| Need | Typical backend |
| --- | --- |
| small local utility | `BATCH` |
| compiled HPC model | `SLURM` |
| dependency-heavy tool | `DOCKER` |
| remote instrument/service host | remote `BATCH` |
| elastic compute | `CLOUD` |

## File-based data exchange

DAGonStar's most robust integration pattern is file exchange. Each task:

1. reads files from its working directory or staged inputs;
2. executes external software;
3. writes named output files;
4. downstream tasks refer to those files with `workflow://`.

This pattern works well because most scientific software already communicates
through files: NetCDF, GRIB, CSV, GeoTIFF, JSON, shapefiles, binary restart
files, and logs.

## The `workflow://` schema for external software

When an external program needs a file produced by another task, reference it in
the command:

```python
post = DagonTask(
    TaskType.BATCH,
    "postprocess",
    "python post.py --input workflow:///simulation/output/model.nc --output product.nc",
)
```

During preprocessing, DAGonStar:

1. finds the `workflow://` token;
2. identifies the producer task;
3. adds a dependency;
4. stages the file into the consumer task's `.dagon/inputs/...` area;
5. rewrites the command to use the staged local path.

Use explicit file paths after the task name:

```text
workflow:///producer/path/inside/producer/scratch/file.nc
```

For cross-workflow references:

```text
workflow://WorkflowName/producer/path/file.nc
```

See [The Workflow Schema](the_workflow_schema.md) for the formal description.

## Preparing launcher scripts

For complex software, avoid putting a long command directly into the task string.
Instead, create a small wrapper script and call it from DAGonStar.

Example `run_model.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

input_file="$1"
output_dir="$2"

mkdir -p "$output_dir"

module purge 2>/dev/null || true
module load netcdf 2>/dev/null || true

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

./model.exe --input "$input_file" --output "$output_dir/result.nc"

test -s "$output_dir/result.nc"
```

DAGonStar task:

```python
model = DagonTask(
    TaskType.BATCH,
    "model",
    "bash run_model.sh workflow:///prepare/input/forcing.nc output",
)
```

## Wrapper script checklist

A good wrapper script should:

- fail fast (`set -euo pipefail`);
- print useful diagnostic information;
- create required output directories;
- validate required inputs exist;
- run the external program;
- validate expected outputs exist and are non-empty;
- avoid embedding secrets;
- write logs to predictable files.

Example validation block:

```bash
if [ ! -s "$input_file" ]; then
  echo "Missing input file: $input_file" >&2
  exit 2
fi
```

## Working directories

DAGonStar changes into the task working directory before executing the command.
External software should therefore use paths relative to the task directory when
possible.

Recommended layout:

```text
task scratch/
  input/ or .dagon/inputs/
  output/
  logs/
  config/
```

## Environment modules and activation

HPC systems often use environment modules:

```bash
module purge
module load gcc/12.2 netcdf openmpi
```

Python tools often use virtual environments:

```bash
. /path/to/venv/bin/activate
python tool.py
```

Conda:

```bash
source /path/to/miniconda/etc/profile.d/conda.sh
conda activate environment-name
```

Put this setup in the wrapper script so the task remains reproducible.

## Slurm wrapper pattern

For Slurm tasks, keep the DAGonStar command focused on the model command and pass
resource requests through the task constructor:

```python
task = DagonTask(
    TaskType.SLURM,
    "wrf",
    "bash run_wrf.sh workflow:///real/wrfinput_d01 output",
    partition="compute",
    ntasks=64,
    time="06:00:00",
)
```

The generated `sbatch` command wraps DAGonStar's launcher script. The wrapper
script should still validate inputs and outputs.

## Docker wrapper pattern

For Docker tasks:

```python
task = DagonTask(
    TaskType.DOCKER,
    "map_render",
    "python map2png.py workflow:///post/product.nc output/map.png",
    image="my-lab/map-render:1.0",
)
```

Ensure the container image contains:

- the executable;
- required system libraries;
- Python/R packages;
- fonts or geospatial data needed by renderers;
- shell tools used by wrapper scripts.

## Logs and provenance

External software should produce logs that remain in the task scratch directory:

```bash
./model.exe "$input" "$output" > logs/model.stdout 2> logs/model.stderr
```

Record:

- command line;
- software version;
- input checksums when possible;
- output checksums for critical products;
- runtime environment.

## Error behavior

DAGonStar marks a task failed when the executed command returns an error code or
when the launcher script raises an exception. Wrapper scripts should return
non-zero exit codes when scientific validation fails, even if the external
program exits with zero.

Example:

```bash
if ! ncdump -h output/result.nc >/dev/null; then
  echo "Invalid NetCDF output" >&2
  exit 3
fi
```

## Practical design pattern

For each external software component, create:

1. `prepare_*` task: creates configuration and input files.
2. `run_*` task: executes the external program.
3. `validate_*` task: checks scientific and structural validity.
4. `postprocess_*` task: converts outputs into analysis products.
5. `publish_*` task: exports final artifacts.

Use `workflow://` references between each stage so the data lineage is explicit.
