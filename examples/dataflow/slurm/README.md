# Docker Tasks with SLURM

DagOnStar supports the deployment of tasks through SLURM (an open-source cluster resource management and job scheduling system).

## Requirements

* [SLURM](https://slurm.schedmd.com/documentation.html)

### Demo 1 - Local SLURM

The file ```dataflow-demo-slurm.py``` runs a workflow composed of four tasks using SLURM as job scheduling system.

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

The file ```dataflow-demo-slurm-remote.py``` runs a workflow composed of four tasks on a remote machine using SLURM as job scheduling system.

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