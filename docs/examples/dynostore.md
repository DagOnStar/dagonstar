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
