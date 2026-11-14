# Docker Tasks with SLURM

DagOnStar supports the deployment of tasks through SLURM (an open-source cluster resource management and job scheduling system).

## Requirements

* [SLURM](https://slurm.schedmd.com/documentation.html)

### Demo 1 - Local SLURM

The file ```dataflow-demo-slurm.py``` runs a workflow composed of four tasks using SLURM as job scheduling system. For each task specify the SLURM partition where execute the tasks.

#### Steps

Open the root directory of DagOnStar in a terminal, and run the following commands to prepare it.

```bash
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD:$PYTHONPATH
```

Now navigate to the directory of the demo.

```bash
cd examples/dataflow/slurm
```

Execute the file ```dataflow-demo-slurm.py``` as follows:

```bash
python dataflow-demo-slurm.py
```

When the execution of the workflow is completed, you must see an output on the terminal as follows:

```console
2023-11-06 13:31:25,290 root         DEBUG    Running workflow: DataFlow-Demo-Slurm
2023-11-06 13:31:25,291 root         DEBUG    A: Status.WAITING
2023-11-06 13:31:25,291 root         DEBUG    A: Status.RUNNING
2023-11-06 13:31:25,291 root         DEBUG    B: Status.WAITING
2023-11-06 13:31:25,291 root         DEBUG    A: Executing...
2023-11-06 13:31:25,292 root         DEBUG    C: Status.WAITING
2023-11-06 13:31:25,293 root         DEBUG    D: Status.WAITING
2023-11-06 13:31:25,294 root         DEBUG    A: Scratch directory: /tmp//1699273885293-A
2023-11-06 13:32:36,811 root         DEBUG    A Completed in 71.14384317398071 seconds ---
2023-11-06 13:32:38,813 root         DEBUG    A: Status.FINISHED
2023-11-06 13:32:38,814 root         DEBUG    B: Status.RUNNING
2023-11-06 13:32:38,814 root         DEBUG    C: Status.RUNNING
2023-11-06 13:32:38,815 root         DEBUG    B: Executing...
2023-11-06 13:32:38,815 root         DEBUG    C: Executing...
2023-11-06 13:32:38,816 root         DEBUG    B: Scratch directory: /tmp//1699273958816-B
2023-11-06 13:32:38,816 root         DEBUG    C: Scratch directory: /tmp//1699273958816-C
2023-11-06 13:32:41,223 root         DEBUG    C Completed in 2.0285587310791016 seconds ---
2023-11-06 13:32:42,296 root         DEBUG    B Completed in 3.0266966819763184 seconds ---
2023-11-06 13:32:42,297 root         DEBUG    Removed /tmp//1699273885293-A
2023-11-06 13:32:43,225 root         DEBUG    C: Status.FINISHED
2023-11-06 13:32:44,299 root         DEBUG    B: Status.FINISHED
2023-11-06 13:32:44,300 root         DEBUG    D: Status.RUNNING
2023-11-06 13:32:44,300 root         DEBUG    D: Executing...
2023-11-06 13:32:44,300 root         DEBUG    D: Scratch directory: /tmp//1699273964301-D
2023-11-06 13:32:46,745 root         DEBUG    D Completed in 2.0274548530578613 seconds ---
2023-11-06 13:32:46,746 root         DEBUG    Removed /tmp//1699273958816-B
2023-11-06 13:32:46,746 root         DEBUG    Removed /tmp//1699273958816-C
2023-11-06 13:32:48,748 root         DEBUG    D: Status.FINISHED
2023-11-06 13:32:48,749 root         INFO     Workflow 'DataFlow-Demo-Slurm' completed in 83.4585907459259 seconds ---
```

### Demo 2 - Remote SLURM

The file ```dataflow-demo-slurm-remote.py``` runs a workflow composed of four tasks on a remote machine using SLURM as job scheduling system. For each task specify the ip and username of remote machine and SLURM partition where execute the tasks.

#### Preconfigurations

1. **Generate an SSH Key Pair**
To begin, you need to generate an SSH key pair on your local machine. Open your terminal and run the following command:

```bash
ssh-keygen -t rsa -b 2048
```

This will generate a public key (usually named `id_rsa.pub`) and a private key (usually named `id_rsa`) in the `~/.ssh` directory.

2. **Copy the Public Key to the Server**
Now, you'll need to copy the public key to the server you want to access. You can use the `ssh-copy-id` command for this. Replace `username` and `server_ip` with your own information:

```bash
ssh-copy-id username@server_ip
```

This command will prompt you for the server password, and then it will copy your public key to the server's `~/.ssh/authorized_keys` file.

3. **Test the Key-Based Authentication**
Try to SSH into the server without a password to test if the key-based authentication is working:

```bash
ssh username@server_ip
```

If everything is set up correctly, you should be able to log in without entering a password.

Now you have successfully set up SSH access to your server without a password, using a key pair for authentication. Make sure to keep your private key secure on your local machine, and don't share it with anyone.

#### Steps

Open the root directory of DagOnStar in a terminal, and run the following commands to prepare it.

```bash
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD:$PYTHONPATH
```

Now navigate to the directory of the demo.

```bash
cd examples/dataflow/slurm
```

Execute the file ```dataflow-demo-slurm-remote.py``` as follows:

```bash
python dataflow-demo-slurm-remote.py
```
## BeeOND on-demand file systems

DAGonStar can run Slurm tasks on BeeOND (BeeGFS On Demand) volumes that a site
creates for jobs submitted with a comment such as `--comment=beeond-fs`.
Volumes can be created per task or per workflow, and DAGonStar copies their
contents to persistent storage before the volume is destroyed. The full guide
is [docs/beeond.md](../../../docs/beeond.md).

### Demo 3 - Local emulation (self-contained)

`beeond_local_emulation.py` needs no Slurm, no `dagon.ini`, and no network. It
uses `portable_emulation=True`, so `$DAGON_BEEOND` points directly at the
persistent directory. It runs a per-task volume, a `workflow://` reference into
the persisted copy, and a shared per-workflow volume, then verifies the
results:

```bash
python examples/dataflow/slurm/beeond_local_emulation.py
python examples/dataflow/slurm/beeond_local_emulation.py --scratch /path/to/keep
```

Expected output ends with `Verification: ok`. The example also runs as part of
`python tools/run_local_examples.py`.

### Demo 4 - Live BeeOND cluster (infrastructure-dependent)

`beeond_slurm.py` mirrors a site batch script in which every node writes a file
into `/mnt/beeond_${SLURM_JOB_USER}-jobid_${SLURM_JOB_ID}` and one step combines
the files. Run it on the login node with a `dagon.ini` whose
`scratch_dir_base` is on a file system shared with the compute nodes:

```bash
python beeond_slurm.py --scope task --partition xxcpu --nodelist 'wn[01-04]'
python beeond_slurm.py --scope workflow --time 00:30:00
```

Add `--ip <login-node> --ssh-user <user>` to submit through SSH with
`RemoteSlurm`. For `--scope task`, the persisted volume is in
`<working_dir of nodes>/beeond/`. For `--scope workflow`, it is in
`<scratch_dir_base>/BeeOND-Slurm-workflow-beeond-default/`. Both commands were
run manually on a four-node BeeOND site (Slurm 23.11.3) on 2026-11-13; they are
not part of the automated checks.
The `beeond-slurm` CI job runs the equivalent checks in
`tools/ci_beeond_slurm.py` on a single-node Slurm cluster with an emulated
BeeOND site; you can run that script on your own cluster with
`--partition <partition> --nodes <n> --scratch <shared-dir>`.

## Scheduler-aware pre-staging

By default, a Slurm job stages its `workflow://` inputs after the scheduler
has allocated its resources. With `Workflow(pre_stage=True)`, or with
`pre_stage=True` on a Slurm task, DAGonStar stages and verifies the inputs on
the submission host first (comparing content with the source when the source
is readable there), writes `.dagon/stage-in-complete.json`, and only then calls
`sbatch --parsable`. If stage-in fails, no job is submitted. See
[Scheduler-aware pre-staging](../../../docs/scheduler_prestaging.md).

All three demos run the same coastal-forecast workflow. `forcing` writes 24
hourly files, and `bathymetry` writes a depth profile. `simulate` requests the
cores and reads `workflow:///forcing/forcing/hour_*.txt` and the bathymetry.
`analyse` opts out with `pre_stage=False`.

### Demo 5 - Legacy vs pre-staged with a mock scheduler (self-contained)

No Slurm, `dagon.ini`, or credentials are needed:

```bash
python3 examples/dataflow/slurm/pre_stage_mock.py
```

`sbatch` is replaced by `mock_scheduler.py`. The mock runs the job script
immediately with the local bash and records, at submission time, whether the
stage-in marker existed and whether the inputs were on scratch. The legacy
run shows `False`/`False` for `simulate`. The pre-staged run shows `True`/`True`
for `simulate` and `False`/`False` for the opted-out `analyse`. The script ends
with `Verification: ok`. The mock has no queue or allocation, so the printed
core-hour figure is the estimate `cores x staging_seconds / 3600`, not a
measurement. `tools/run_local_examples.py` runs this demo in CI.

### Demo 6 - Local Slurm (infrastructure-dependent)

Prerequisites: a Slurm login node, and a scratch directory on a file system
that the login node and the compute nodes share at the same path and that
persists while jobs are queued. Node-local and BeeOND storage are not
suitable.

```bash
cd examples/dataflow/slurm
python3 pre_stage_local.py --scratch /shared/scratch/$USER/dagon --partition <partition> --cores 200
python3 pre_stage_local.py --scratch /shared/scratch/$USER/dagon --legacy
```

The script prints when stage-in finished and when the allocation started the
compute launcher. The two times come from different hosts, have one-second
resolution, and assume synchronised clocks. The script then checks that
stage-in finished first. The `beeond-slurm` CI job runs this demo with
`--partition ci` on its single-node cluster, together with
`tools/ci_prestage_slurm.py`.

For a deeper site check, run `tools/hpc_prestage_deep.py` from the repository
root on the login node. It submits real jobs, and some stay pending on purpose
for a minute or more, so use a partition where that is acceptable:

```bash
python3 tools/hpc_prestage_deep.py --scratch /shared/scratch/$USER/dagon-deep --partition <partition> --size-mib 1024
```

### Demo 7 - Remote Slurm over SSH (infrastructure-dependent)

```bash
cd examples/dataflow/slurm
python3 pre_stage_remote.py --host <login-host> --user <user> --key ~/.ssh/id_rsa \
    --remote-scratch /shared/scratch/<user>/dagon [--port 22] [--partition <partition>]
```

`stage_in.sh` is written to the login node and run there over SSH, and the
remote `sbatch` runs only after stage-in succeeds. Nothing is assumed to be
mounted locally. The unit tests run this script against a loopback SSH double.
It has also been run once, manually, from a workstation against one production
Slurm 23.11 cluster, and ended with `Verification: ok`. Demo 6 passed on the
same cluster in both lifecycles.
Demos 6 and 7 submit real jobs, so run them only where you are authorised to.
