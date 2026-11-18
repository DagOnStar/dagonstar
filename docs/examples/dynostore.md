# DynoStore examples

[`examples/dynostore`](../../examples/dynostore) contains two examples:

- `inspect_integration.py` builds the graph and prints commands locally without
  contacting DynoStore;
- `dynostore_workflow.py` performs a live producer/upload/download/consumer
  workflow through the external DynoStore client.

The examples illustrate the DAGonStore architecture described in
*DAGonStore: Reliable Data Management for Workflows on the Computing Continuum
with DynoStore and DAGonStar* (SC Workshops 2025, DOI
`10.1145/3731599.3767579`). DynoStore owns resilient storage and reconstruction;
DAGonStar owns task execution and the explicit producer-to-consumer edge.

This is currently a task-level integration, not an automatic DAGonStar stager.
`DataMover.DYNOSTORE` is reserved in the enum, but `Stager.stage_in` does not
execute it on the repository's documented branch. See the [optional DynoStore case study](../tutorial/integrations/dynostore.md)
and the example README for setup, security, durability, and verification.

The common [ad-hoc file-system interface](../adhoc_filesystems.md) adds a
`dynostore` workflow resource: it can bring a Docker Compose deployment up and
down with the workflow, waits for the gateway, gives bound tasks
`DYNOSTORE_SERVER`, `DYNOSTORE_URL`, `DYNOSTORE_CATALOG`, and
`DYNOSTORE_AUTH_VARIABLE` (the name of the token variable, never the token),
and offers `put`/`get`/`exists`/`evict` helpers that read the token from an
environment variable at call time; tasks can use the same client through
`python -m dagon.adhoc dynostore put|get|exists|evict`. It reuses the
`[dynostore]` host and port of `dagon.ini` when no server is given. DynoStore at
commit `b9dedd7` needs
[`tools/adhoc/dynostore-b9dedd7-fixes.patch`](../../tools/adhoc/dynostore-b9dedd7-fixes.patch)
to deploy from its README steps and to return the new bytes when a key is
re-used; the fixes are listed in the
[ad-hoc guide](../adhoc_filesystems.md#dynostore). Live runs, before and after
the patch, are recorded in
[`docs/performance/adhoc_filesystems_2026-11-18.md`](../performance/adhoc_filesystems_2026-11-18.md).
