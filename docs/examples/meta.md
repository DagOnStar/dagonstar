# Meta-task examples

## Purpose

The examples show one scientific step - a word count - written natively for
several workflow engines and run, unmodified, as a single `TaskType.META` task
between two DAGonStar batch tasks. Data enters and leaves the external
workflow only through `workflow://` references.

## DAGonStar mechanisms

- `workflow://` input discovery, staging into `inputs/<name>/`, and hand-over
  as engine-native parameters (Nextflow `params`, Snakemake `config`, Parsl
  keyword arguments, a CWL job document);
- declared output collection into `outputs/<path>`, checked to stay inside the
  scratch directory, with SHA-256 evidence;
- adapters as the only engine-specific code ([adapter interface](../meta_tasks.md#developing-a-new-adapter));
- verified checkpoint reuse and portable emulation with the `mock` engine.

## Run and verify

```bash
python examples/meta/meta_workflow_local.py          # no engine needed
python examples/meta/meta_engines.py                 # every installed engine; others are skipped
python examples/meta/meta_engines.py --engine parsl --parsl-python /path/to/env/bin/python
python -m unittest tests.test_meta_task -v
```

`meta_workflow_local.py` is part of `tools/run_local_examples.py`.
`meta_engines.py` asserts the exact top word for each engine it runs.

## Boundary

The engines are external programs and must be installed separately; DAGonStar
does not install or modify them. The live results recorded for this release
(Snakemake, Parsl, StreamFlow, and cwltool passed; Nextflow was not executed)
are in [the performance record](../performance/meta_engines_2026-11-19.md).
