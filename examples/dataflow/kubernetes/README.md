## Kubernetes Tasks with DagOnStar

DagOnStar supports the deployment of tasks on Kubernetes clusters using [K3s](https://k3s.io/).

## Requirements

* [K3s](https://k3s.io/) (lightweight Kubernetes distribution)
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
cp dagon.ini.sample examples/dataflow/kubernetes/dagon.ini
```

Set up K3s automatically with the provided script:

```bash
bash dagon/setup-k3s.sh
```

This will:

Install K3s

Configure ~/.kube/config

Set the KUBECONFIG environment variable permanently

[!NOTE]
You only need to run this setup once.

## Running Kubernetes tasks

Navigate to the Kubernetes example and run the demo:

```bash
cd examples/dataflow/kubernetes/
python dataflow-demo-k3s.py
```
During the execution, the demo will create pods for each task, wait until they are running, execute the commands, and finally clean up the pods (if you specify remove=True).


## Remote Kubernetes Tasks with DagOnStar

DagOnStar allows you to execute Kubernetes tasks on remote servers via SSH. This is useful for distributing workloads across multiple machines or accessing Kubernetes clusters remotely.

## Prerequisites

Before running remote tasks, ensure the following:

1. K3s (or any Kubernetes distribution) is installed on the remote machine
2. SSH service is enabled on the remote machine
3. `kubectl` is properly configured on the remote machine

## Remote Machine Setup

### Installing K3s

On the remote machine (e.g., your Kali VM or remote server), install and configure K3s:

```bash
# On the remote machine (e.g., Kali VM)
curl -sfL https://get.k3s.io | sh -

# Wait for installation to complete (1-2 minutes)

# Configure kubectl access for your user
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config

# Verify K3s installation
kubectl get nodes
```

Expected output:
```
NAME    STATUS   ROLES                  AGE   VERSION
kali    Ready    control-plane,master   30s   v1.28.x+k3s1
```

> [!TIP]
> K3s includes `kubectl` by default. If you need to install it separately, use:
> ```bash
> curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
> sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
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
remote_ip = 192.168.1.100  # IP address of the remote server (from 'ip a' command)
ssh_user = your_username   # Your SSH username on the remote machine
ssh_port = 22              # SSH port (default 22, use 2222 if using VM port forwarding)
```

### Configuration Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `remote_ip` | IP address or hostname of the remote server | `192.168.1.100`, `10.0.0.5`, or `k8s.example.com` |
| `ssh_user` | SSH username for authentication | `kali`, `ubuntu`, `your_username` |
| `ssh_port` | SSH port number | `22` (standard), `2222` (VM forwarding), or custom port |

### SSH Key Authentication

For seamless execution, configure SSH key-based authentication:

```bash
# On your local machine (Ubuntu)
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

Once configured, navigate to the remote Kubernetes example and run:

```bash
cd examples/dataflow/kubernetes/
python dataflow-demo-k3s-remote.py
```

### What Happens During Execution

1. **SSH Connection**: DagOnStar establishes an SSH connection to the remote machine
2. **Pod Creation**: Each task creates a pod in the remote K3s cluster
3. **Command Execution**: Commands are executed inside the pods via `kubectl exec`
4. **Data Transfer**: Files are transferred between pods using `workflow:///` URLs
5. **Cleanup**: Pods are deleted after execution (if `remove=True`)

### Example Output

```
============================================================
Starting Remote Kubernetes Workflow
============================================================

Creating remote pod: a-d7a3dc9f-1760051924696 on 192.168.1.100
Waiting for remote pod a-d7a3dc9f-1760051924696 to be ready...
Remote pod a-d7a3dc9f-1760051924696 ready with IP: 10.42.0.15
Executing in remote pod: mkdir output; hostname > output/f1.txt

Creating remote pod: b-72bbc7aa-1760051924947 on 192.168.1.100
Copying file output/f1.txt from DataPrep to DataAnalysis
File copied successfully

============================================================
Workflow Completed Successfully!
============================================================
```

## Troubleshooting

### Error: "command not found: kubectl"

**Cause**: kubectl is not installed or not in PATH on the remote machine

**Solution**:
```bash
# On the remote machine
which kubectl

# If not found, install it:
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### Error: "The connection to the server localhost:8080 was refused"

**Cause**: kubectl cannot find the Kubernetes cluster configuration

**Solution**:
```bash
# On the remote machine
# Verify K3s is running
sudo systemctl status k3s

# Configure kubectl access
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

### Error: SSH Connection Timeout

**Cause**: SSH service is not running or firewall is blocking connections

**Solution**:
```bash
# On the remote machine
sudo systemctl start ssh
sudo systemctl status ssh

# Check if firewall is blocking (if using ufw)
sudo ufw allow 22/tcp

# On local machine, test SSH connection
ssh your_username@remote_ip -p 22
```

### Error: "Permission denied (publickey)"

**Cause**: SSH key authentication is not configured

**Solution**:
```bash
# On local machine
ssh-copy-id -p 22 your_username@remote_ip

# Verify SSH key is copied
ssh your_username@remote_ip -p 22 "cat ~/.ssh/authorized_keys"
```

### Error: Pods Stuck in "Pending" State

**Cause**: Insufficient resources or networking issues

**Solution**:
```bash
# On the remote machine
# Check pod status
kubectl describe pod <pod-name>

# Check available resources
free -h
df -h

# Check K3s logs
sudo journalctl -u k3s -f
```

### Error: "ImagePullBackOff"

**Cause**: K3s cannot download the container image

**Solution**:
```bash
# On the remote machine
# Check internet connectivity
ping google.com

# Manually pull the image
sudo k3s ctr images pull docker.io/library/ubuntu:20.04

# List available images
sudo k3s ctr images list
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

## Advanced Configuration

### Using Custom Kubernetes Namespaces

```python
taskA = DagonTask(
    TaskType.KUBERNETES,
    "A",
    "echo 'Hello from custom namespace'",
    image="ubuntu:20.04",
    namespace="my-namespace",  # Use custom namespace
    ip=REMOTE_IP,
    ssh_username=SSH_USER,
    ssh_port=SSH_PORT
)
```

### Using Different Container Images

```python
taskB = DagonTask(
    TaskType.KUBERNETES,
    "B",
    "python --version",
    image="python:3.11",  # Use different image per task
    ip=REMOTE_IP,
    ssh_username=SSH_USER,
    ssh_port=SSH_PORT
)
```

### Keeping Pods After Execution (Debugging)

```python
taskC = DagonTask(
    TaskType.KUBERNETES,
    "C",
    "echo 'Debug this task'",
    image="ubuntu:20.04",
    remove=False,  # Keep pod after execution
    ip=REMOTE_IP,
    ssh_username=SSH_USER,
    ssh_port=SSH_PORT
)
```

## Comparison: Local vs Remote Kubernetes Tasks

| Feature | Local K3s | Remote K3s |
|---------|-----------|------------|
| **Configuration** | `dagon.ini` not required | Requires `dagon.ini` with SSH settings |
| **SSH Keys** | Not needed | Required for authentication |
| **Network** | Localhost only | SSH over network |
| **Use Case** | Development, testing | Production, distributed workloads |
| **Parameters** | No `ip`, `ssh_username`, `ssh_port` | Requires `ip`, `ssh_username`, `ssh_port` |

### Local Example (No SSH)

```python
taskA = DagonTask(
    TaskType.KUBERNETES,
    "A",
    "hostname",
    image="ubuntu:20.04"
    # No ip, ssh_username, or ssh_port
)
```

### Remote Example (With SSH)

```python
taskA = DagonTask(
    TaskType.KUBERNETES,
    "A",
    "hostname",
    image="ubuntu:20.04",
    ip="192.168.1.100",
    ssh_username="kali",
    ssh_port=22
)
```

## Best Practices

1. **Always use SSH key authentication** - Never use password-based SSH for automation
2. **Test kubectl manually first** - Verify `kubectl get nodes` works via SSH before running workflows
3. **Monitor resource usage** - K3s requires at least 2GB RAM; monitor with `free -h`
4. **Use namespaces** - Organize pods using Kubernetes namespaces for different workflows
5. **Clean up regularly** - Use `remove=True` to automatically delete pods after execution
6. **Check network connectivity** - Ensure stable network between local and remote machines
7. **Keep K3s updated** - Regularly update K3s on remote machines for security patches

## Performance Considerations

- **Network latency**: Remote execution adds SSH and network overhead
- **Image pulling**: First-time image pulls can be slow; consider pre-pulling common images
- **Resource limits**: Ensure remote machine has sufficient CPU and memory for your workloads
- **Concurrent tasks**: K3s can handle multiple pods simultaneously; adjust based on resources

## Security Notes

- Always use SSH key authentication instead of passwords
- Restrict SSH access using firewall rules (`ufw`, `iptables`)
- Use non-root users for SSH connections
- Keep K3s and kubectl updated to the latest versions
- Consider using VPN for remote connections over the internet

## Additional Resources

- [K3s Documentation](https://docs.k3s.io/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [DagOnStar GitHub Repository](https://github.com/CoCo-ARCOS/dagonstar-containers)

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review K3s logs: `sudo journalctl -u k3s -f`
- Verify SSH connectivity: `ssh -v user@host -p port`
- Open an issue on the [GitHub repository](https://github.com/CoCo-ARCOS/dagonstar-containers/issues)