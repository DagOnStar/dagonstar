## Apptainer Tasks with DagOnStar

DagOnStar supports the deployment of tasks on HPC environments using [Apptainer](https://apptainer.org/) containers.

## Requirements

* [Apptainer](https://apptainer.org/) (container runtime for HPC)
* Python 3.8+
* Virtualenv

## Installation

Clone the repository and prepare the Python environment:

```bash
git clone https://github.com/CoCo-ARCOS/dagonstar-containers.git
cd dagonstar-containers/

virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD:$PYTHONPATH
```

Copy the configuration file:

```bash
cp dagon.ini.sample examples/dataflow/apptainer/dagon.ini
```

Set up Apptainer automatically with the provided script:

```bash
bash dagon/setup-apptainer.sh
```

This will:

- Install Apptainer
- Configure cache and temporary directories  
- Set environment variables permanently
- Test basic functionality

> [!NOTE]
> You only need to run this setup once.

## Running Apptainer tasks

Navigate to the Apptainer example and run the demo:

```bash
cd examples/dataflow/apptainer/
python dataflow-demo-apptainer.py
```

During the execution, the demo will create containers for each task, execute the commands with overlays for file sharing, and finally clean up temporary files (if you specify `remove=True`).

### What Happens During Execution

1. **Container Preparation**: Apptainer downloads/builds the SIF image from the specified source
2. **Overlay Creation**: A writable overlay is created to allow file modifications inside the container
3. **Command Execution**: Your commands are executed inside the isolated container environment
4. **Data Transfer**: Files are transferred between containers using filesystem staging
5. **Cleanup**: Temporary files and overlays are removed after execution (if `remove=True`)

### Example Output

```
Preparing Apptainer container: a-d7a3dc9f-1760051924696
Building SIF image from: docker://ubuntu:20.04
SIF image built: /tmp/apptainer_work_a-d7a3dc9f-1760051924696/A.sif
Creating 1024MB overlay...
Overlay created: /tmp/apptainer_work_a-d7a3dc9f-1760051924696/overlay_a-d7a3dc9f-1760051924696.img
Container a-d7a3dc9f-1760051924696 prepared successfully

Executing in container: mkdir output; hostname > output/f1.txt
[A] Output: {"result": "Task completed"}

Cleaning up working directory: /tmp/apptainer_work_a-d7a3dc9f-1760051924696
```

## Advanced Configuration

### Using Custom Container Images

```python
from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("Custom-Image-Example")

# Use a Docker image
task1 = DagonTask(
    TaskType.APPTAINER,
    "PythonTask",
    "python --version",
    image="docker://python:3.11"
)

# Use a pre-built SIF file
task2 = DagonTask(
    TaskType.APPTAINER,
    "LocalSIF",
    "cat /etc/os-release",
    image="/path/to/container.sif"
)

# Use a custom registry
task3 = DagonTask(
    TaskType.APPTAINER,
    "CustomRegistry",
    "hostname",
    image="docker://myregistry.com/myimage:tag"
)

workflow.add_task(task1)
workflow.add_task(task2)
workflow.add_task(task3)
workflow.run()
```

### Using Bind Paths

Bind paths allow you to mount host directories inside the container:

```python
task = DagonTask(
    TaskType.APPTAINER,
    "BindExample",
    "ls /data && cat /config/settings.ini",
    image="docker://ubuntu:20.04",
    bind_paths=[
        "/host/data:/data",           # Mount /host/data to /data in container
        "/host/config:/config:ro"     # Mount read-only
    ]
)
```

### Adjusting Overlay Size

For tasks that need more writable space:

```python
task = DagonTask(
    TaskType.APPTAINER,
    "LargeData",
    "dd if=/dev/zero of=bigfile bs=1M count=2000",
    image="docker://ubuntu:20.04",
    overlay_size="4096"  # 4GB overlay (default is 1024MB)
)
```

### Custom Temporary Directory

Specify a custom location for temporary files:

```python
task = DagonTask(
    TaskType.APPTAINER,
    "CustomTmp",
    "echo 'Using custom tmp'",
    image="docker://ubuntu:20.04",
    tmp_dir="/scratch/tmp"  # Use /scratch instead of /tmp
)
```

### Keeping Containers After Execution (Debugging)

```python
task = DagonTask(
    TaskType.APPTAINER,
    "DebugTask",
    "echo 'Debug this'",
    image="docker://ubuntu:20.04",
    remove=False  # Keep container files after execution
)
```

## Troubleshooting

### Error: "apptainer: command not found"

**Cause**: Apptainer is not installed or not in PATH

**Solution**:
```bash
# Check if Apptainer is installed
which apptainer

# If not found, install it
bash dagon/setup-apptainer.sh

# Or manually:
sudo apt update
sudo apt install -y apptainer
```

### Error: "FATAL: container creation failed: mount /proc/self/fd/3->/usr/local/var/apptainer/mnt/session/rootfs error"

**Cause**: Insufficient permissions or namespace issues

**Solution**:
```bash
# Run with --fakeroot (user namespace)
apptainer exec --fakeroot docker://ubuntu:20.04 echo "test"

# Or ensure user namespaces are enabled
sudo sysctl -w kernel.unprivileged_userns_clone=1
```

### Error: "FATAL: while extracting image: root filesystem extraction failed: extract command failed"

**Cause**: Insufficient disk space or corrupted download

**Solution**:
```bash
# Check disk space
df -h

# Clear Apptainer cache
rm -rf ~/.apptainer/cache/*

# Set custom cache directory with more space
export APPTAINER_CACHEDIR=/path/to/large/disk/cache
```

### Error: "overlay: Resource temporarily unavailable"

**Cause**: Overlay file is locked by another process

**Solution**:
```bash
# Find and kill processes using the overlay
lsof | grep overlay
# Or wait for the process to finish

# Clean up stale lock files
rm -f /tmp/apptainer_work_*/overlay_*.img.lock
```

### Warning: "INFO: Converting SIF file to temporary sandbox..."

**Cause**: Normal operation when Apptainer needs to extract the container

**Solution**: This is not an error. The warning can be suppressed by:
```bash
export APPTAINER_SILENT=true
```

### Error: "cannot create directory '/staging': Read-only file system"

**Cause**: Container filesystem is read-only without overlay

**Solution**: This should not happen with DagOnStar's implementation as it automatically creates overlays. If it does:
```bash
# Verify overlay is being created
ls -lh /tmp/apptainer_work_*/overlay_*.img

# Increase overlay size if needed
task = DagonTask(..., overlay_size="2048")
```

### Performance: Slow Image Building

**Cause**: Downloading large images or slow network

**Solution**:
```bash
# Pre-build commonly used images
apptainer build ubuntu2004.sif docker://ubuntu:20.04
apptainer build python39.sif docker://python:3.9

# Use the pre-built SIF files
task = DagonTask(
    TaskType.APPTAINER,
    "FastTask",
    "echo 'Using cached image'",
    image="ubuntu2004.sif"
)

# Or set a persistent cache location
export APPTAINER_CACHEDIR=/opt/apptainer/cache
```

## Remote Apptainer Tasks with DagOnStar

DagOnStar allows you to execute Apptainer tasks on remote servers via SSH. This is useful for distributing workloads across multiple machines or accessing HPC resources remotely.

## Prerequisites

Before running remote tasks, ensure the following:

1. Apptainer is installed on the remote machine
2. SSH service is enabled on the remote machine
3. Sufficient disk space on the remote machine (at least 5GB recommended)

## Remote Machine Setup

### Installing Apptainer

On the remote machine (e.g., your Kali VM or HPC node), install and configure Apptainer:

```bash
# On the remote machine (e.g., Kali VM or HPC node)
sudo apt update
sudo apt upgrade -y
sudo apt install -y apptainer

# Verify installation
apptainer --version
```

> [!TIP]
> On some HPC systems, Apptainer might be available as a module:
> ```bash
> module load apptainer
> # or
> module load singularity  # Older systems
> ```

### Configuring SSH Service

Enable and verify SSH service:

```bash
# Enable SSH service to start on boot
sudo systemctl enable ssh

# Start SSH service
sudo systemctl start ssh

# Verify SSH is running
sudo systemctl status ssh

# Check your IP address and note it down
ip a
```

> [!TIP]
> Look for the `inet` address under your network interface (usually `eth0` or `wlan0`). This is the IP you'll use in the configuration.

## Configuration

Before running remote examples, edit the `dagon.ini` file in your example directory and configure the SSH parameters:

```ini
[ssh]
# SSH Configuration for Remote Tasks
# Edit these values according to your environment
remote_ip = 192.168.1.100    # IP address of the remote server (from 'ip a' command)
ssh_user = your_username      # Your SSH username on the remote machine
ssh_port = 22                 # SSH port (default 22, use 2222 if using VM port forwarding)
```

### Configuration Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `remote_ip` | IP address or hostname of the remote server | `192.168.1.100`, `10.0.0.5`, or `hpc.example.com` |
| `ssh_user` | SSH username for authentication | `kali`, `ubuntu`, `your_username` |
| `ssh_port` | SSH port number | `22` (standard), `2222` (VM forwarding), or custom port |

### SSH Key Authentication

For seamless execution, configure SSH key-based authentication:

```bash
# On your local machine
# Generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096

# Copy your public key to the remote machine
ssh-copy-id -p 22 your_username@remote_ip

# Test SSH connection without password
ssh your_username@remote_ip -p 22
```

> [!NOTE]
> SSH key authentication is required for automated workflow execution. Password-based authentication may cause the workflow to hang.

## Running Remote Examples

Once configured, navigate to the remote Apptainer example and run:

```bash
cd examples/dataflow/apptainer/
python dataflow-demo-apptainer-remote.py
```

### What Happens During Remote Execution

1. **SSH Connection**: DagOnStar establishes an SSH connection to the remote machine
2. **Script Transfer**: Task scripts are transferred to the remote machine via SSH
3. **Container Preparation**: Apptainer downloads/builds SIF images on the remote machine
4. **Command Execution**: Commands are executed inside containers on the remote machine
5. **Data Transfer**: Files are transferred between tasks using filesystem staging
6. **Cleanup**: Temporary files are removed from the remote machine (if `remove=True`)

### Example Output

```
============================================================
Starting Remote Apptainer Workflow
============================================================

Preparing remote Apptainer container: a-d7a3dc9f-1760051924696 on 192.168.1.100
Building SIF image on remote machine from: docker://ubuntu:20.04
Remote SIF image built successfully: /tmp/apptainer_sif_a-d7a3dc9f-1760051924696/A.sif
Remote container a-d7a3dc9f-1760051924696 prepared successfully

Executing in remote container: mkdir output; hostname > output/f1.txt
[A] Task completed successfully

Copying file output/f1.txt from A to B
Exporting output/f1.txt to remote staging
File copied successfully via filesystem staging

============================================================
Workflow Completed Successfully!
============================================================
```

## Remote Troubleshooting

### Error: SSH Connection Timeout

**Cause**: SSH service is not running or firewall is blocking connections

**Solution**:
```bash
# On the remote machine
sudo systemctl start ssh
sudo systemctl status ssh

# Check if firewall is blocking (if using ufw)
sudo ufw allow 22/tcp

# On local machine, test SSH connection with verbose output
ssh -v your_username@remote_ip -p 22
```

### Error: "Permission denied (publickey)"

**Cause**: SSH key authentication is not configured

**Solution**:
```bash
# On local machine
ssh-copy-id -p 22 your_username@remote_ip

# Verify SSH key is copied
ssh your_username@remote_ip -p 22 "cat ~/.ssh/authorized_keys"

# Test connection
ssh your_username@remote_ip -p 22
```

### Error: "apptainer: command not found" (Remote)

**Cause**: Apptainer is not installed on the remote machine

**Solution**:
```bash
# SSH to remote machine
ssh your_username@remote_ip -p 22

# Install Apptainer
sudo apt update
sudo apt install -y apptainer

# Verify
apptainer --version
```

### Error: "No space left on device" (Remote)

**Cause**: Insufficient disk space on remote machine

**Solution**:
```bash
# On remote machine, check disk space
df -h

# Clean up Apptainer cache
rm -rf ~/.apptainer/cache/*

# Set custom cache and tmp directories with more space
export APPTAINER_CACHEDIR=/path/to/large/disk/cache
export APPTAINER_TMPDIR=/path/to/large/disk/tmp
```

### Error: Remote file transfer fails

**Cause**: Network issues or insufficient permissions

**Solution**:
```bash
# Test SSH file transfer manually
scp -P 22 test.txt your_username@remote_ip:/tmp/

# Check remote directory permissions
ssh your_username@remote_ip -p 22 "ls -la /tmp"

# Verify working directory is writable
ssh your_username@remote_ip -p 22 "mkdir -p /tmp/test && touch /tmp/test/file"
```

## VM Port Forwarding Setup (Optional)

If your remote machine is a VM running on the same host, you may need to configure port forwarding:

### VirtualBox

```bash
# Forward SSH port 22 to host port 2222
VBoxManage modifyvm "YourVM" --natpf1 "ssh,tcp,,2222,,22"
```

Then update `dagon.ini`:
```ini
[ssh]
remote_ip = 127.0.0.1
ssh_user = your_username
ssh_port = 2222
```

### VMware

1. Open VM Settings
2. Go to Network Adapter → NAT Settings
3. Add Port Forwarding:
   - Host Port: 2222
   - Guest Port: 22

### KVM/QEMU

```bash
# Start VM with port forwarding
qemu-system-x86_64 -netdev user,id=net0,hostfwd=tcp::2222-:22 ...
```

## Comparison: Local vs Remote Apptainer Tasks

| Feature | Local Apptainer | Remote Apptainer |
|---------|-----------------|------------------|
| **Configuration** | `dagon.ini` not required | Requires `dagon.ini` with SSH settings |
| **SSH Keys** | Not needed | Required for authentication |
| **Network** | Localhost only | SSH over network |
| **Use Case** | Development, testing | Production, HPC, distributed workloads |
| **Parameters** | No `ip`, `ssh_username`, `ssh_port` | Requires `ip`, `ssh_username`, `ssh_port` |
| **Performance** | Faster (no SSH overhead) | Network latency added |

### Local Example (No SSH)

```python
taskA = DagonTask(
    TaskType.APPTAINER,
    "A",
    "hostname",
    image="docker://ubuntu:20.04"
    # No ip, ssh_username, or ssh_port
)
```

### Remote Example (With SSH)

```python
taskA = DagonTask(
    TaskType.APPTAINER,
    "A",
    "hostname",
    image="docker://ubuntu:20.04",
    ip="192.168.1.100",
    ssh_username="kali",
    ssh_port=22
)
```

## Best Practices

1. **Use SSH key authentication** - Never use password-based SSH for automation
2. **Pre-build common images** - Build and reuse SIF files to speed up execution
3. **Monitor disk space** - Apptainer containers can be large; monitor with `df -h`
4. **Use appropriate overlay sizes** - Adjust based on your workload (default: 1024MB)
5. **Clean up regularly** - Use `remove=True` to automatically delete temporary files
6. **Set custom cache locations** - Use persistent cache to avoid re-downloading images
7. **Test manually first** - Verify Apptainer works via SSH before running workflows
8. **Bind only what's needed** - Minimize bind paths for better security and performance

## Performance Considerations

- **Image caching**: First run downloads images; subsequent runs are faster
- **Overlay size**: Larger overlays allow more writes but take longer to create
- **Network speed**: Remote execution adds SSH and file transfer overhead
- **Resource availability**: Ensure remote machine has sufficient CPU, memory, and disk
- **Concurrent tasks**: Apptainer supports parallel execution; adjust based on resources

## Security Notes

- Always use SSH key authentication instead of passwords
- Restrict SSH access using firewall rules (`ufw`, `iptables`)
- Use non-root users for SSH connections
- Keep Apptainer updated to the latest version
- Consider using VPN for remote connections over the internet
- Be cautious with bind paths - avoid mounting sensitive directories

## HPC-Specific Considerations

### SLURM Integration

If your remote machine uses SLURM, you can combine Apptainer with SLURM:

```python
# Note: This requires additional SLURM task type implementation
# Example conceptual usage:
taskA = DagonTask(
    TaskType.APPTAINER,
    "HPCTask",
    "intensive_computation.sh",
    image="docker://myapp:latest",
    ip="hpc.cluster.edu",
    ssh_username="researcher",
    ssh_port=22,
    bind_paths=["/scratch:/scratch", "/data:/data"]
)
```

### Module Systems

Many HPC systems use environment modules:

```bash
# On remote HPC node
module load apptainer
module load python/3.9

# Verify modules are loaded
module list
```

### Shared Filesystems

On HPC systems with shared storage (Lustre, GPFS, NFS):

```python
taskA = DagonTask(
    TaskType.APPTAINER,
    "SharedFS",
    "process_data.py",
    image="/shared/containers/analysis.sif",  # Use shared SIF
    tmp_dir="/scratch/$USER",  # Use scratch space
    bind_paths=["/shared/data:/data:ro"]  # Bind shared data
)
```

## Additional Resources

- [Apptainer Documentation](https://apptainer.org/docs/)
- [Apptainer User Guide](https://apptainer.org/docs/user/latest/)
- [DagOnStar GitHub Repository](https://github.com/CoCo-ARCOS/dagonstar-containers)
- [Singularity/Apptainer Migration Guide](https://apptainer.org/docs/admin/latest/singularity_migration.html)

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review Apptainer logs: Check stdout/stderr from the workflow
- Verify SSH connectivity: `ssh -v user@host -p port`
- Test Apptainer manually: `apptainer exec docker://ubuntu:20.04 echo test`
- Open an issue on the [GitHub repository](https://github.com/CoCo-ARCOS/dagonstar-containers/issues)