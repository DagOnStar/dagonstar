# Lesson 16: Use DynoStore with DAGonStar

> Colab compatibility: structural example supported; live integration requires
> a reachable DynoStore deployment and its separately installed client.

## Objective

Persist a producer's output in DynoStore and retrieve it from a dependent
consumer without coupling the consumer to the producer's scratch host.

## Current implementation boundary

The DAGonStore paper describes DynoStore as a location-transparent, resilient
storage layer using erasure coding and load-aware placement. Its historical
DAGonStar integration used a Python client with `put`, `get_catalog`, `find`,
and delete operations. The current `master` branch reserves the
`DataMover.DYNOSTORE` enum value but does not implement automatic DynoStore
staging. This lesson therefore demonstrates the supported, explicit approach:
commands invoke the separately installed client, while a normal DAGonStar edge
controls task ordering. The example completes automatic dependency discovery
first and then adds an ordering-only edge; this avoids staging a producer file
through `COPY` or SCP merely to express ordering.

## Inspect locally

No server, client, or credential is needed to inspect the graph and commands:

```bash
python3 docs/dynostore_integration.py
```

The output shows `consumer (dependencies: producer)`. It also shows that the
server URL is read at task runtime from `DYNOSTORE_SERVER`; it is not embedded
in the workflow.

## Live workflow

The complete source is
[`examples/dynostore/dynostore_workflow.py`](../../examples/dynostore/dynostore_workflow.py).
It creates `readings.csv`, uploads it as a named catalog, retrieves that catalog
into the consumer scratch directory, and writes `result.csv`.

Install the client version required by the target DynoStore deployment, verify
its TLS and authentication configuration, then run:

```bash
export DYNOSTORE_SERVER=https://dynostore.example.org
python3 examples/dynostore/dynostore_workflow.py \
  --catalog lesson16-$(date +%s) \
  --scratch /path/to/scratch
```

The example follows the CLI contract used by the paper's integration branch:

```text
python3 -m dynostore.cli --server SERVER put FILE --catalog=NAME
python3 -m dynostore.cli --server SERVER get_catalog NAME DESTINATION
```

The client also supports `--recursive` for directory uploads; this lesson
uploads one file so the flag is intentionally omitted.

Treat this as a deployment boundary: confirm the commands against the client
installed at your site. A successful `put` response may precede asynchronous
erasure coding, depending on server policy. Configure synchronous durability
when a consumer must not start until redundant chunks are committed.

## Security and reproducibility

- Never commit OAuth tokens, encryption keys, or private service URLs.
- Use HTTPS and verify certificates; do not use `verify=False`.
- Use unique catalog names to prevent one run from overwriting another.
- Record the DynoStore client/server versions and erasure-code policy (`n`,
  `k`, synchronous/asynchronous upload) alongside experimental results.
- Define retention and deletion separately. The example does not delete data.
- Declare DynoStore artifacts in FAIR metadata only with non-secret identifiers
  and only when the deployment can substantiate persistence and access claims.

## Verification

Run the offline structural example and its tests:

```bash
python3 docs/dynostore_integration.py
python3 -m unittest tests.test_dynostore_examples -v
```

A live test is intentionally not part of CI because it requires external
infrastructure. After a live run, compare the producer's `readings.csv` and the
consumer's `result.csv`, and inspect the DynoStore catalog using site-approved
tools.
