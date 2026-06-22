# Cloud Dataflow Examples

Source directory: [`examples/dataflow/cloud`](../../examples/dataflow/cloud)

## Files

- `dataflow-demo-cloud.py`
- `dataflow-demo-cloud-docker.py`
- `dataflow-demo-docker.json`
- `README.md`
- `imgs/ami_ID.png`

## Purpose

These examples demonstrate DAGonStar tasks backed by cloud virtual machines.
Cloud operations are implemented through Apache Libcloud and provider-specific
configuration.

## Supported provider concepts

The repository contains cloud helper classes for:

- Amazon EC2
- DigitalOcean
- Google Compute Engine

The example README focuses on EC2.

## Prerequisites

- Cloud account.
- API credentials.
- SSH key pair.
- network/security group permitting SSH.
- provider image ID and instance size.
- budget controls and cleanup plan.

For EC2 configuration:

```ini
[ec2]
key=<aws_access_key_id>
secret=<aws_secret_access_key>
region=<ec2_region>
```

Do not commit real values.

## Execution model

A cloud task combines:

- provider identifier;
- SSH username;
- key options;
- instance flavor;
- instance name;
- command;
- optional stop/cleanup behavior.

Example pattern:

```python
taskA = DagonTask(
    TaskType.CLOUD,
    "A",
    "mkdir output; echo I am A > output/f1.txt",
    Provider.EC2,
    "ubuntu",
    ssh_key_ec2_taskA,
    instance_flavour=ec2_flavour,
    instance_name="dagonTaskA",
    stop_instance=True,
)
```

## Verification

Cloud examples are not generic CI tests. Before running:

1. verify credentials with the provider CLI or console;
2. verify the selected image supports SSH;
3. verify the security group permits SSH from your client;
4. set a spending limit;
5. know how to manually terminate instances.

Run:

```bash
cd examples/dataflow/cloud
python dataflow-demo-cloud.py
```

after editing provider-specific values.

## Operational warning

The example documentation notes that instance stopping and data retrieval may
require manual intervention. Treat cloud runs as real infrastructure operations:
monitor created resources and clean them up explicitly.

## Scientific interpretation

Cloud tasks are useful for elastic workflows when data, software, and cost
constraints permit. Scientific reproducibility requires recording:

- provider;
- region;
- image ID;
- instance type;
- bootstrap steps;
- container images, if used;
- input/output object locations;
- cleanup status.
