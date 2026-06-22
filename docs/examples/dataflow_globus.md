# Globus Dataflow Example

Source directory: [`examples/dataflow/globus`](../../examples/dataflow/globus)

## Files

- `dataflow-demo-globus.py`
- `README.md`
- `figs/` screenshots showing Globus setup steps

## Purpose

This example demonstrates Globus-backed movement of scientific data products
between endpoints. Globus is useful when datasets are large, geographically
distributed, or managed by research cyberinfrastructure.

## Prerequisites

- Globus account.
- Globus Connect Personal or Globus Connect Server.
- source endpoint UUID.
- intermediate endpoint UUID.
- destination endpoint UUID.
- Globus application/client ID.
- network and filesystem permissions on each endpoint.

## Configuration

The example README documents a `[globus]` section:

```ini
[globus]
clientid=<globus_client_uuid>
intermadiate_endpoint=<intermediate_endpoint_uuid>
```

Note the current implementation spelling: `intermadiate_endpoint`.
Documentation preserves this spelling because the code reads that key.

## Execution model

`GlobusManager` starts an OAuth flow using `globus_sdk.NativeAppAuthClient`.
The user is prompted to visit an authorization URL and paste the resulting code.
After authorization, DAGonStar submits transfer tasks through Globus Transfer.

## Verification

Before running DAGonStar:

1. log into <https://app.globus.org/>;
2. verify each endpoint is active;
3. manually transfer a tiny test file between endpoints;
4. confirm paths are visible from the endpoint root expected by Globus.

Then run:

```bash
cd examples/dataflow/globus
python dataflow-demo-globus.py
```

## Scientific interpretation

Globus is appropriate for workflows in which data movement is itself a
scientific infrastructure step. Record:

- endpoint UUIDs;
- collection names;
- paths;
- transfer task IDs;
- authorization context;
- checksum/sync policy when relevant.
