# Lesson 13: FAIR by design

Enable FAIR recording with `workflow.enable_fair(FairProfile(...))`, then use
`declare_inputs()`, `declare_outputs()`, and `annotate()` to make task intent
machine-actionable. Run [the local example](../../examples/fair/fair_local.py) with
a configured `dagon.ini`; it needs no external service or new dependency.

The recorder observes normal workflow lifecycle hooks and writes `run.json`,
RO-Crate JSON-LD, PROV JSON, DataCite, CodeMeta, checksums, a validation report,
and Markdown/HTML reports under `<scratch>/.dagon/fair/<workflow>/<run>/` (or
`FairProfile.output_dir`). Environment capture is allowlist-only and names that
look like secrets are excluded. A `workflow:///A/file` dependency remains a
staging edge and is also recorded as producer/consumer provenance. The existing
parser's whitespace limitation still applies to those references.
