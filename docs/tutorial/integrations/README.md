# Optional integrations

These case studies sit outside the numbered curriculum so infrastructure and maturity do not interrupt the local learning path.

| Label | Meaning |
|---|---|
| Supported and locally testable | Deterministic verification requires no external system. |
| Supported but infrastructure-dependent | Public behavior exists; live evidence needs configured infrastructure. |
| Experimental | Behavior exists with limited validation or evolving interfaces. |
| Reserved or planned | An identifier exists, but automatic behavior is not implemented. |

- [DynoStore case study](dynostore.md) — explicit integration; automatic `DataMover.DYNOSTORE` staging is reserved rather than implemented.
- [FaaS task guide](../../faas_tasks.md) and [credential-free examples](../../../examples/faas/README.md) — supported invocation of already-deployed functions; deployment is outside DAGonStar's task lifecycle.
- [All-task interoperability guide](../../tasktype_interoperability.md) — locally testable construction, traversal, FAIR, checkpoint, and CWL contracts; portable emulation is not evidence that an external backend ran.
