# Complete Guide: Nomad Installation and Configuration for Dagon

## Index

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Installation on Raspberry Pi](#installation-on-raspberry-pi)
4. [Installation on PC](#installation-on-pc)
5. [Network Configuration](#network-configuration)
6. [Verifying the Installation](#verifying-the-installation)
7. [Integration with Dagon](#integration-with-dagon)
8. [Configuration Files](#configuration-files)
9. [Troubleshooting](#troubleshooting)

---

## Introduction

This guide documents the complete process of installing and configuring HashiCorp Nomad on:

- **Edge Node**: Raspberry Pi 5 (8GB RAM)
- **Fog Node**: Linux PC

The goal is to create a distributed Edge-Fog architecture to run Dagon workflows.

---

## Prerequisites

### Hardware

- **Raspberry Pi 5**: 8GB RAM, 64GB SD card
- **PC**: Linux (Ubuntu/Debian), minimum 4GB RAM

### Software

- **Operating System**: Raspberry Pi OS (64-bit) / Ubuntu 20.04+
- **Docker**: Installed on both nodes
- **Python 3**: To run Dagon scripts
- **SSH**: Configured for remote access to Raspberry Pi

### Network

- Both nodes on the same local network
- Open ports:
  - `4646`: Nomad HTTP API
  - `4647`: Nomad RPC
  - `4648`: Serf (gossip protocol)

---

## Installation on Raspberry Pi

### Method 1: Installation via APT (Recommended)

#### Step 1: Add the HashiCorp Repository

```bash
# Add GPG key
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

# Add repository
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list

# Update and install
sudo apt update
sudo apt install nomad
```

#### Step 2: Verify Installation

```bash
nomad version
# Expected output: Nomad v1.11.1 or higher

which nomad
# Output: /usr/bin/nomad
```

#### Step 3: Install Docker (if not already installed)

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Log out and log back in for the group to take effect
```

#### Step 4: Configure Nomad

Use the automated script:

```bash
chmod +x configure_nomad.sh
./configure_nomad.sh
```

Or manually create `/etc/nomad.d/nomad.hcl`:

```hcl
# Nomad configuration for Raspberry Pi

datacenter = "dc1"
data_dir = "/opt/nomad/data"

# Nomad Server
server {
  enabled = true
  bootstrap_expect = 1
}

# Nomad Client
client {
  enabled = true
  
  # Network interface (adjust according to your setup)
  network_interface = "eth0"  # or "wlan0" if using WiFi
  
  # Options
  options {
    "driver.raw_exec.enable" = "1"
  }
  
  # Host volumes available
  host_volume "home" {
    path = "/home"
    read_only = false
  }
  
  host_volume "tmp" {
    path = "/tmp"
    read_only = false
  }
  
  # Resources reserved for the system
  reserved {
    cpu = 500      # 500 MHz
    memory = 512   # 512 MB
  }
}

# Docker Plugin
plugin "docker" {
  config {
    volumes {
      enabled = true
    }
    
    allow_privileged = false
    
    gc {
      image = true
      image_delay = "5m"
      container = true
    }
  }
}

# Telemetry
telemetry {
  publish_allocation_metrics = true
  publish_node_metrics = true
  prometheus_metrics = true
}

# Logs
log_level = "INFO"
log_file = "/var/log/nomad/nomad.log"
log_rotate_max_files = 5
```

#### Step 5: Create Necessary Directories

```bash
sudo mkdir -p /opt/nomad/data
sudo mkdir -p /var/log/nomad
sudo chmod 755 /opt/nomad/data
sudo chmod 755 /var/log/nomad
```

#### Step 6: Start the Service

```bash
sudo systemctl enable nomad
sudo systemctl start nomad

# Check status
sudo systemctl status nomad
```

#### Step 7: Verify Functionality

```bash
# View nodes
nomad node status
# Expected output: 1 node with status "ready"

# View server
nomad server members
# Expected output: 1 server "alive"

# Test API
curl http://localhost:4646/v1/status/leader
# Expected output: "192.168.1.X:4647"
```

### Method 2: Installation via Automated Script

```bash
chmod +x install_nomad.sh
./install_nomad.sh
```

This script performs all the above steps automatically.

---

## Installation on PC

### Step 1: Install Nomad

Same as on Raspberry Pi:

```bash
# Add repository
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt update
sudo apt install nomad
```

### Step 2: Verify Docker

```bash
docker version

# If not installed:
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### Step 3: Configure Nomad for PC

Create `/etc/nomad.d/nomad.hcl`:

```hcl
# Nomad configuration for PC (Fog Node)

datacenter = "dc1"
data_dir = "/opt/nomad/data"

# Nomad Server
server {
  enabled = true
  bootstrap_expect = 1
}

# Nomad Client
client {
  enabled = true
  
  # Network interface
  network_interface = "eth0"  # Adjust according to your setup
  
  # Options
  options {
    "driver.raw_exec.enable" = "1"
  }
  
  # Host volumes
  host_volume "home" {
    path = "/home"
    read_only = false
  }
  
  host_volume "tmp" {
    path = "/tmp"
    read_only = false
  }
  
  # Reserved resources (more generous on PC)
  reserved {
    cpu = 1000     # 1 GHz
    memory = 2048  # 2 GB
  }
}

# Docker Plugin
plugin "docker" {
  config {
    volumes {
      enabled = true
    }
    
    allow_privileged = false
    
    gc {
      image = true
      image_delay = "5m"
      container = true
    }
  }
}

# Telemetry
telemetry {
  publish_allocation_metrics = true
  publish_node_metrics = true
  prometheus_metrics = true
}

# Logs
log_level = "INFO"
log_file = "/var/log/nomad/nomad.log"
log_rotate_max_files = 5
```

### Step 4: Start Nomad on PC

```bash
# Create directories
sudo mkdir -p /opt/nomad/data
sudo mkdir -p /var/log/nomad

# Start service
sudo systemctl enable nomad
sudo systemctl start nomad
sudo systemctl status nomad
```

### Step 5: Verify

```bash
nomad node status
nomad server members
curl http://localhost:4646/v1/status/leader
```

---

## Network Configuration

### Get IPs

```bash
# On Raspberry Pi
hostname -I
# Example output: 192.168.1.50

# On PC
hostname -I
# Example output: 192.168.1.100
```

### Check Connectivity

```bash
# From PC, check access to Nomad on Raspberry Pi
curl http://192.168.1.50:4646/v1/status/leader

# From Raspberry Pi, check access to Nomad on PC
curl http://192.168.1.100:4646/v1/status/leader
```

### Firewall (if necessary)

```bash
# Open ports in firewall
sudo ufw allow 4646/tcp
sudo ufw allow 4647/tcp
sudo ufw allow 4648/tcp
```

---

## Verifying the Installation

### Automated Verification Script

Use the `check_nomad.sh` script:

```bash
chmod +x check_nomad.sh
./check_nomad.sh
```

### Manual Verification

#### 1. Service Status

```bash
sudo systemctl status nomad
```

**Expected output:**

```
● nomad.service - Nomad
   Loaded: loaded
   Active: active (running)
```

#### 2. Available Nodes

```bash
nomad node status
```

**Expected output:**

```
ID        DC   Name         Class   Drain  Eligibility  Status
abc123... dc1  raspberrypi  <none>  false  eligible     ready
```

#### 3. Functional API

```bash
curl http://localhost:4646/v1/status/leader
```

**Expected output:**

```
"192.168.1.50:4647"
```

#### 4. Docker Available

```bash
nomad node status -verbose | grep -A 10 "Drivers"
```

**Expected output:**

```
Drivers
  docker = healthy
```

#### 5. Web UI Accessible

Open your browser:

- Raspberry Pi: `http://192.168.1.50:4646/ui`
- PC: `http://localhost:4646/ui`

---

## Integration with Dagon

### 1. Copy nomad_task.py

```bash
# Copy the NomadTask implementation to Dagon
cp nomad_task.py ~/dagon/dagon/nomad_task.py
```

### 2. Update task.py

Edit `~/dagon/dagon/task.py`:

**Add to the TaskType class:**

```python
class TaskType(Enum):
    # ... existing types ...
    NOMAD = "nomad"
```

**Add to tasks_types:**

```python
tasks_types = {
    # ... existing types ...
    TaskType.NOMAD: ("dagon.nomad_task", "NomadTask")
}
```

### 3. Configure dagon.ini

Create or edit `dagon.ini`:

```ini
[ssh]
raspi_ip = 192.168.1.50
raspi_user = raspi
raspi_port = 22

[batch]
scratch_dir_base = /tmp/dagon_scratch
threads = 4

[dagon_service]
use = False

[nomad]
# For edge-only scripts (everything on Raspberry)
address = http://192.168.1.50:4646

# For edge-fog scripts (distributed)
edge_address = http://192.168.1.50:4646
fog_address = http://localhost:4646

datacenter = dc1
region = global
```

### 4. Pre-download Docker Images

```bash
# On Raspberry Pi
docker pull ubuntu:22.04

# On PC
docker pull ubuntu:22.04
```

### 5. Run Tests

```bash
# Edge-only workflow
python edge_nomad_script.py

# Edge-fog workflow
python edge_fog_nomad_script.py
```

---

## Configuration Files

### File Structure

```
nomad-dagon-integration/
├── nomad_task.py                    # NomadTask implementation
├── task_updated.py                  # Changes for task.py
├── edge_nomad_script.py             # Edge-only example
├── edge_fog_nomad_script.py         # Edge-fog example
├── test_nomad_integration.py        # Tests
├── configure_nomad.sh               # Automated configuration
├── install_nomad.sh                 # Automated installation
├── check_nomad.sh                   # Verification
├── nomad.hcl                        # Nomad config example
├── dagon.ini.example                # Dagon config example
└── README.md                        # Documentation
```

### Key Files

#### nomad_task.py

Location: `~/dagon/dagon/nomad_task.py`

Full implementation of NomadTask and RemoteNomadTask for integration with Dagon.

#### nomad.hcl

Location: `/etc/nomad.d/nomad.hcl`

Main Nomad configuration with:

- Server and client on the same node
- Docker driver enabled
- Volumes configured
- Telemetry enabled

#### dagon.ini

Location: `~/dagon.ini` (or in the project directory)

Dagon configuration with:

- SSH credentials
- Nomad addresses
- Workflow configuration

---

## Troubleshooting

### Problem 1: Nomad Does Not Start

**Symptom:**

```bash
sudo systemctl status nomad
# Active: failed
```

**Solution:**

```bash
# View logs
sudo journalctl -u nomad -n 50

# Check configuration
nomad agent -config=/etc/nomad.d/nomad.hcl -dev-connect

# Retry
sudo systemctl restart nomad
```

### Problem 2: Node in "down" State

**Symptom:**

```bash
nomad node status
# Status: down
```

**Solution:**

```bash
# Restart Nomad
sudo systemctl restart nomad

# Check Docker
docker ps

# View logs
sudo journalctl -u nomad -f
```

### Problem 3: Jobs in "pending"

**Symptom:**

```bash
nomad job status <job-id>
# Status: pending
# Placement Failure: No nodes were eligible
```

**Solution:**

```bash
# Check node resources
nomad node status -verbose

# Check Docker driver
nomad node status -verbose | grep -A 10 "Drivers"

# Verify the node is "ready"
nomad node status
```

### Problem 4: "Connection refused" When Connecting to Nomad

**Symptom:**

```
ConnectionError: Failed to establish connection to localhost:4646
```

**Solution:**

```bash
# Check that Nomad is running
sudo systemctl status nomad

# Check port
sudo netstat -tlnp | grep 4646

# Check firewall
sudo ufw status

# Test connection
curl http://localhost:4646/v1/status/leader
```

### Problem 5: Docker Not Available in Nomad

**Symptom:**

```bash
nomad node status -verbose | grep docker
# docker = unhealthy
```

**Solution:**

```bash
# Check Docker
sudo systemctl status docker
docker ps

# Add user to Docker group
sudo usermod -aG docker $USER
# Log out and log back in

# Restart Nomad
sudo systemctl restart nomad
```

### Problem 6: Bash Variables Not Recognized

**Symptom:**

```
Failed Validation: Unknown variable: There is no variable named "i"
```

**Solution:**

This has already been fixed in the scripts, but if it occurs:

- Make sure bash variables use `$i` without additional braces
- Verify that `${{variable}}` is only used for bash parameter expansion
- Do not use double braces `{{` in Python f-strings

### Problem 7: Files Not Transferred Between Edge and Fog

**Symptom:**

```bash
ERROR: Input directory not found
```

**Solution:**

```bash
# Check SSH
ssh raspi@192.168.1.50 'ls /home/raspi/edge_files_*'

# Check permissions
ls -la /tmp/fog_input_*

# Run SCP manually for debugging
scp -r raspi@192.168.1.50:/home/raspi/edge_files_*/* /tmp/test/
```

---

## Useful Commands

### Nomad Management

```bash
# View service status
sudo systemctl status nomad

# Start/stop/restart
sudo systemctl start nomad
sudo systemctl stop nomad
sudo systemctl restart nomad

# View logs in real time
sudo journalctl -u nomad -f

# View logs from file
tail -f /var/log/nomad/nomad.log
```

### Nomad CLI Commands

```bash
# Jobs
nomad job status                    # List all jobs
nomad job status <job-id>           # Job details
nomad job stop <job-id>             # Stop job
nomad job stop -purge <job-id>      # Stop and purge

# Allocations
nomad alloc status                  # List allocations
nomad alloc status <alloc-id>       # Details
nomad alloc logs <alloc-id>         # View logs
nomad alloc logs -f <alloc-id>      # Real-time logs

# Nodes
nomad node status                   # List nodes
nomad node status -verbose          # With details
nomad node drain <node-id>          # Drain node

# Server
nomad server members                # View servers
nomad server force-leave <node>     # Remove server

# System
nomad system gc                     # Garbage collection
nomad system reconcile summaries    # Reconcile state
```

### Monitoring

```bash
# Nomad CPU and memory
top -p $(pgrep nomad)

# Node statistics
nomad node status -stats

# View evaluations
nomad eval status

# Check cluster health
nomad operator raft list-peers
```

---

## Additional Resources

### Official Documentation

- [Nomad Documentation](https://developer.hashicorp.com/nomad/docs)
- [Nomad Docker Driver](https://developer.hashicorp.com/nomad/docs/drivers/docker)
- [Nomad API Reference](https://developer.hashicorp.com/nomad/api-docs)

### Web UIs

- **Raspberry Pi**: `http://192.168.1.50:4646/ui`
- **PC**: `http://localhost:4646/ui`

### Log Files

- **Service**: `sudo journalctl -u nomad`
- **File**: `/var/log/nomad/nomad.log`

### Configuration Files

- **Nomad config**: `/etc/nomad.d/nomad.hcl`
- **Systemd service**: `/lib/systemd/system/nomad.service`
- **Data directory**: `/opt/nomad/data`

---

## Installation Summary

### Raspberry Pi (Edge Node)

```bash
# 1. Install Nomad via APT
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install nomad

# 2. Configure
./configure_nomad.sh

# 3. Verify
./check_nomad.sh
```

### PC (Fog Node)

```bash
# Repeat the same steps as on Raspberry Pi
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install nomad
./configure_nomad.sh
./check_nomad.sh
```

### Dagon Integration

```bash
# 1. Copy nomad_task.py
cp nomad_task.py ~/dagon/dagon/

# 2. Update task.py (see Integration section)

# 3. Configure dagon.ini

# 4. Run tests
python edge_fog_nomad_script.py
```

---
