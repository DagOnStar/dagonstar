# Metrics Monitoring Configuration Guide

This guide provides step-by-step instructions for setting up a complete monitoring stack across edge and fog computing nodes. The system uses Prometheus for metrics collection, Node Exporter for system metrics, custom exporters for hardware-specific data, and Grafana for visualization.

## Table of Contents
- [Raspberry Pi 5 Setup (Edge Node)](#raspberry-pi-5-edge-node)
- [PC Setup (Fog Node)](#pc-fog-node)
- [Grafana Installation](#grafana-installation)

---

## Raspberry Pi 5 (Edge Node)

### Installing Node Exporter

Node Exporter is a Prometheus exporter that collects hardware and OS-level metrics from Linux systems. It exposes metrics like CPU usage, memory, disk I/O, network statistics, and more.

```bash
# Update package repositories to get the latest package information
sudo apt update

# Install Node Exporter from the official Debian/Ubuntu repositories
sudo apt install prometheus-node-exporter -y

# Enable the service to start automatically on boot
sudo systemctl enable prometheus-node-exporter

# Start the Node Exporter service immediately
sudo systemctl start prometheus-node-exporter

# Check the service status to ensure it's running correctly
sudo systemctl status prometheus-node-exporter
```

#### Verification

Node Exporter runs on port 9100 by default and exposes metrics via an HTTP endpoint.

```bash
# Test that Node Exporter is working by fetching metrics locally
# You should see hundreds of lines of metrics in Prometheus format
curl http://localhost:9100/metrics
```

### Enabling Textfile Collector in Node Exporter

The textfile collector allows you to expose custom metrics by writing them to files in a specific directory. This is useful for metrics that aren't collected by Node Exporter's built-in collectors.

```bash
# Create the directory where custom metric files will be stored
sudo mkdir -p /var/lib/node_exporter/textfile_collector

# Set permissions to allow writing (777 is used for simplicity; in production, use more restrictive permissions)
sudo chmod 777 /var/lib/node_exporter/textfile_collector

# Add the 'raspi' user to the 'prometheus' group
# This allows the raspi user to write metrics files that prometheus can read
sudo usermod -a -G prometheus raspi

# Set proper ownership: prometheus user, raspi group
sudo chown prometheus:raspi /var/lib/node_exporter/textfile_collector

# Alternative: If you want prometheus to own everything
# sudo chown -R prometheus:prometheus /var/lib/node_exporter
```

#### Verification

Check if custom metrics (in this case, metrics containing "dagon") are being exported:

```bash
# Search for custom metrics in the Node Exporter output
curl localhost:9100/metrics | grep dagon
```

### Configuring Node Exporter to Use Textfile Collector

By default, Node Exporter doesn't enable the textfile collector. We need to modify its systemd service configuration to add the necessary command-line flag.

```bash
# Edit the systemd service configuration for Node Exporter
# This creates an override file that won't be overwritten during package updates
sudo systemctl edit prometheus-node-exporter
```

An empty editor will open. Paste the following configuration:

```bash
[Service]
# Clear the default ExecStart directive
ExecStart=

# Set a new ExecStart with the textfile collector enabled
ExecStart=/usr/bin/prometheus-node-exporter \
  --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

After saving the file, reload systemd and restart the service:

```bash
# Re-execute systemd (reload the systemd manager configuration)
sudo systemctl daemon-reexec

# Reload all systemd unit files (pick up our changes)
sudo systemctl daemon-reload

# Restart Node Exporter with the new configuration
sudo systemctl restart prometheus-node-exporter
```

Verify that the textfile collector flag is active:

```bash
# Check the running process to confirm the flag is present
ps aux | grep prometheus-node-exporter
# You should see: --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

Verify that metrics are being exported correctly:

```bash
# Test that Node Exporter is still working after the configuration change
curl http://localhost:9100/metrics | grep node_cpu
```

### Viewing Internal PMIC Data (Real Hardware)

The Raspberry Pi 5 has a Power Management Integrated Circuit (PMIC) that monitors power consumption across different voltage rails. This data is accessible via the `vcgencmd` command.

```bash
# Read power consumption data from the Raspberry Pi's PMIC
vcgencmd pmic_read_adc
```

Expected output:
```
 3V7_WL_SW_A current(0)=0.09466522A
   3V3_SYS_A current(1)=0.08197812A
   1V8_SYS_A current(2)=0.15029320A
  DDR_VDD2_A current(3)=0.00390372A
  DDR_VDDQ_A current(4)=0.00000000A
   1V1_SYS_A current(5)=0.20299340A
    0V8_SW_A current(6)=0.30546610A
  VDD_CORE_A current(7)=1.11625000A
   3V3_DAC_A current(17)=0.00000000A
   3V3_ADC_A current(18)=0.00018315A
   0V8_AON_A current(16)=0.00274725A
      HDMI_A current(22)=0.01660560A
 3V7_WL_SW_V volt(8)=3.62925200V
   3V3_SYS_V volt(9)=3.31652900V
   1V8_SYS_V volt(10)=1.79877700V
  DDR_VDD2_V volt(11)=1.10146400V
  DDR_VDDQ_V volt(12)=0.60622650V
   1V1_SYS_V volt(13)=1.10402800V
    0V8_SW_V volt(14)=0.79853400V
  VDD_CORE_V volt(15)=0.74944980V
   3V3_DAC_V volt(20)=3.31043600V
   3V3_ADC_V volt(21)=3.31684600V
   0V8_AON_V volt(19)=0.79794790V
      HDMI_V volt(23)=5.10138000V
     EXT5V_V volt(24)=5.08530000V
      BATT_V volt(25)=0.00000000V
```

**Understanding the data:**
- Each voltage rail is listed with both current (A) and voltage (V) measurements
- Power per rail is calculated as: **P = V × I** (Power = Voltage × Current)
- Total Raspberry Pi power consumption is: **P_total = Σ (V_i × I_i)** (sum of all rail powers)

The main voltage rails and their purposes:
- **VDD_CORE**: CPU core voltage (typically the highest power consumer)
- **3V3_SYS**: 3.3V system rail (GPIO, peripherals)
- **1V8_SYS**: 1.8V system rail (some peripherals)
- **DDR_VDD2/VDDQ**: Memory power rails
- **HDMI**: HDMI output power
- **3V7_WL_SW**: WiFi/wireless power

### Custom Prometheus Exporter for Raspberry Pi PMIC

We create a custom exporter (similar in concept to Scaphandre but using real physical PMIC data) to expose Raspberry Pi power consumption metrics to Prometheus.

**See: rpi_pmic_exporter.py**

This Python script should be placed at `/usr/local/bin/rpi_pmic_exporter.py` on the Raspberry Pi. The script:
1. Calls `vcgencmd pmic_read_adc` to get power data
2. Parses the voltage and current values
3. Calculates power consumption for each rail (P = V × I)
4. Exposes metrics on port 9101 in Prometheus format

Make the script executable:

```bash
# Add execute permissions to the exporter script
sudo chmod +x /usr/local/bin/rpi_pmic_exporter.py
```

### Creating a Systemd Service for the PMIC Exporter

To run the exporter automatically and reliably, we create a systemd service.

Create a file at `/etc/systemd/system/rpi-pmic-exporter.service`:

```bash
[Unit]
# Service description
Description=Raspberry Pi PMIC Prometheus Exporter
# Start after networking is available
After=network.target

[Service]
# Run as a simple foreground process
Type=simple
# Command to execute (using Python 3 to run our exporter script)
ExecStart=/usr/bin/python3 /usr/local/bin/rpi_pmic_exporter.py
# Automatically restart if the service crashes
Restart=always

[Install]
# Start this service when the system reaches multi-user mode (normal boot)
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Reload systemd to recognize the new service file
sudo systemctl daemon-reload

# Enable the service to start on boot and start it immediately
sudo systemctl enable --now rpi-pmic-exporter
```

Verify the exporter is working:

```bash
# Fetch metrics from the PMIC exporter
# You should see power consumption data for each voltage rail
curl localhost:9101/metrics | grep rpi_pmic
```

Expected output:

```
# HELP rpi_pmic_power_watts Total Raspberry Pi power consumption (PMIC)
# TYPE rpi_pmic_power_watts gauge
rpi_pmic_power_watts 1.9255070147064302

# HELP rpi_pmic_rail_power_watts Power consumption per PMIC rail
# TYPE rpi_pmic_rail_power_watts gauge
rpi_pmic_rail_power_watts{rail="3V7_WL_SW"} 0.32880673246644
rpi_pmic_rail_power_watts{rail="3V3_SYS"} 0.3767178533456
rpi_pmic_rail_power_watts{rail="1V8_SYS"} 0.2740037277054
rpi_pmic_rail_power_watts{rail="DDR_VDD2"} 0.007529669827470001
rpi_pmic_rail_power_watts{rail="DDR_VDDQ"} 0.0
rpi_pmic_rail_power_watts{rail="1V1_SYS"} 0.2397142538336
rpi_pmic_rail_power_watts{rail="0V8_SW"} 0.21979063163771997
rpi_pmic_rail_power_watts{rail="VDD_CORE"} 0.39514565068999996
rpi_pmic_rail_power_watts{rail="3V3_DAC"} 0.00020204619600000003
rpi_pmic_rail_power_watts{rail="3V3_ADC"} 0.001619053326
rpi_pmic_rail_power_watts{rail="0V8_AON"} 0.0021442349742000003
rpi_pmic_rail_power_watts{rail="HDMI"} 0.07983316070400001
```


### Modify SIF image to include dependencies for the container tasks

#### On the RasPi, create a definition file:
```bash
cat > ~/python_dht.def << 'EOF'
Bootstrap: docker
From: python:3.9-slim

%post
    # Pre-install all dependencies
    pip install --no-cache-dir pyserial pandas pymongo

%runscript
    exec "$@"
EOF
```
#### Build the new image:
```bash
sudo apptainer build python_dht.sif python_dht.def
```
---

## PC (Fog Node)

### Installing Node Exporter

The same Node Exporter we installed on the Raspberry Pi is also needed on the fog node (PC) to collect system-level metrics.

```bash
# Update package repositories
sudo apt update

# Install Node Exporter
sudo apt install prometheus-node-exporter -y

# Check the service status
sudo systemctl status prometheus-node-exporter
```

#### Verification

```bash
# Test Node Exporter on the PC
curl http://localhost:9100/metrics
```

### Installing Scaphandre

Scaphandre is a power consumption monitoring tool for x86 systems. It uses Intel RAPL (Running Average Power Limit) to measure CPU and memory power consumption. This is the fog node equivalent of the Raspberry Pi PMIC exporter.

Before installing, ensure your system supports RAPL:

```bash
# Load the Intel RAPL kernel module (for kernels >= 5.x)
sudo modprobe intel_rapl_common

# For older kernels (< 5.x), use:
# sudo modprobe intel_rapl

# Verify that the RAPL interface exists
# If this directory exists, your CPU supports RAPL
ls /sys/class/powercap/intel-rapl/
```

**Note:** RAPL is available on:
- Intel CPUs: Sandy Bridge (2011) and newer
- AMD CPUs: Zen (2017) and newer

Download the official Debian package (version 1.0.0):

```bash
# Navigate to temporary directory
cd /tmp

# Download the Scaphandre Debian package
curl -LO https://github.com/barnumbirr/scaphandre-debian/releases/download/v1.0.0-1/scaphandre_1.0.0-1_amd64_bookworm.deb
```

Install the package:

```bash
# Install Scaphandre using apt (handles dependencies automatically)
sudo apt install ./scaphandre_1.0.0-1_amd64_bookworm.deb
```

#### Verification

```bash
# Check Scaphandre version
scaphandre --version

# View power consumption metrics in the terminal
# -t 5 means refresh every 5 seconds
sudo scaphandre stdout -t 5
```

### Enabling Textfile Collector in Node Exporter

Same process as on the Raspberry Pi, but without the raspi user:

```bash
# Create the textfile collector directory
sudo mkdir -p /var/lib/node_exporter/textfile_collector

# Set ownership to prometheus user and group
sudo chown -R prometheus:prometheus /var/lib/node_exporter
```

#### Verification

```bash
# Check if custom metrics are being exported
curl localhost:9100/metrics | grep dagon
```

### Installing Prometheus

Prometheus is the time-series database that collects and stores metrics from all exporters. It runs on the fog node and scrapes metrics from:
- Local Node Exporter (PC system metrics)
- Local Scaphandre (PC power consumption)
- Remote Node Exporter (Raspberry Pi system metrics)
- Remote PMIC Exporter (Raspberry Pi power consumption)

```bash
# Install Prometheus from the official Debian repository
sudo apt install prometheus -y
```

#### Verification

```bash
# Check Prometheus version
prometheus --version

# Verify the service is running
sudo systemctl status prometheus
```

Prometheus web interface is accessible at: **http://localhost:9090**

### Configuring Node Exporter

Same configuration as on the Raspberry Pi to enable the textfile collector:

```bash
# Edit the systemd service override file
sudo systemctl edit prometheus-node-exporter
```

Paste this configuration in the empty editor:

```bash
[Service]
# Clear the default ExecStart
ExecStart=

# Add the textfile collector flag
ExecStart=/usr/bin/prometheus-node-exporter \
  --collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

Reload and restart:

```bash
# Reload systemd configuration
sudo systemctl daemon-reexec
sudo systemctl daemon-reload

# Restart Node Exporter with new settings
sudo systemctl restart prometheus-node-exporter
```

Verify the configuration:

```bash
# Check that the process is running with the correct flag
ps aux | grep prometheus-node-exporter

# Verify metrics are being exported
curl localhost:9100/metrics | grep dagon
```

### Configuring Prometheus Scrape Targets

Edit the Prometheus configuration file:

```bash
sudo nano /etc/prometheus/prometheus.yml
```

Configure the scrape jobs (replace the `scrape_configs` section):

```yaml
scrape_configs:
  # Prometheus monitoring itself
  - job_name: 'prometheus'
    scrape_interval: 5s  # Collect metrics every 5 seconds
    scrape_timeout: 5s   # Timeout after 5 seconds if target doesn't respond
    static_configs:
      - targets: ['localhost:9090']

  # Node Exporter on the PC (fog/cloud node)
  # Collects system metrics: CPU, memory, disk, network, etc.
  - job_name: 'node-pc'
    static_configs:
      - targets: ['localhost:9100']

  # Node Exporter on the Raspberry Pi (edge node)
  # Collects the same system metrics but from the remote edge device
  - job_name: 'node-rpi'
    static_configs:
      - targets:
        - 'RASPBERRY_PI_IP:9100'  # Replace with actual Raspberry Pi IP address
```

**Important:** Replace `RASPBERRY_PI_IP` with your actual Raspberry Pi IP address (e.g., `192.168.1.100`).

## Adding Scaphandre to Prometheus

### Creating a Systemd Service for Scaphandre in Prometheus Mode

Scaphandre can run in different modes. The "prometheus" mode exposes an HTTP endpoint that Prometheus can scrape.

Create the systemd service file:

```bash
sudo nano /etc/systemd/system/scaphandre.service
```

Paste this configuration:

```bash
[Unit]
Description=Scaphandre Prometheus Exporter
After=network.target

[Service]
Type=simple
User=root  # Running as root because RAPL requires elevated privileges
ExecStart=/usr/bin/scaphandre prometheus  # Start in Prometheus exporter mode
Restart=on-failure  # Restart if the service crashes
RestartSec=5  # Wait 5 seconds before restarting
LimitNOFILE=1048576  # Increase file descriptor limit

[Install]
WantedBy=multi-user.target
```

**Note:** Scaphandre runs as root because accessing `/sys/class/powercap/` requires root privileges.

Start and enable the service:

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Start Scaphandre immediately
sudo systemctl start scaphandre

# Check service status
sudo systemctl status scaphandre

# Enable Scaphandre to start on boot
sudo systemctl enable scaphandre
```

Edit the Prometheus configuration:

```bash
sudo nano /etc/prometheus/prometheus.yml
```

Add a new scrape job for Scaphandre (DO NOT mix with the node-pc job):

```yaml
  # Scaphandre power consumption metrics for the PC
  # This runs on port 8080 by default (different from Node Exporter's 9100)
  - job_name: "scaphandre"
    scrape_interval: 5s
    static_configs:
      - targets: ["localhost:8080"]
```

Reload Prometheus to apply changes:

```bash
# Restart Prometheus to pick up the new configuration
sudo systemctl restart prometheus
```

Verify in the Prometheus web UI:
- Navigate to **http://localhost:9090/targets**
- You should see the "scaphandre" job listed and showing as "UP"

Verify that Scaphandre is exposing metrics:

```bash
# Fetch metrics from Scaphandre
# You should see power consumption metrics for CPU, RAM, etc.
curl http://localhost:8080/metrics | grep scaph
```

Common Scaphandre metrics:
- `scaph_host_power_microwatts`: Total host power consumption
- `scaph_process_power_consumption_microwatts`: Per-process power consumption
- `scaph_socket_power_microwatts`: Per-CPU-socket power consumption

## Adding Raspberry Pi PMIC to PC Prometheus

To complete the monitoring setup, configure Prometheus on the PC to also scrape metrics from the Raspberry Pi's PMIC exporter.

Edit the Prometheus configuration on the PC:

```bash
sudo nano /etc/prometheus/prometheus.yml
```

Add the PMIC exporter job (this should be in addition to the jobs already configured):

```yaml
  # Node Exporter on Raspberry Pi (system metrics)
  - job_name: 'node-rpi'
    static_configs:
      - targets:
        - 'RASPBERRY_PI_IP:9100'  # Replace with actual IP

  # Scaphandre on PC (power metrics)
  - job_name: 'scaphandre'
    static_configs:
      - targets: ['localhost:8080']

  # PMIC Exporter on Raspberry Pi (power metrics)
  # This gives us detailed power consumption per voltage rail
  - job_name: 'pmic-rpi'
    static_configs:
      - targets: ['RASPBERRY_PI_IP:9101']  # Replace with actual IP
```

**Important:** Replace `RASPBERRY_PI_IP` with your Raspberry Pi's actual IP address in both places.

Restart Prometheus:

```bash
sudo systemctl restart prometheus
```

Verify all targets are being scraped:
- Open **http://localhost:9090/targets**
- You should see all four jobs (prometheus, node-pc, node-rpi, scaphandre, pmic-rpi) showing as "UP"
- If any target shows as "DOWN", check:
  - Network connectivity between PC and Raspberry Pi
  - Firewall rules (ports 9100 and 9101 must be open)
  - That the exporters are running on the Raspberry Pi

---

## Grafana Installation

Grafana is a visualization and analytics platform that creates dashboards from Prometheus data. It provides a web interface for creating graphs, alerts, and monitoring infrastructure.

### Installing Prerequisites

```bash
# Install required packages for adding the Grafana repository
sudo apt-get install -y apt-transport-https wget
```

### Importing the GPG Key

Grafana packages are signed with a GPG key to verify authenticity:

```bash
# Create directory for keyrings if it doesn't exist
sudo mkdir -p /etc/apt/keyrings/

# Download and import the Grafana GPG key
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
```

### Adding the Grafana Repository

**For stable releases:**

```bash
# Add the Grafana stable repository to APT sources
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
```

**For beta releases (optional):**

```bash
# Add the Grafana beta repository (if you want to test new features)
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com beta main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
```

### Installing Grafana

```bash
# Update package list to include Grafana
sudo apt-get update

# Install Grafana OSS (Open Source Software) edition
sudo apt-get install grafana
```

### Starting the Grafana Service

```bash
# Reload systemd daemon to recognize Grafana service
sudo systemctl daemon-reload

# Start Grafana server
sudo systemctl start grafana-server

# Enable Grafana to start on boot (optional but recommended)
sudo systemctl enable grafana-server

# Check Grafana service status
sudo systemctl status grafana-server
```

### Accessing Grafana

Grafana web interface is available at: **http://localhost:3000**

**Default credentials:**
- Username: `admin`
- Password: `admin`

**Note:** You will be prompted to change the password on first login.

### Adding Prometheus as a Data Source

After logging in to Grafana:

1. **Navigate to Data Sources:**
   - Click the gear icon (⚙️) on the left sidebar
   - Select "Data sources"
   - Click "Add data source"

2. **Select Prometheus:**
   - Find and click on "Prometheus" from the list

3. **Configure the connection:**
   - **URL:** `http://localhost:9090` (this is where Prometheus is running)
   - Leave other settings as default
   - Click "Save & Test"

4. **Verify connection:**
   - You should see a green message: "Data source is working"

### Creating Dashboards

Now you can create dashboards to visualize your metrics:

**Example queries to get started:**
- `rpi_pmic_power_watts` - Total Raspberry Pi power consumption
- `scaph_host_power_microwatts / 1000000` - PC power in watts
- `rate(node_cpu_seconds_total[5m])` - CPU usage
- `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes` - Memory usage percentage
- `rate(node_network_receive_bytes_total[5m])` - Network receive rate

**Popular community dashboards:**
- Node Exporter Full: Dashboard ID `1860`
- Scaphandre Overview: Create custom dashboard with power metrics

### Grafana API Token (For Automation)

If you need to automate dashboard creation or access Grafana programmatically:

1. Go to Configuration → API Keys
2. Click "Add API key"
3. Set permissions and expiration
4. Copy the generated token

**Your token:** `123...` (replace with actual token when generated)

### Importing the Dagon Tasks Dashboard on the PC

Once Prometheus is configured as a data source in Grafana, you can import the prepared dashboard to visualize Raspberry Pi, PC, and Dagon workflow metrics.

1. Copy the file `grafana-dashboard-dagon-tasks.json` to the PC where Grafana is installed (for example to your home directory or `/tmp`).  
2. Open Grafana at `http://localhost:3000` in your browser and log in with your credentials.  
3. In the left sidebar, click on the **Dashboards** icon, then select **New → Import**.  
4. On the Import page, click **Upload JSON file** and select the `grafana-dashboard-dagon-tasks.json` file.  
5. In the **Folder** field, choose where you want to store the dashboard (for example, “General”).  
6. In the **Prometheus** data source field, select the data source that points to `http://localhost:9090`. The dashboard JSON is configured to use a Prometheus data source, so make sure you select the correct one.  
7. Click **Import**.

After importing, the dashboard will include panels such as:

- Raspberry Pi power consumption from the PMIC exporter (for example, `rpi_pmic_power_watts`).  
- PC power consumption from Scaphandre (for example, `scaph_host_power_microwatts / 1000000`).  
- CPU and RAM usage for both Raspberry Pi and PC using Node Exporter metrics (for example, `node_cpu_seconds_total` and `node_memory_*`).  
- Workflow start and end events as annotations (for example, `dagon_workflow_start` and `dagon_workflow_end`).

---

## Summary of the Complete Setup

**On Raspberry Pi 5 (Edge Node):**
- Node Exporter (port 9100) - System metrics
- PMIC Exporter (port 9101) - Power consumption metrics

**On PC (Fog Node):**
- Prometheus (port 9090) - Metrics collection and storage
- Node Exporter (port 9100) - PC system metrics
- Scaphandre (port 8080) - PC power consumption metrics
- Grafana (port 3000) - Visualization and dashboards

**Metrics Flow:**
1. Exporters collect metrics (Node Exporter, Scaphandre, PMIC)
2. Prometheus scrapes metrics from all exporters every 5 seconds
3. Prometheus stores metrics in its time-series database
4. Grafana queries Prometheus and displays data in dashboards
5. Users access Grafana web interface to monitor the system

**Key Files:**
- `/etc/prometheus/prometheus.yml` - Prometheus configuration
- `/etc/systemd/system/scaphandre.service` - Scaphandre service
- `/etc/systemd/system/rpi-pmic-exporter.service` - PMIC exporter service
- `/usr/local/bin/rpi_pmic_exporter.py` - PMIC exporter script

**Troubleshooting Tips:**
- Check service status: `sudo systemctl status <service-name>`
- View service logs: `sudo journalctl -u <service-name> -f`
- Test connectivity: `curl http://<ip>:<port>/metrics`
- Verify Prometheus targets: http://localhost:9090/targets
- Check firewall: `sudo ufw status` (ensure ports are open)