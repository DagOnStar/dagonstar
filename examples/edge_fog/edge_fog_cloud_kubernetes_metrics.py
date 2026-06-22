#!/usr/bin/env python3
"""
Dagon DHT Workflow with Energy Metrics Capture - Kubernetes Version
Usa imagen local python-dht:latest cargada en K3s
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
print("Dagon DHT Workflow with Energy Monitoring - Kubernetes")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Raspberry Pi: {RASPI_IP}")
print(f"MongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print(f"Prometheus: {PROMETHEUS_URL}")
print(f"Sampling: every {SAMPLING_INTERVAL}s")
print(f"Container Runtime: Kubernetes (containerd)")
print("="*70 + "\n")

workflow = Workflow("DHT-Sensor-Capture-And-Preprocess")

# ========== TASK A: DHT Sensor Capture ==========
taskA_command = f"""
TASK="A"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"
EXECUTION_ID="{EXECUTION_ID}"

METRICS_TMP="/tmp/dagon_${{TASK}}.prom"
METRICS_DIR="/var/lib/node_exporter/textfile_collector"
METRICS_CURRENT="${{METRICS_DIR}}/dagon_dht_${{TASK}}_current.prom"
METRICS_HISTORY="/home/raspi/.dagon_metrics/history/dagon_dht_${{TASK}}_${{EXECUTION_ID}}.prom"
METRICS_BACKUP="/home/raspi/.dagon_metrics/dagon_dht_${{TASK}}.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

LOG_FILE="/home/raspi/dagon_capture_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting DHT sensor capture (Kubernetes)"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "=========================================="

python3 << 'EOF'
import serial, re, json, time, os

PORT = '/dev/ttyACM0'
BAUDRATE = 9600
DURATION = 300
OUTPUT_FILE = 'output.json'

print(f"Configuration:\\n  Port: {{PORT}}\\n  Duration: {{DURATION}}s")

if not os.path.exists(PORT):
    print(f"ERROR: Port {{PORT}} not found")
    json.dump({{'error': 'Port not found', 'timestamp': time.time()}}, open(OUTPUT_FILE, 'w'), indent=2)
    exit(1)

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

DEST="/home/raspi/sensor_output_${{EXECUTION_ID}}.json"
cp output.json "$DEST" 2>/dev/null || echo '{{"error":"output.json not created"}}' > "$DEST"

echo "=========================================="
echo "Log saved to: $LOG_FILE"
echo "Results saved to: $DEST"

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=${{RECORDS:-0}}

grep -q "ERROR" "$LOG_FILE" && SUCCESS=0

cat <<EOF_METRICS > ${{METRICS_TMP}}
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{RECORDS}}

# HELP dagon_execution_start_timestamp_seconds Start timestamp of execution
# TYPE dagon_execution_start_timestamp_seconds gauge
dagon_execution_start_timestamp_seconds{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{START_TS}}
EOF_METRICS

mkdir -p $(dirname ${{METRICS_HISTORY}})
cp ${{METRICS_TMP}} ${{METRICS_HISTORY}}
echo "Metrics history saved: ${{METRICS_HISTORY}}"

mkdir -p $(dirname ${{METRICS_BACKUP}})
cp ${{METRICS_TMP}} ${{METRICS_BACKUP}}
echo "Metrics backup saved: ${{METRICS_BACKUP}}"

if [ -d "${{METRICS_DIR}}" ]; then
    cp ${{METRICS_TMP}} ${{METRICS_CURRENT}} 2>/dev/null && echo "Metrics published to Prometheus: ${{METRICS_CURRENT}}" || echo "Warning: Could not publish to Prometheus"
fi

echo "${{EXECUTION_ID}}" > /home/raspi/.dagon_metrics/current_execution_id

echo "=========================================="
"""

taskA = DagonTask(
    TaskType.KUBERNETES,
    "A",
    taskA_command,
    image="python-dht:latest",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

taskA.namespace = "default"
taskA.remove = True
taskA.volumes = [
    f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    "/var/lib/node_exporter:/var/lib/node_exporter"
]
taskA.devices = ["/dev/ttyACM0:/dev/ttyACM0"]
taskA.privileged = True
taskA.image_pull_policy = "Never"  # CLAVE: Usar imagen local, no descargar

workflow.add_task(taskA)


# ========== TASK B: Data Preprocessing ==========
taskB_command = f"""
TASK="B"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"

EXECUTION_ID=$(cat /home/raspi/.dagon_metrics/current_execution_id 2>/dev/null || echo "{EXECUTION_ID}")

METRICS_TMP="/tmp/dagon_${{TASK}}.prom"
METRICS_DIR="/var/lib/node_exporter/textfile_collector"
METRICS_CURRENT="${{METRICS_DIR}}/dagon_dht_${{TASK}}_current.prom"
METRICS_HISTORY="/home/raspi/.dagon_metrics/history/dagon_dht_${{TASK}}_${{EXECUTION_ID}}.prom"
METRICS_BACKUP="/home/raspi/.dagon_metrics/dagon_dht_${{TASK}}.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

LOG_FILE="/home/raspi/dagon_preprocess_${{EXECUTION_ID}}.log"

echo "==========================================" >> "$LOG_FILE"
echo "Starting preprocessing (Kubernetes)" >> "$LOG_FILE"
echo "Execution ID: ${{EXECUTION_ID}}" >> "$LOG_FILE"
echo "Date: $(date)" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"

python3 << 'EOF' >> "$LOG_FILE" 2>&1
import json, glob, os, time
import pandas as pd

with open('/home/raspi/.dagon_metrics/current_execution_id') as f:
    execution_id = f.read().strip()

time.sleep(2)

input_file = f'/home/raspi/sensor_output_{{execution_id}}.json'
output_file = input_file.replace('.json', '_preprocessed.json')

if not os.path.exists(input_file):
    print(f"ERROR: Input file not found: {{input_file}}")
    exit(1)

print(f"Processing: {{input_file}}")

with open(input_file) as f:
    data = json.load(f)

if isinstance(data, dict) and 'error' in data:
    print(f"ERROR in input file: {{data['error']}}")
    exit(1)

df = pd.DataFrame(data)

if df.empty or 'humidity' not in df or 'temp_c' not in df:
    print("ERROR: Invalid data structure")
    exit(1)

summary = {{
    'count': int(len(df)),
    'mean_humidity': float(df['humidity'].mean()),
    'mean_temp_c': float(df['temp_c'].mean()),
    'min_humidity': float(df['humidity'].min()),
    'max_humidity': float(df['humidity'].max()),
    'min_temp_c': float(df['temp_c'].min()),
    'max_temp_c': float(df['temp_c'].max()),
    'start_time': float(df['timestamp'].min()),
    'end_time': float(df['timestamp'].max())
}}

print(f"RECORDS_CAPTURED={{summary['count']}}")
print(f"  Mean Humidity: {{summary['mean_humidity']:.2f}}%")
print(f"  Mean Temp: {{summary['mean_temp_c']:.2f}}°C")

with open(output_file, 'w') as out:
    json.dump({{'execution_id': execution_id, 'summary': summary, 'raw': data}}, out, indent=2)

print(f"✓ Output saved: {{output_file}}")
EOF

PYTHON_EXIT=$?

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=${{RECORDS:-0}}

[ $PYTHON_EXIT -eq 0 ] || SUCCESS=0

cat <<EOF_METRICS > ${{METRICS_TMP}}
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{RECORDS}}
EOF_METRICS

mkdir -p $(dirname ${{METRICS_HISTORY}})
cp ${{METRICS_TMP}} ${{METRICS_HISTORY}}

mkdir -p $(dirname ${{METRICS_BACKUP}})
cp ${{METRICS_TMP}} ${{METRICS_BACKUP}}

if [ -d "${{METRICS_DIR}}" ]; then
    cp ${{METRICS_TMP}} ${{METRICS_CURRENT}} 2>/dev/null
fi

echo "==========================================" >> "$LOG_FILE"
echo "Task B completed" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"

exit $PYTHON_EXIT
"""

taskB = DagonTask(
    TaskType.KUBERNETES,
    "B",
    taskB_command,
    image="python-dht:latest",  # Usa la misma imagen (tiene pandas incluido)
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

taskB.namespace = "default"
taskB.remove = True
taskB.volumes = [
    f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    "/var/lib/node_exporter:/var/lib/node_exporter"
]
taskB.image_pull_policy = "Never"

workflow.add_task(taskB)
taskB.add_dependency_to(taskA)


# ========== TASK C: MongoDB Upload ==========
taskC_command = f"""
TASK="C"
WORKFLOW="DHT-Sensor-Capture-And-Preprocess"

EXECUTION_ID=$(cat /home/raspi/.dagon_metrics/current_execution_id 2>/dev/null || echo "{EXECUTION_ID}")

METRICS_TMP="/tmp/dagon_${{TASK}}.prom"
METRICS_DIR="/var/lib/node_exporter/textfile_collector"
METRICS_CURRENT="${{METRICS_DIR}}/dagon_dht_${{TASK}}_current.prom"
METRICS_HISTORY="/home/raspi/.dagon_metrics/history/dagon_dht_${{TASK}}_${{EXECUTION_ID}}.prom"
METRICS_BACKUP="/home/raspi/.dagon_metrics/dagon_dht_${{TASK}}.prom"

START_TS=$(date +%s.%N)
SUCCESS=1
RECORDS=0

LOG_FILE="/home/raspi/dagon_mongodb_${{EXECUTION_ID}}.log"

echo "==========================================" > "$LOG_FILE"
echo "Starting MongoDB upload (Kubernetes)" >> "$LOG_FILE"
echo "Execution ID: ${{EXECUTION_ID}}" >> "$LOG_FILE"
echo "Date: $(date)" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"

python3 << 'PYEOF' >> "$LOG_FILE" 2>&1
import json, os, time
from datetime import datetime, timezone
from pymongo import MongoClient

with open('/home/raspi/.dagon_metrics/current_execution_id') as f:
    execution_id = f.read().strip()

time.sleep(1)

input_file = f'/home/raspi/sensor_output_{{execution_id}}_preprocessed.json'

if not os.path.exists(input_file):
    print(f"ERROR: Input file not found: {{input_file}}")
    exit(1)

print(f"Loading: {{input_file}}")

with open(input_file) as f:
    data = json.load(f)

print(f"Connecting to MongoDB...")
client = MongoClient("{MONGO_URI}", serverSelectionTimeoutMS=10000)
db = client["{MONGO_DB}"]
collection = db["{MONGO_COLLECTION}"]

try:
    client.server_info()
    print("Connected to MongoDB")
    
    doc = {{
        'execution_id': execution_id,
        'workflow': 'DHT-Sensor-Capture-And-Preprocess',
        'timestamp': datetime.now(timezone.utc),
        'architecture': 'edge-kubernetes',
        'edge_device': 'raspberry-pi',
        'container_runtime': 'kubernetes',
        'tasks': {{
            'A': {{'location': 'edge', 'runtime': 'kubernetes'}},
            'B': {{'location': 'edge', 'runtime': 'kubernetes'}},
            'C': {{'location': 'edge', 'runtime': 'kubernetes'}}
        }},
        'summary': data.get('summary', {{}})
    }}
    
    result = collection.insert_one(doc)
    print(f"✓ Document inserted: {{result.inserted_id}}")
    print(f"RECORDS_CAPTURED={{data.get('summary', {{}}).get('count', 0)}}")
    
except Exception as e:
    print(f"ERROR: {{e}}")
    exit(1)
finally:
    client.close()

PYEOF

PYTHON_EXIT=$?

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")

RECORDS=$(grep -o "RECORDS_CAPTURED=[0-9]*" "$LOG_FILE" | tail -1 | cut -d= -f2)
RECORDS=${{RECORDS:-0}}

[ $PYTHON_EXIT -eq 0 ] || SUCCESS=0

cat <<EOF_METRICS > ${{METRICS_TMP}}
# HELP dagon_task_duration_seconds Duration of a Dagon task
# TYPE dagon_task_duration_seconds gauge
dagon_task_duration_seconds{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{DURATION}}

# HELP dagon_task_success Task success (1=success, 0=failure)
# TYPE dagon_task_success gauge
dagon_task_success{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{SUCCESS}}

# HELP dagon_task_records_total Records processed by task
# TYPE dagon_task_records_total gauge
dagon_task_records_total{{workflow="${{WORKFLOW}}",task="${{TASK}}",execution_id="${{EXECUTION_ID}}"}} ${{RECORDS}}
EOF_METRICS

mkdir -p $(dirname ${{METRICS_HISTORY}})
cp ${{METRICS_TMP}} ${{METRICS_HISTORY}}

mkdir -p $(dirname ${{METRICS_BACKUP}})
cp ${{METRICS_TMP}} ${{METRICS_BACKUP}}

if [ -d "${{METRICS_DIR}}" ]; then
    cp ${{METRICS_TMP}} ${{METRICS_CURRENT}} 2>/dev/null
fi

echo "==========================================" >> "$LOG_FILE"
echo "MongoDB upload completed" >> "$LOG_FILE"
echo "Log saved to: $LOG_FILE" >> "$LOG_FILE"
echo "==========================================" >> "$LOG_FILE"

exit $PYTHON_EXIT
"""

taskC = DagonTask(
    TaskType.KUBERNETES,
    "C",
    taskC_command,
    image="python-dht:latest",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

taskC.namespace = "default"
taskC.remove = True
taskC.volumes = [
    f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    "/var/lib/node_exporter:/var/lib/node_exporter"
]
taskC.image_pull_policy = "Never"

workflow.add_task(taskC)
taskC.add_dependency_to(taskB)


# ========== WORKFLOW EVENT FUNCTIONS ==========
def write_workflow_event(metric_name, workflow_name, execution_id):
    """Writes a point-in-time metric for Prometheus on the Raspberry Pi via SSH"""
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
        
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print(f"Workflow event published: {metric_name}")
    except Exception as e:
        print(f"Could not write workflow event: {e}")


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')

# ========== ENERGY MONITORING ==========
energy_collector = PrometheusMetricsCollector(
    prometheus_url=PROMETHEUS_URL,
    sampling_interval=SAMPLING_INTERVAL
)

print("Starting energy monitoring...\n")
energy_collector.start_collection()

print(f"Executing workflow (Tasks A, B, C)...\n")

write_workflow_event(
    metric_name="dagon_workflow_start",
    workflow_name=workflow.name,
    execution_id=EXECUTION_ID
)

workflow_start = time.time()

try:
    workflow.run()
    workflow_success = True
except Exception as e:
    print(f"Error in workflow: {e}")
    import traceback
    traceback.print_exc()
    workflow_success = False

write_workflow_event(
    metric_name="dagon_workflow_end",
    workflow_name=workflow.name,
    execution_id=EXECUTION_ID
)

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

print(f"\nStopping energy monitoring...")
energy_collector.stop_collection()

energy_stats = energy_collector.calculate_statistics()
energy_collector.print_summary()

energy_filename = f"energy_metrics_{EXECUTION_ID}.json"
energy_collector.export_to_json(energy_filename)

# ========== EXPORT TO MONGODB ==========
print("\n" + "="*70)
print("Adding energy metrics to MongoDB...")
print("="*70)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    
    client.server_info()
    print("Connected to MongoDB")
    
    workflow_doc = collection.find_one({"execution_id": EXECUTION_ID})
    
    if workflow_doc:
        print(f"Found workflow document")
        
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
        
        result = collection.update_one(
            {"execution_id": EXECUTION_ID},
            update_data
        )
        
        print(f"Energy metrics added to document")
        print(f"   RasPi Energy: {energy_stats.get('rpi_energy_wh', 0):.4f} Wh")
        if 'pc_energy_wh' in energy_stats:
            print(f"   PC Energy: {energy_stats.get('pc_energy_wh', 0):.4f} Wh")
        
    else:
        print(f"Warning: Workflow document not found")
        print("    This can happen if Task C failed or did not complete")
    
    client.close()
    
except Exception as e:
    print(f"Error exporting to MongoDB: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("WORKFLOW COMPLETED")
print("="*70)
print(f"Total duration: {workflow_duration:.2f}s")
print(f"RasPi Energy: {energy_stats.get('rpi_energy_wh', 0):.4f} Wh")
if 'pc_energy_wh' in energy_stats:
    print(f"PC Energy: {energy_stats.get('pc_energy_wh', 0):.4f} Wh")
print(f"\nLocal metrics: {energy_filename}")
print(f"MongoDB: {MONGO_DB}.{MONGO_COLLECTION}")
print("="*70 + "\n")