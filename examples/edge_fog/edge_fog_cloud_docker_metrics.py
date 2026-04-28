#!/usr/bin/env python3
"""
Dagon DHT Workflow with Energy Metrics Capture
Integrates: DHT sensor + MongoDB + Prometheus energy metrics
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

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("DHT Workflow - Docker")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node (Raspberry Pi): {RASPI_IP} - Task A")
print(f"Fog Node (PC): localhost - Tasks B & C")
print(f"MongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print("="*70 + "\n")

# Pre-create directories
FOG_DATA_DIR = f"/tmp/fog_data_{EXECUTION_ID}"
DOCKER_SCRATCH_DIR = f"/tmp/docker_scratch_{EXECUTION_ID}"

print("Creating local directories...")
os.makedirs(FOG_DATA_DIR, mode=0o777, exist_ok=True)
os.makedirs(f"{DOCKER_SCRATCH_DIR}/taskB", mode=0o777, exist_ok=True)
os.makedirs(f"{DOCKER_SCRATCH_DIR}/taskC", mode=0o777, exist_ok=True)
print(f"✓ Directories created\n")

# ========== TASK A: DHT Sensor Capture (EDGE) ==========
taskA_command = f"""
TASK="A"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"
EXECUTION_ID="{EXECUTION_ID}"

METRICS_FILE="/home/{RASPI_USER}/.dagon_metrics/history/dagon_dht_A_{EXECUTION_ID}.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

LOG_FILE="/home/{RASPI_USER}/dagon_capture_{EXECUTION_ID}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Task A: DHT Sensor Capture (EDGE)"
echo "Execution ID: {EXECUTION_ID}"
echo "=========================================="

pip3 install --quiet --no-cache-dir pyserial 2>&1 | grep -v "already satisfied" || true

python3 << 'EOF'
import serial, re, json, time, os

PORT = '/dev/ttyACM0'
BAUDRATE = 9600
DURATION = 300  # Same as Apptainer: 5 minutes
OUTPUT_FILE = 'output.json'

if not os.path.exists(PORT):
    print(f"ERROR: Port {{PORT}} not found")
    json.dump({{'error': 'Port not found', 'timestamp': time.time()}}, open(OUTPUT_FILE, 'w'), indent=2)
    exit(1)

try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=2)
    print(f"Port {{PORT}} opened\\n")
    print("Starting DHT11 sensor reading...")
    
    data, start = [], time.time()
    
    while time.time() - start < DURATION:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if not line:
            continue
        print(line)
        m = re.search(r'Humidity:\\s*([\\d.]+).*Temperature:\\s*([\\d.]+)', line)
        if m:
            data.append({{'timestamp': time.time(), 'humidity': float(m[1]), 'temp_c': float(m[2])}})
    
    ser.close()
    print(f"RECORDS_CAPTURED={{len(data)}}")
    json.dump(data, open(OUTPUT_FILE, 'w'), indent=2)
    
except Exception as e:
    json.dump({{'error': str(e), 'timestamp': time.time()}}, open(OUTPUT_FILE, 'w'), indent=2)
    print(f"ERROR: {{e}}")
    exit(1)
EOF

DEST="/home/{RASPI_USER}/sensor_output_{EXECUTION_ID}.json"
cp output.json "$DEST" 2>/dev/null || echo '{{"error":"file not created"}}' > "$DEST"

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")
RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0

# UNIFIED METRICS FORMAT (matches Apptainer)
mkdir -p $(dirname ${{METRICS_FILE}})
cat > ${{METRICS_FILE}} << EOF_METRICS
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="DHT-Sensor-Capture-And-Preprocess",task="A",execution_id="{EXECUTION_ID}"}} ${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="DHT-Sensor-Capture-And-Preprocess",task="A",execution_id="{EXECUTION_ID}"}} ${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="DHT-Sensor-Capture-And-Preprocess",task="A",execution_id="{EXECUTION_ID}"}} ${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="DHT-Sensor-Capture-And-Preprocess",task="A",execution_id="{EXECUTION_ID}"}} ${{START_TS}}
EOF_METRICS

echo "{EXECUTION_ID}" > /home/{RASPI_USER}/.dagon_metrics/current_execution_id
echo "✓ Task A completed (metrics saved)"
"""

# ========== TASK B: Preprocessing (FOG - PC) ==========
taskB_command = f"""
TASK="B"
EXECUTION_ID="{EXECUTION_ID}"

DATA_DIR="/tmp/fog_data_{EXECUTION_ID}"
INPUT_FILE="${{DATA_DIR}}/sensor_output_{EXECUTION_ID}.json"
OUTPUT_FILE="${{DATA_DIR}}/sensor_output_{EXECUTION_ID}_preprocessed.json"
LOG_FILE="${{DATA_DIR}}/taskB.log"
METRICS_FILE="${{DATA_DIR}}/taskB_metrics.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

echo "==========================================" | tee "$LOG_FILE"
echo "Task B: Preprocessing (FOG/PC)" | tee -a "$LOG_FILE"
echo "Execution ID: {EXECUTION_ID}" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

if [ ! -f "${{INPUT_FILE}}" ]; then
    echo "ERROR: Input not found: ${{INPUT_FILE}}" | tee -a "$LOG_FILE"
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
print("Preprocessing completed successfully")
PYEOF

PYTHON_EXIT=$?

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")
RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0
[ $PYTHON_EXIT -ne 0 ] && SUCCESS=0

# UNIFIED METRICS FORMAT (matches Apptainer)
cat > ${{METRICS_FILE}} << EOF_METRICS
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="DHT-Sensor-Capture-And-Preprocess",task="B",execution_id="{EXECUTION_ID}"}} ${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="DHT-Sensor-Capture-And-Preprocess",task="B",execution_id="{EXECUTION_ID}"}} ${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="DHT-Sensor-Capture-And-Preprocess",task="B",execution_id="{EXECUTION_ID}"}} ${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="DHT-Sensor-Capture-And-Preprocess",task="B",execution_id="{EXECUTION_ID}"}} ${{START_TS}}
EOF_METRICS

echo "✓ Task B completed" | tee -a "$LOG_FILE"

exit $PYTHON_EXIT
"""

# ========== TASK C: MongoDB Export (FOG - PC) ==========
taskC_command = f"""
TASK="C"
EXECUTION_ID="{EXECUTION_ID}"

DATA_DIR="/tmp/fog_data_{EXECUTION_ID}"
INPUT_FILE="${{DATA_DIR}}/sensor_output_{EXECUTION_ID}_preprocessed.json"
LOG_FILE="${{DATA_DIR}}/taskC.log"

echo "==========================================" | tee "$LOG_FILE"
echo "Task C: MongoDB Export (FOG/PC)" | tee -a "$LOG_FILE"
echo "Execution ID: {EXECUTION_ID}" | tee -a "$LOG_FILE"
echo "==========================================" | tee -a "$LOG_FILE"

if [ ! -f "${{INPUT_FILE}}" ]; then
    echo "ERROR: Input not found" | tee -a "$LOG_FILE"
    exit 1
fi

pip3 install --quiet --no-cache-dir pymongo 2>&1 | grep -v "already satisfied" >> "$LOG_FILE" || true

python3 << 'PYEOF' 2>&1 | tee -a "$LOG_FILE"
import json, re, os
from pymongo import MongoClient
from datetime import datetime, timezone

DATA_DIR = "/tmp/fog_data_{EXECUTION_ID}"
INPUT_FILE = f"{{DATA_DIR}}/sensor_output_{EXECUTION_ID}_preprocessed.json"

with open(INPUT_FILE) as f:
    data = json.load(f)

try:
    client = MongoClient("{MONGO_URI}", serverSelectionTimeoutMS=10000)
    db = client["{MONGO_DB}"]
    collection = db["{MONGO_COLLECTION}"]
    client.server_info()
    print("✓ MongoDB connected")
    
    if collection.find_one({{"execution_id": "{EXECUTION_ID}"}}):
        print("⚠ Already exists")
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
    
    # UNIFIED DOCUMENT STRUCTURE (matches Apptainer)
    document = {{
        "execution_id": "{EXECUTION_ID}",
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
    print(f"✓ Inserted: {{result.inserted_id}}")
    print(f"  Records: {{data['summary']['count']}}")
    print(f"  Mean temp: {{data['summary']['mean_temp_c']:.2f}}°C")
    print(f"  Mean humidity: {{data['summary']['mean_humidity']:.2f}}%")
    print(f"  Total duration: {{total_duration:.2f}}s")
    print(f"\\n✓ Total docs: {{collection.count_documents({{}})}}")
    
except Exception as e:
    print(f"✗ ERROR: {{e}}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    client.close()
PYEOF

echo "✓ Task C completed" | tee -a "$LOG_FILE"
exit $?
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


# ========== EXECUTION FUNCTION ==========
def execute_with_transfer():
    """Execute workflow with file transfer"""
    
    # Phase 1: Task A on Edge
    print("="*70)
    print("PHASE 1: Task A (Edge - Raspberry Pi)")
    print("="*70)
    
    taskA = DagonTask(
        TaskType.DOCKER,
        "A",
        taskA_command,
        image="python:3.9-slim",
        ip=RASPI_IP,
        ssh_username=RASPI_USER,
        ssh_port=RASPI_PORT,
        working_dir=f"/home/{RASPI_USER}/docker_scratch_{EXECUTION_ID}/taskA",
        volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}",
        devices=["/dev/ttyACM0:/dev/ttyACM0"]
    )
    
    workflow_a = Workflow("Task-A")
    workflow_a.add_task(taskA)
    workflow_a.run()
    print("✓ Task A completed\n")
    
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
        TaskType.DOCKER,
        "B",
        taskB_command,
        image="python:3.9-slim",
        working_dir=f"{DOCKER_SCRATCH_DIR}/taskB",
        volume="/tmp:/tmp"
    )
    
    taskC_new = DagonTask(
        TaskType.DOCKER,
        "C",
        taskC_command,
        image="python:3.9-slim",
        working_dir=f"{DOCKER_SCRATCH_DIR}/taskC",
        volume="/tmp:/tmp"
    )
    
    workflow_bc = Workflow("Tasks-BC")
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

# ========== MONGODB ENERGY UPDATE (UNIFIED FORMAT) ==========
print("\n" + "="*70)
print("Updating MongoDB with energy metrics...")
print("="*70)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    client.server_info()
    
    if collection.find_one({"execution_id": EXECUTION_ID}):
        # UNIFIED energy structure (matches Apptainer exactly)
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
        print("⚠ Document not found")
    
    client.close()
except Exception as e:
    print(f"⚠ Could not update energy: {e}")

# ========== SUMMARY ==========
print("\n" + "="*70)
print("WORKFLOW SUMMARY")
print("="*70)
print(f"Execution: {EXECUTION_ID}")
print(f"Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS ✓' if workflow_success else 'FAILED ✗'}")
print(f"Energy: {energy_stats.get('rpi_energy_wh', 0):.4f} Wh (RasPi)")
if 'pc_energy_wh' in energy_stats:
    total = energy_stats.get('rpi_energy_wh', 0) + energy_stats.get('pc_energy_wh', 0)
    print(f"        {energy_stats.get('pc_energy_wh', 0):.4f} Wh (PC)")
    print(f"        {total:.4f} Wh (TOTAL)")
print(f"\nMongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print("="*70 + "\n")