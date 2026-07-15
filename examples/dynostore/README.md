# DynoStore integration examples

These examples demonstrate the explicit task-level integration described in
the DAGonStore paper. They use the external DynoStore Python client to persist
a producer artifact under a catalog name and retrieve it in a dependent task.

The current DAGonStar `master` branch reserves `DataMover.DYNOSTORE`, but does
not automatically select or execute it in `Stager.stage_in`. Consequently,
these examples invoke the client explicitly. They call
`workflow.make_dependencies()` and then add the ordering-only edge with
`consumer.add_dependency_to(producer)`, so no producer scratch artifact is
silently transferred by another stager.

Inspect the commands and dependency graph without a service:

```bash
python3 examples/dynostore/inspect_integration.py
```

For a live run, install the DynoStore client version deployed by your site and
provide only the data access manager URL in the environment:

```bash
export DYNOSTORE_SERVER=https://dynostore.example.org
python3 examples/dynostore/dynostore_workflow.py \
  --catalog dagonstar-demo-$(date +%s) \
  --scratch /path/to/scratch
```

The client interface follows the historical integration branch:

```text
python3 -m dynostore.cli --server SERVER put FILE --catalog=NAME
python3 -m dynostore.cli --server SERVER get_catalog NAME DESTINATION
```

Use `--recursive` only when uploading a directory rather than the single file
used by this example.

Client releases and site deployments may differ. Confirm these commands against
the deployed DynoStore client before a production run. Authentication material
must be supplied using that client's environment or secure runtime mechanism;
never place tokens in workflow commands, configuration committed to Git, FAIR
metadata, or catalog names. Use a unique catalog per workflow run and define a
site-specific retention/deletion policy.
