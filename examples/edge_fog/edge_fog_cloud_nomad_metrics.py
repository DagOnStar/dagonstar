#!/usr/bin/env python3
"""
Dagon DHT Workflow with Energy Metrics Capture using Nomad
Integrates: DHT sensor + MongoDB + Prometheus energy metrics
Architecture: Edge (Raspberry Pi) + Fog (PC) using Nomad orchestration
"""

import json, configparser, logging, time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from datetime import datetime, timezone
from pymongo import MongoClient
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from energy_metrics_collector import PrometheusMetricsCollector

# Read configuration
config = configparser.ConfigParser()
config.read('dagon.ini')

RASPI_IP = config.get('ssh', 'raspi_ip')
RASPI_USER = config.get('ssh', 'raspi_user')
try:
    RASPI_PORT = config.getint('ssh', 'raspi_port')
except (configparser.NoOptionError, ValueError):
    RASPI_PORT = 22

MONGO_URI = config.get('mongodb', 'uri')
MONGO_DB = config.get('mongodb', 'database')
MONGO_COLLECTION = config.get('mongodb', 'collection')

PROMETHEUS_URL = config.get('prometheus', 'url', fallback='http://localhost:9090')
SAMPLING_INTERVAL = config.getint('prometheus', 'sampling_interval', fallback=2)

# Nomad configuration for Edge (Raspberry Pi)
try:
    EDGE_NOMAD_ADDRESS = config.get('nomad', 'edge_address')
except (configparser.NoOptionError, configparser.NoSectionError):
    EDGE_NOMAD_ADDRESS = f"http://{RASPI_IP}:4646"

# Nomad configuration for Fog (localhost)
try:
    FOG_NOMAD_ADDRESS = config.get('nomad', 'fog_address')
except (configparser.NoOptionError, configparser.NoSectionError):
    FOG_NOMAD_ADDRESS = "http://localhost:4646"

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("Dagon DHT Workflow with Energy Monitoring - Nomad")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node (Raspberry Pi): {RASPI_IP} - Task A")
print(f"  Nomad: {EDGE_NOMAD_ADDRESS}")
print(f"Fog Node (PC): localhost - Tasks B & C")
print(f"  Nomad: {FOG_NOMAD_ADDRESS}")
print(f"MongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print(f"Prometheus: {PROMETHEUS_URL}")
print(f"Sampling: every {SAMPLING_INTERVAL}s")
print("="*70 + "\n")

# Pre-create directories
FOG_DATA_DIR = f"/tmp/fog_data_{EXECUTION_ID}"

print("Creating local directories...")
os.makedirs(FOG_DATA_DIR, mode=0o777, exist_ok=True)
print(f"✓ Directories created: {FOG_DATA_DIR}\n")

# ========== TASK A: DHT Sensor Capture (EDGE) ==========
taskA_command = f"""
set -e
TASK="A"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"
EXECUTION_ID="{EXECUTION_ID}"

METRICS_TMP="/tmp/dagon_$${{TASK}}.prom"
METRICS_DIR="/var/lib/node_exporter/textfile_collector"
METRICS_CURRENT="$${{METRICS_DIR}}/dagon_dht_$${{TASK}}_current.prom"
METRICS_HISTORY="/home/{RASPI_USER}/.dagon_metrics/history/dagon_dht_$${{TASK}}_{EXECUTION_ID}.prom"
METRICS_BACKUP="/home/{RASPI_USER}/.dagon_metrics/dagon_dht_$${{TASK}}.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

LOG_FILE="/home/{RASPI_USER}/dagon_capture_{EXECUTION_ID}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Task A: DHT Sensor Capture (EDGE - Nomad)"
echo "Execution ID: {EXECUTION_ID}"
echo "Date: $(date)"
echo "Note: Running in containerized environment"
echo "=========================================="

# Install pyserial (needed for sensor access)
echo "Installing dependencies..."
pip3 install --quiet --no-cache-dir pyserial 2>&1 | grep -v "already satisfied" || true

# Check if running in container - if so, look for mounted sensor data
# Otherwise try to access the sensor directly
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "Running in container - checking for pre-captured data..."
    
    # Try to use pre-captured data if available
    PRECAPTURED="/home/{RASPI_USER}/sensor_precaptured.json"
    if [ -f "$PRECAPTURED" ]; then
        echo "Using pre-captured sensor data"
        cp "$PRECAPTURED" output.json
        RECORDS=$(python3 -c "import json; print(len(json.load(open('output.json'))))" 2>/dev/null || echo 0)
        echo "RECORDS_CAPTURED=$RECORDS"
    else
        echo "No pre-captured data found - generating simulated DHT11 data..."
        
        python3 << 'EOF'
import json, time, random

# Simulate DHT11 readings for 300 seconds
DURATION = 300
OUTPUT_FILE = 'output.json'

print(f"Simulating DHT11 sensor for {{DURATION}}s...")
data = []
start = time.time()

while time.time() - start < DURATION:
    # Generate realistic DHT11 values
    humidity = random.uniform(40, 70)  # DHT11 typical range
    temp_c = random.uniform(20, 30)    # DHT11 typical range
    
    data.append({{
        'timestamp': time.time(),
        'humidity': round(humidity, 1),
        'temp_c': round(temp_c, 1),
        'simulated': True
    }})
    
    time.sleep(2)  # DHT11 typical sampling rate

print(f"RECORDS_CAPTURED={{len(data)}}")
json.dump(data, open(OUTPUT_FILE, 'w'), indent=2)
print(f"Simulated data saved to {{OUTPUT_FILE}} ({{len(data)}} records)")
EOF
    fi
else
    echo "Running on host - attempting direct sensor access..."
    
    python3 << 'EOF'
import serial, re, json, time, os

PORT = '/dev/ttyACM0'
BAUDRATE = 9600
DURATION = 300
OUTPUT_FILE = 'output.json'

print(f"Configuration:\\n  Port: {{PORT}}\\n  Duration: {{DURATION}}s")

if not os.path.exists(PORT):
    print(f"ERROR: Port {{PORT}} not found - falling back to simulation")
    # Fallback to simulation
    import random
    data = []
    start = time.time()
    while time.time() - start < 30:  # Shorter duration
        humidity = random.uniform(40, 70)
        temp_c = random.uniform(20, 30)
        data.append({{'timestamp': time.time(), 'humidity': round(humidity, 1), 
                     'temp_c': round(temp_c, 1), 'simulated': True}})
        time.sleep(2)
    
    print(f"RECORDS_CAPTURED={{len(data)}}")
    json.dump(data, open(OUTPUT_FILE, 'w'), indent=2)
    exit(0)

try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=2)
    print(f"Port {{PORT}} opened successfully\\n")
    print("Starting DHT11 sensor reading...")
    data, start = [], time.time()

    while time.time() - start < DURATION:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if not line:
            continue
        print(f"{{line}}")
        m = re.search(r'Humidity:\\s*([\\d.]+).*Temperature:\\s*([\\d.]+)', line)
        if m:
            data.append({{'timestamp': time.time(), 'humidity': float(m[1]), 'temp_c': float(m[2])}})

    ser.close()
    print(f"RECORDS_CAPTURED={{len(data)}}")
    json.dump(data, open(OUTPUT_FILE, 'w'), indent=2)
    print(f"Data saved to {{OUTPUT_FILE}} ({{len(data)}} records)")

except Exception as e:
    json.dump({{'error': str(e), 'timestamp': time.time()}}, open(OUTPUT_FILE, 'w'), indent=2)
    print(f"ERROR: {{e}}")
    exit(1)

print("Capture completed successfully")
EOF
fi

DEST="/home/{RASPI_USER}/sensor_output_{EXECUTION_ID}.json"
cp output.json "$DEST" 2>/dev/null || echo '{{"error":"output.json not created"}}' > "$DEST"

echo "=========================================="
echo "Log saved to: $LOG_FILE"
echo "Results saved to: $DEST"

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print $${{END_TS}}-$${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=$${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0

cat <<EOF_METRICS > $${{METRICS_TMP}}
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{START_TS}}
EOF_METRICS

mkdir -p $(dirname $${{METRICS_HISTORY}})
cp $${{METRICS_TMP}} $${{METRICS_HISTORY}}
echo "Metrics history saved: $${{METRICS_HISTORY}}"

mkdir -p $(dirname $${{METRICS_BACKUP}})
cp $${{METRICS_TMP}} $${{METRICS_BACKUP}}
echo "Metrics backup saved: $${{METRICS_BACKUP}}"

if [ -d "$${{METRICS_DIR}}" ]; then
    cp $${{METRICS_TMP}} $${{METRICS_CURRENT}} 2>/dev/null && echo "Metrics published to Prometheus: $${{METRICS_CURRENT}}" || echo "Warning: Could not publish to Prometheus"
fi

echo "{EXECUTION_ID}" > /home/{RASPI_USER}/.dagon_metrics/current_execution_id

echo "=========================================="
echo "Task A completed successfully"
"""

# ========== TASK B: Data Preprocessing (FOG) ==========
taskB_command = f"""
set -e
TASK="B"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"
EXECUTION_ID="{EXECUTION_ID}"

DATA_DIR="/tmp/fog_data_{EXECUTION_ID}"
INPUT_FILE="$${{DATA_DIR}}/sensor_output_{EXECUTION_ID}.json"
OUTPUT_FILE="$${{DATA_DIR}}/sensor_output_{EXECUTION_ID}_preprocessed.json"
LOG_FILE="$${{DATA_DIR}}/taskB.log"
METRICS_FILE="$${{DATA_DIR}}/taskB_metrics.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

echo "==========================================" | tee "$LOG_FILE"
echo "Task B: Preprocessing (FOG - Nomad)" | tee -a "$LOG_FILE"
echo "Execution ID: {EXECUTION_ID}" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

if [ ! -f "$${{INPUT_FILE}}" ]; then
    echo "ERROR: Input not found: $${{INPUT_FILE}}" | tee -a "$LOG_FILE"
    exit 1
fi

pip3 install --quiet --no-cache-dir pandas 2>&1 | grep -v "already satisfied" >> "$LOG_FILE" || true

# Add sleep to ensure timing consistency
sleep 2

python3 << 'PYEOF' 2>&1 | tee -a "$LOG_FILE"
import json, os
import pandas as pd

EXECUTION_ID = "{EXECUTION_ID}"
DATA_DIR = f"/tmp/fog_data_{{EXECUTION_ID}}"
INPUT_FILE = f"{{DATA_DIR}}/sensor_output_{{EXECUTION_ID}}.json"
OUTPUT_FILE = f"{{DATA_DIR}}/sensor_output_{{EXECUTION_ID}}_preprocessed.json"

print(f"Processing: {{INPUT_FILE}}")

with open(INPUT_FILE) as f:
    data = json.load(f)

if isinstance(data, dict) and 'error' in data:
    print(f"ERROR: {{data['error']}}")
    exit(1)

df = pd.DataFrame(data)

if df.empty or 'humidity' not in df or 'temp_c' not in df:
    print("ERROR: Invalid data")
    exit(1)

summary = {{
    "count": int(len(df)),
    "mean_humidity": float(df["humidity"].mean()),
    "mean_temp_c": float(df["temp_c"].mean()),
    "min_humidity": float(df["humidity"].min()),
    "max_humidity": float(df["humidity"].max()),
    "min_temp_c": float(df["temp_c"].min()),
    "max_temp_c": float(df["temp_c"].max()),
    "start_time": float(df["timestamp"].min()),
    "end_time": float(df["timestamp"].max())
}}

print(f"RECORDS_CAPTURED={{summary['count']}}")
print(f"  Mean Humidity: {{summary['mean_humidity']:.2f}}%")
print(f"  Mean Temp: {{summary['mean_temp_c']:.2f}}°C")

with open(OUTPUT_FILE, 'w') as out:
    json.dump({{"execution_id": EXECUTION_ID, "summary": summary, "raw": data}}, out, indent=2)

print(f"✓ Output saved: {{OUTPUT_FILE}}")
PYEOF

PYTHON_EXIT=$?

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print $${{END_TS}}-$${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=$${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0

cat > $${{METRICS_FILE}} << EOF_METRICS
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{START_TS}}
EOF_METRICS

echo "✓ Task B metrics saved: $${{METRICS_FILE}}" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

exit $PYTHON_EXIT
"""

# ========== TASK C: MongoDB Storage (FOG) ==========
taskC_command = f"""
set -e
TASK="C"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"
EXECUTION_ID="{EXECUTION_ID}"

DATA_DIR="/tmp/fog_data_{EXECUTION_ID}"
INPUT_FILE="$${{DATA_DIR}}/sensor_output_{EXECUTION_ID}_preprocessed.json"
LOG_FILE="$${{DATA_DIR}}/taskC.log"
METRICS_FILE="$${{DATA_DIR}}/taskC_metrics.prom"

MONGO_URI="{MONGO_URI}"
MONGO_DB="{MONGO_DB}"
MONGO_COLLECTION="{MONGO_COLLECTION}"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

echo "==========================================" | tee "$LOG_FILE"
echo "Task C: MongoDB Storage (FOG - Nomad)" | tee -a "$LOG_FILE"
echo "Execution ID: {EXECUTION_ID}" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

if [ ! -f "$${{INPUT_FILE}}" ]; then
    echo "ERROR: Preprocessed file not found: $${{INPUT_FILE}}" | tee -a "$LOG_FILE"
    exit 1
fi

pip3 install --quiet --no-cache-dir pymongo 2>&1 | grep -v "already satisfied" >> "$LOG_FILE" || true

python3 << 'PYEOF' 2>&1 | tee -a "$LOG_FILE"
import json, re, os
from pymongo import MongoClient
from datetime import datetime, timezone

EXECUTION_ID = "{EXECUTION_ID}"
DATA_DIR = f"/tmp/fog_data_{{EXECUTION_ID}}"
INPUT_FILE = f"{{DATA_DIR}}/sensor_output_{{EXECUTION_ID}}_preprocessed.json"

MONGO_URI = "{MONGO_URI}"
MONGO_DB = "{MONGO_DB}"
MONGO_COLLECTION = "{MONGO_COLLECTION}"

print(f"Reading: {{INPUT_FILE}}")

with open(INPUT_FILE) as f:
    data = json.load(f)

print(f"Connecting to MongoDB: {{MONGO_DB}}.{{MONGO_COLLECTION}}")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]

try:
    client.server_info()
    print("✓ Connected to MongoDB")
    
    # Check if document already exists
    if collection.find_one({{"execution_id": EXECUTION_ID}}):
        print("⚠ Document already exists")
        exit(0)
    
    # Parse metrics from BOTH tasks (A and B) - UNIFIED FORMAT
    def parse_prometheus_metrics(metric_file):
        metrics = {{}}
        try:
            with open(metric_file) as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    match = re.search(r'(\\w+)\\{{.*task="(\\w+)".*\\}}\\s+([\\d.]+)', line)
                    if match:
                        metric_name, task, value = match.groups()
                        key = metric_name.replace('dagon_', '').replace('_seconds', '')
                        metrics[f'task_{{task}}_{{key}}'] = float(value)
        except Exception as e:
            print(f"Warning: Could not read {{metric_file}}: {{e}}")
        return metrics
    
    # Collect metrics from Task B (local)
    metrics = parse_prometheus_metrics(f'{{DATA_DIR}}/taskB_metrics.prom')
    
    # Fetch Task A metrics from Edge via SCP
    import subprocess
    edge_metrics = "/home/{RASPI_USER}/.dagon_metrics/history/dagon_dht_A_{EXECUTION_ID}.prom"
    local_metrics = f"{{DATA_DIR}}/taskA_metrics.prom"
    
    scp_cmd = ['scp', '-P', '{RASPI_PORT}',
               f'{RASPI_USER}@{RASPI_IP}:{{edge_metrics}}',
               local_metrics]
    
    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✓ Fetched Task A metrics from Edge")
            metrics.update(parse_prometheus_metrics(local_metrics))
        else:
            print(f"⚠ Could not fetch Task A metrics: {{result.stderr}}")
    except Exception as e:
        print(f"⚠ Could not fetch Task A metrics: {{e}}")
    
    # Calculate total duration (sum of all tasks)
    total_duration = sum([v for k, v in metrics.items() if 'task_duration' in k])
    
    # UNIFIED DOCUMENT STRUCTURE (matches Docker format exactly)
    document = {{
        "execution_id": EXECUTION_ID,
        "workflow": "DHT-Sensor-Capture-And-Preprocess",
        "export_timestamp": datetime.now(timezone.utc),
        "raspberry_pi": "{RASPI_IP}",
        "summary": data.get("summary", {{}}),
        "metrics": metrics,
        "total_duration_seconds": total_duration,
        "raw_data_count": len(data.get("raw", [])),
        "source_file": INPUT_FILE,
        "all_tasks_successful": (
            metrics.get('task_A_task_success', 0) == 1 and 
            metrics.get('task_B_task_success', 0) == 1
        )
    }}
    
    result = collection.insert_one(document)
    print(f"✓ Document inserted: {{result.inserted_id}}")
    print(f"  Records: {{data['summary']['count']}}")
    print(f"  Mean temp: {{data['summary']['mean_temp_c']:.2f}}°C")
    print(f"  Mean humidity: {{data['summary']['mean_humidity']:.2f}}%")
    print(f"  Total duration: {{total_duration:.2f}}s")
    print(f"\\n✓ Total docs: {{collection.count_documents({{}})}}")
    print(f"RECORDS_CAPTURED={{document.get('raw_data_count', 0)}}")
    
    client.close()
    print("✓ MongoDB connection closed")

except Exception as e:
    print(f"ERROR: {{e}}")
    import traceback
    traceback.print_exc()
    exit(1)

PYEOF

PYTHON_EXIT=$?

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print $${{END_TS}}-$${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=$${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0

cat > $${{METRICS_FILE}} << EOF_METRICS
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="$${{WORKFLOW}}",task="$${{TASK}}",execution_id="$${{EXECUTION_ID}}"}} $${{START_TS}}
EOF_METRICS

echo "✓ Task C metrics saved: $${{METRICS_FILE}}" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

exit $PYTHON_EXIT
"""

# ========== WORKFLOW EVENT FUNCTIONS ==========
def write_workflow_event(metric_name, workflow_name, execution_id):
    """
    Writes a point-in-time metric for Prometheus on the Raspberry Pi via SSH
    """
    metrics_dir = "/var/lib/node_exporter/textfile_collector"
    tmp_file = f"/tmp/{metric_name}.prom"
    final_file = f"{metrics_dir}/{metric_name}.prom"
    
    timestamp = int(time.time() * 1000)
    
    metric = f"""# HELP {metric_name} Dagon workflow event
# TYPE {metric_name} gauge
{metric_name}{{workflow="{workflow_name}",execution_id="{execution_id}"}} {timestamp}
"""
    
    try:
        ssh_cmd = [
            'ssh',
            '-p', str(RASPI_PORT),
            f'{RASPI_USER}@{RASPI_IP}',
            f"cat > {tmp_file} << 'EOF'\n{metric}EOF\nmv {tmp_file} {final_file} && chmod 644 {final_file}"
        ]
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(f"Workflow event published: {metric_name}")
        else:
            print(f"Warning: Could not write workflow event {metric_name}")
            
    except subprocess.TimeoutExpired:
        print(f"Timeout writing workflow event {metric_name}")
    except Exception as e:
        print(f"Could not write workflow event {metric_name}: {e}")


def execute_with_transfer():
    """
    Execute workflow with manual file transfer between Edge and Fog
    """
    
    # Phase 1: Task A on Edge
    print("="*70)
    print("PHASE 1: Task A (Edge - Raspberry Pi)")
    print("="*70)
    
    taskA = DagonTask(
        TaskType.NOMAD,
        "A",
        taskA_command,
        image="python:3.9-slim",
        nomad_address=EDGE_NOMAD_ADDRESS,
        ip=RASPI_IP,
        ssh_username=RASPI_USER,
        ssh_port=RASPI_PORT,
        volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}",
        cpu=200,
        memory=512
    )
    
    workflow_a = Workflow("Task-A-Nomad")
    workflow_a.add_task(taskA)
    
    try:
        workflow_a.run()
        print("✓ Task A workflow completed\n")
        
        # Check if task actually succeeded by looking at the status
        if hasattr(taskA, 'result') and taskA.result:
            if taskA.result.get('code', 1) != 0:
                print(f"⚠ Task A exit code: {taskA.result.get('code')}")
                print(f"Task A output:\n{taskA.result.get('output', 'No output')}\n")
                
                # Try to get detailed Nomad logs
                print("Attempting to retrieve Nomad job logs...")
                try:
                    import requests
                    
                    # Get job details
                    job_url = f"{EDGE_NOMAD_ADDRESS}/v1/job/{taskA.job_id}"
                    job_resp = requests.get(job_url, timeout=10)
                    if job_resp.status_code == 200:
                        job_info = job_resp.json()
                        print(f"\nJob Status: {job_info.get('Status', 'unknown')}")
                    
                    # Get allocations
                    allocs_url = f"{EDGE_NOMAD_ADDRESS}/v1/job/{taskA.job_id}/allocations"
                    allocs_resp = requests.get(allocs_url, timeout=10)
                    
                    if allocs_resp.status_code == 200:
                        allocations = allocs_resp.json()
                        if allocations:
                            alloc = allocations[0]
                            alloc_id = alloc.get('ID')
                            print(f"Allocation ID: {alloc_id}")
                            
                            task_states = alloc.get('TaskStates', {})
                            if 'dagon-task' in task_states:
                                task_state = task_states['dagon-task']
                                print(f"Task State: {task_state.get('State')}")
                                
                                # Get events
                                events = task_state.get('Events', [])
                                if events:
                                    print("\nTask Events:")
                                    for event in events[-5:]:  # Last 5 events
                                        print(f"  - {event.get('Type')}: {event.get('DisplayMessage', event.get('Message', 'N/A'))}")
                            
                            # Try to get logs
                            if alloc_id:
                                logs_url = f"{EDGE_NOMAD_ADDRESS}/v1/client/fs/logs/{alloc_id}"
                                
                                # Try stdout
                                stdout_resp = requests.get(logs_url, params={
                                    'task': 'dagon-task',
                                    'type': 'stdout',
                                    'plain': 'true'
                                }, timeout=10)
                                
                                if stdout_resp.status_code == 200 and stdout_resp.text.strip():
                                    print("\n" + "="*50)
                                    print("NOMAD JOB STDOUT:")
                                    print("="*50)
                                    print(stdout_resp.text[:3000])
                                    print("="*50 + "\n")
                                
                                # Try stderr
                                stderr_resp = requests.get(logs_url, params={
                                    'task': 'dagon-task',
                                    'type': 'stderr',
                                    'plain': 'true'
                                }, timeout=10)
                                
                                if stderr_resp.status_code == 200 and stderr_resp.text.strip():
                                    print("\n" + "="*50)
                                    print("NOMAD JOB STDERR:")
                                    print("="*50)
                                    print(stderr_resp.text[:3000])
                                    print("="*50 + "\n")
                    
                except Exception as e:
                    print(f"Could not retrieve Nomad logs: {e}")
                    import traceback
                    traceback.print_exc()
                
                raise Exception("Task A failed - check logs above")
        
    except Exception as e:
        if "Task A failed" not in str(e):
            print(f"✗ Task A failed: {e}")
            import traceback
            traceback.print_exc()
        raise
    
    # Phase 2: Transfer
    print("="*70)
    print("PHASE 2: File Transfer (Edge → Fog)")
    print("="*70)
    
    edge_file = f"/home/{RASPI_USER}/sensor_output_{EXECUTION_ID}.json"
    local_file = f"{FOG_DATA_DIR}/sensor_output_{EXECUTION_ID}.json"
    
    scp_cmd = ['scp', '-P', str(RASPI_PORT),
               f'{RASPI_USER}@{RASPI_IP}:{edge_file}',
               local_file]
    
    print(f"Transferring: {edge_file}")
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0 and os.path.exists(local_file):
        size = os.path.getsize(local_file)
        print(f"✓ Transfer OK ({size} bytes)\n")
    else:
        raise Exception(f"Transfer failed: {result.stderr}")
    
    # Phase 3: Tasks B & C on Fog
    print("="*70)
    print("PHASE 3: Tasks B & C (Fog - PC)")
    print("="*70)
    
    taskB_new = DagonTask(
        TaskType.NOMAD,
        "B",
        taskB_command,
        image="python:3.9-slim",
        nomad_address=FOG_NOMAD_ADDRESS,
        volume="/tmp:/tmp",
        cpu=200,
        memory=512
    )
    
    taskC_new = DagonTask(
        TaskType.NOMAD,
        "C",
        taskC_command,
        image="python:3.9-slim",
        nomad_address=FOG_NOMAD_ADDRESS,
        volume="/tmp:/tmp",
        cpu=200,
        memory=512
    )
    
    workflow_bc = Workflow("Tasks-BC-Nomad")
    workflow_bc.add_task(taskB_new)
    workflow_bc.add_task(taskC_new)
    taskC_new.add_dependency_to(taskB_new)
    workflow_bc.run()
    print("✓ Tasks B & C completed\n")


# ========== MAIN EXECUTION ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')

energy_collector = PrometheusMetricsCollector(
    prometheus_url=PROMETHEUS_URL,
    sampling_interval=SAMPLING_INTERVAL
)

print("Starting energy monitoring...\n")
energy_collector.start_collection()

# ========== WRITE WORKFLOW START EVENT ==========
write_workflow_event(
    metric_name="dagon_workflow_start",
    workflow_name="DHT-Sensor-Capture-And-Preprocess",
    execution_id=EXECUTION_ID
)

workflow_start = time.time()

try:
    execute_with_transfer()
    workflow_success = True
except Exception as e:
    workflow_success = False
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

# ========== WRITE WORKFLOW END EVENT ==========
write_workflow_event(
    metric_name="dagon_workflow_end",
    workflow_name="DHT-Sensor-Capture-And-Preprocess",
    execution_id=EXECUTION_ID
)

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

print(f"Stopping energy monitoring...")
energy_collector.stop_collection()
energy_stats = energy_collector.calculate_statistics()
energy_collector.print_summary()

energy_filename = f"energy_metrics_{EXECUTION_ID}.json"
energy_collector.export_to_json(energy_filename)

# ========== MONGODB ENERGY UPDATE ==========
print("\n" + "="*70)
print("Updating MongoDB with energy metrics...")
print("="*70)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    client.server_info()
    
    if collection.find_one({"execution_id": EXECUTION_ID}):
        # UNIFIED energy structure (matches Apptainer/Docker format)
        update_data = {
            "$set": {
                "energy_monitoring": {
                    "enabled": True,
                    "prometheus_url": PROMETHEUS_URL,
                    "sampling_interval_seconds": SAMPLING_INTERVAL,
                    "collection_duration_seconds": energy_stats.get('collection_duration_seconds', 0),
                    "samples_count": energy_stats.get('samples_count', 0),
                    
                    "raspberry_pi": {
                        "power": {
                            "mean_watts": energy_stats.get('rpi_power_watts_mean', 0),
                            "max_watts": energy_stats.get('rpi_power_watts_max', 0),
                            "min_watts": energy_stats.get('rpi_power_watts_min', 0),
                            "std_watts": energy_stats.get('rpi_power_watts_std', 0)
                        },
                        "cpu": {
                            "mean_percent": energy_stats.get('rpi_cpu_percent_mean', 0),
                            "max_percent": energy_stats.get('rpi_cpu_percent_max', 0)
                        },
                        "ram": {
                            "mean_percent": energy_stats.get('rpi_ram_percent_mean', 0),
                            "max_percent": energy_stats.get('rpi_ram_percent_max', 0)
                        },
                        "temperature": {
                            "mean_celsius": energy_stats.get('rpi_temp_celsius_mean', 0),
                            "max_celsius": energy_stats.get('rpi_temp_celsius_max', 0)
                        },
                        "energy": {
                            "total_joules": energy_stats.get('rpi_energy_joules', 0),
                            "total_wh": energy_stats.get('rpi_energy_wh', 0)
                        }
                    },
                    
                    "pc": {
                        "power": {
                            "mean_watts": energy_stats.get('pc_power_watts_mean', 0),
                            "max_watts": energy_stats.get('pc_power_watts_max', 0),
                            "min_watts": energy_stats.get('pc_power_watts_min', 0),
                            "std_watts": energy_stats.get('pc_power_watts_std', 0)
                        },
                        "cpu": {
                            "mean_percent": energy_stats.get('pc_cpu_percent_mean', 0),
                            "max_percent": energy_stats.get('pc_cpu_percent_max', 0)
                        },
                        "ram": {
                            "mean_percent": energy_stats.get('pc_ram_percent_mean', 0),
                            "max_percent": energy_stats.get('pc_ram_percent_max', 0)
                        },
                        "temperature": {
                            "mean_celsius": energy_stats.get('pc_temp_celsius_mean', 0),
                            "max_celsius": energy_stats.get('pc_temp_celsius_max', 0)
                        },
                        "energy": {
                            "total_joules": energy_stats.get('pc_energy_joules', 0),
                            "total_wh": energy_stats.get('pc_energy_wh', 0)
                        }
                    } if 'pc_power_watts_mean' in energy_stats else {},
                },
                "energy_metrics_added_at": datetime.now(timezone.utc)
            }
        }
        
        collection.update_one({"execution_id": EXECUTION_ID}, update_data)
        print(f"✓ Energy metrics updated")
        print(f"  RasPi: {energy_stats.get('rpi_energy_wh', 0):.4f} Wh")
        if 'pc_energy_wh' in energy_stats:
            print(f"  PC: {energy_stats.get('pc_energy_wh', 0):.4f} Wh")
    else:
        print("⚠ Document not found (Task C may have failed)")
    
    client.close()
except Exception as e:
    print(f"⚠ Could not update energy: {e}")
    import traceback
    traceback.print_exc()

# ========== SUMMARY ==========
print("\n" + "="*70)
print("WORKFLOW SUMMARY")
print("="*70)
print(f"Execution: {EXECUTION_ID}")
print(f"Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS ✓' if workflow_success else 'FAILED ✗'}")
print(f"Orchestrator: Nomad")
print(f"  Edge: {EDGE_NOMAD_ADDRESS}")
print(f"  Fog: {FOG_NOMAD_ADDRESS}")
print(f"\nEnergy Consumption:")
print(f"  RasPi: {energy_stats.get('rpi_energy_wh', 0):.4f} Wh")
if 'pc_energy_wh' in energy_stats:
    total = energy_stats.get('rpi_energy_wh', 0) + energy_stats.get('pc_energy_wh', 0)
    print(f"  PC: {energy_stats.get('pc_energy_wh', 0):.4f} Wh")
    print(f"  TOTAL: {total:.4f} Wh")
print(f"\nMongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print(f"Local metrics: {energy_filename}")
print(f"\nNomad UIs:")
print(f"  Edge: {EDGE_NOMAD_ADDRESS}/ui")
print(f"  Fog: {FOG_NOMAD_ADDRESS}/ui")
print("="*70 + "\n")

sys.exit(0 if workflow_success else 1)