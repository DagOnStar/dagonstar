# CWL interoperability example

This example defines a three-step DAGonStar workflow and exports it as a
self-contained CWL v1.2 command graph. It is intentionally command-only: it
does not use `workflow://` staging or a DAGonStar-specific remote executor, so
the checked-in CWL document can run with a generic CWL runner.

From the repository root:

```bash
python3 examples/cwl/export_workflow.py --output /tmp/interoperable-workflow.cwl
```

The repository also contains the deterministic generated artifact
[`interoperable-workflow.cwl`](interoperable-workflow.cwl). If `cwltool` is
installed, validate and run either copy:

```bash
cwltool --validate examples/cwl/interoperable-workflow.cwl
cwltool examples/cwl/interoperable-workflow.cwl
```

The two preparation steps may run concurrently. The simulation step consumes
their boolean completion tokens and starts only after both succeed. Those
tokens express control dependencies; they are not scientific data outputs.

For workflows whose commands contain `workflow://` references, the exporter
preserves graph ordering but does not translate DAGonStar staging into CWL
`File` parameters. See the [CWL export guide](../../docs/cwl_export.md) for the
complete interoperability boundary.
