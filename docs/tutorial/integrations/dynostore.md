# Case Study: Persist Workflow Artifacts with DynoStore

> **Maturity:** Reserved automatic mover; explicit client integration is infrastructure-dependent.

DAGonStar currently reserves `DataMover.DYNOSTORE`, but the stager does not implement automatic DynoStore transfer. Selecting the enum is therefore not evidence of catalog registration or artifact movement.

The supported teaching pattern is explicit: run the DynoStore client as a task or invoke a separately installed client from application code, add ordering dependencies where required, verify client exit status and catalog evidence, and keep deployment credentials outside workflow source. An ordering-only dependency does not imply transfer. Catalog registration does not by itself prove byte transfer, preservation, or public accessibility.

For a live deployment, document endpoint, client version, authentication source, command, expected catalog record, checksum comparison, cleanup, and site-specific variability. See [the existing DynoStore example guide](../../examples/dynostore.md) and the [integration maturity index](README.md).
