# Meta-tasks with real workflow engines: live verification (19 November 2026)

This record covers [`TaskType.META`](../meta_tasks.md) driving unmodified,
real workflow engines. The runs were manual and are not part of CI; CI runs the
engine-free tests (`command` and `mock` adapters, generated-command checks) and
skips the live tests when an engine is absent.

## Host and software

| Item | Value |
|---|---|
| Host | macOS 26.6.2, arm64, Python 3.12.10 (DAGonStar process) |
| Snakemake | 9.27.2 (pip, separate virtual environment on `PATH`) |
| Parsl | 2026.11.16 (pip, same virtual environment; `DAGON_META_PARSL_PYTHON`) |
| StreamFlow | 0.2.0rc3 (pip, its own virtual environment; 0.1.6, the latest non-pre-release, was not used) |
| cwltool | 3.1.20260413085819 (system) |
| Nextflow | not run (see below) |

Each engine was installed without changes. DAGonStar did not install, patch, or
configure any of them.

## Workload

`examples/meta/meta_engines.py` and `tests.test_meta_task.MetaLiveEngineTests`
build `producer (batch) -> count (meta) -> report (batch)`. The producer writes
a text; the meta-task runs the same word count written natively for each
engine (`examples/meta/workflows/`: `Snakefile`, `wordcount_parsl.py`,
`main.nf`, `wordcount.cwl`); the report reads
`workflow:///count/outputs/counts.tsv`. The scripts check the exact counts.

```bash
PATH=<engine bins>:$PATH python3 examples/meta/meta_engines.py --parsl-python <venv>/bin/python
PATH=<engine bins>:$PATH DAGON_META_PARSL_PYTHON=<venv>/bin/python python3 -m unittest tests.test_meta_task -v
```

## Results

| Engine | Result | Engine run time (meta_result `duration_seconds`) | Output path |
|---|---|---|---|
| Snakemake | passed (example and live test) | 3.2 s | `run/results/counts.tsv` → `outputs/counts.tsv` |
| Parsl (threads executor, function mode) | passed | 0.6 s | `run/results/counts.tsv` → `outputs/counts.tsv` |
| StreamFlow (generated StreamFlow file, local deployment) | passed | 1.0 s | `engine_output: counts` from the printed CWL output object |
| cwltool (`--no-container`) | passed | 0.9 s | `engine_output: counts` |
| Nextflow | not executed | — | — |

The `tests.test_meta_task` suite ran 34 tests with one skip (Nextflow) and no
failures in this environment.

Observed during the runs:

- The first Parsl attempt failed because the driver was started as
  `python -m dagon.meta.parsl_driver`, which imported DAGonStar's dependencies
  into the Parsl interpreter. The driver is now self-contained and started by
  path; the rerun passed.
- One Snakemake run in the first batch spent about 15 minutes between the end
  of the engine (3 s) and the start of the downstream task; a standalone rerun
  of the same example took 12 s end to end. The cause was not identified and
  the delay did not recur.

## Not verified

- **Nextflow**: downloading the Nextflow launcher was not permitted in this
  session, so `main.nf` and the live test were not executed. The adapter's
  command line and parameter file are covered by
  `tests.test_meta_task.MetaAdapterCommandTests.test_nextflow`. Install
  Nextflow (Java 17+) and run
  `python examples/meta/meta_engines.py --engine nextflow` to close this gap.
- Engine-side remote execution (Nextflow executors, Snakemake executor
  plugins, Parsl providers, StreamFlow remote deployments) was not exercised.
- Linux and Windows live runs were not performed.
