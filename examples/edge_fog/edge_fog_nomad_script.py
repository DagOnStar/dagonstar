#!/usr/bin/env python3
"""
Edge-Fog Distributed Processing Workflow with Dagon using Nomad
Splits processing between Edge (Raspberry Pi) and Fog (PC) nodes
Task A: Generate 10 random files on Edge node (1KB, 1MB, 10MB) via Nomad
Task B: Compress files on Fog node (PC) via Nomad
"""

import json, configparser, logging, time, sys, subprocess, os
from dagon import Workflow
from dagon.task import DagonTask, TaskType

# Read SSH configuration
config = configparser.ConfigParser()
config.read('dagon.ini')

RASPI_IP = config.get('ssh', 'raspi_ip')
RASPI_USER = config.get('ssh', 'raspi_user')

try:
    RASPI_PORT = config.getint('ssh', 'raspi_port')
except (configparser.NoOptionError, ValueError):
    RASPI_PORT = 22

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
print("Edge-Fog Distributed Nomad Workflow - Performance Test")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node: {RASPI_IP} (Nomad: {EDGE_NOMAD_ADDRESS})")
print(f"Fog Node: localhost (Nomad: {FOG_NOMAD_ADDRESS})")
print(f"Total files: 10 (mixed sizes: 1KB, 1MB, 10MB)")
print("="*70 + "\n")

# ========== TASK A: File Generation on Edge (Writing Phase) ==========
taskA_command = f"""
set -e
TASK=A
EXECUTION_ID={EXECUTION_ID}
NUM_FILES=10
OUTPUT_DIR=/home/{RASPI_USER}/edge_files_{EXECUTION_ID}
LOG_FILE=/home/{RASPI_USER}/edge_fog_taskA_{EXECUTION_ID}.log

exec > >(tee -a $LOG_FILE) 2>&1

echo ==========================================
echo Starting Task A: File Generation on Edge
echo Execution ID: {EXECUTION_ID}
echo Date: $(date)
echo Node: Edge Raspberry Pi Nomad
echo ==========================================

mkdir -p $OUTPUT_DIR
echo Output directory: $OUTPUT_DIR

START=$(date +%s)
FILES_GENERATED=0

# Generate files with different sizes
for i in 1 2 3 4; do
    dd if=/dev/urandom of=$OUTPUT_DIR/file_$i\_1KB.dat bs=1024 count=1 2>/dev/null && FILES_GENERATED=$((FILES_GENERATED + 1))
done

for i in 1 2 3; do
    dd if=/dev/urandom of=$OUTPUT_DIR/file_$i\_1MB.dat bs=1048576 count=1 2>/dev/null && FILES_GENERATED=$((FILES_GENERATED + 1))
done

for i in 1 2 3; do
    dd if=/dev/urandom of=$OUTPUT_DIR/file_$i\_10MB.dat bs=10485760 count=1 2>/dev/null && FILES_GENERATED=$((FILES_GENERATED + 1))
done

END=$(date +%s)
DURATION=$((END - START))

echo ==========================================
echo Task A completed in $DURATION seconds
echo Files generated: $FILES_GENERATED/10
echo ==========================================

# Save metrics
cat > /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json << 'JSONEOF'
{{
  "task": "A",
  "workflow": "Edge-Fog-Nomad-File-Processing",
  "execution_id": "{EXECUTION_ID}",
  "duration_seconds": DURATION_PLACEHOLDER,
  "success": 1,
  "files_generated": FILES_PLACEHOLDER,
  "edge_directory": "OUTPUT_PLACEHOLDER",
  "node": "edge-nomad"
}}
JSONEOF

sed -i "s/DURATION_PLACEHOLDER/$DURATION/" /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json
sed -i "s/FILES_PLACEHOLDER/$FILES_GENERATED/" /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json
sed -i "s|OUTPUT_PLACEHOLDER|$OUTPUT_DIR|" /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json
"""

# Create Task A (Edge - Remote Nomad)
taskA = DagonTask(
    TaskType.NOMAD,
    "A",
    taskA_command,
    image="ubuntu:22.04",
    nomad_address=EDGE_NOMAD_ADDRESS,
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT,
    volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    cpu=200,
    memory=512
)

# ========== TASK B: File Compression on Fog (Reading Phase) ==========
taskB_command = f"""
set -e
TASK=B
EXECUTION_ID={EXECUTION_ID}
INPUT_DIR=/tmp/fog_input_{EXECUTION_ID}
OUTPUT_DIR=/tmp/fog_compressed_{EXECUTION_ID}
LOG_FILE=/tmp/edge_fog_taskB_{EXECUTION_ID}.log

exec > >(tee -a $LOG_FILE) 2>&1

echo ==========================================
echo Starting Task B: File Compression on Fog
echo Execution ID: {EXECUTION_ID}
echo Date: $(date)
echo Node: Fog PC Nomad
echo ==========================================

if [ ! -d $INPUT_DIR ]; then
    echo ERROR: Input directory not found: $INPUT_DIR
    exit 1
fi

mkdir -p $OUTPUT_DIR
echo Output directory: $OUTPUT_DIR

START=$(date +%s)
FILES_COMPRESSED=0

# Compress all files
for input_file in $INPUT_DIR/*.dat; do
    if [ -f "$input_file" ]; then
        base_name=$(basename "$input_file" .dat)
        output_file=$OUTPUT_DIR/$base_name.gz
        
        echo Compressing: $base_name
        
        if gzip -c "$input_file" > "$output_file"; then
            FILES_COMPRESSED=$((FILES_COMPRESSED + 1))
            original_size=$(stat -c%s "$input_file" 2>/dev/null || echo 0)
            compressed_size=$(stat -c%s "$output_file" 2>/dev/null || echo 0)
            echo Compressed successfully - Original: $original_size bytes, Compressed: $compressed_size bytes
        else
            echo ERROR compressing file
        fi
    fi
done

END=$(date +%s)
DURATION=$((END - START))

echo ==========================================
echo Task B completed in $DURATION seconds
echo Files compressed: $FILES_COMPRESSED/10
echo ==========================================

cat > /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json << 'JSONEOF'
{{
  "task": "B",
  "workflow": "Edge-Fog-Nomad-File-Processing",
  "execution_id": "{EXECUTION_ID}",
  "duration_seconds": DUR_PH,
  "success": 1,
  "files_compressed": FC_PH,
  "input_directory": "INPUT_PLACEHOLDER",
  "output_directory": "OUTPUT_PLACEHOLDER",
  "node": "fog-nomad"
}}
JSONEOF

sed -i "s/DUR_PH/$DURATION/" /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json
sed -i "s/FC_PH/$FILES_COMPRESSED/" /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json
sed -i "s|INPUT_PLACEHOLDER|$INPUT_DIR|" /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json
sed -i "s|OUTPUT_PLACEHOLDER|$OUTPUT_DIR|" /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json
"""

# Create Task B (Fog - Local Nomad)
taskB = DagonTask(
    TaskType.NOMAD,
    "B",
    taskB_command,
    image="ubuntu:22.04",
    nomad_address=FOG_NOMAD_ADDRESS,
    volume="/tmp:/tmp",
    cpu=200,
    memory=512
    # No ip, ssh_username - runs on local Nomad
)

# ========== WORKFLOW EXECUTION ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')

print("Starting workflow execution...\n")
workflow_start = time.time()

# Execute Task A (Edge) in its own workflow
print("="*70)
print("PHASE 1: File Generation on Edge Node")
print("="*70)
try:
    workflow_a = Workflow("Edge-File-Generation-Nomad")
    workflow_a.add_task(taskA)
    workflow_a.run()
    print("\n✓ Task A completed successfully\n")
    taskA_success = True
except Exception as e:
    print(f"\n✗ Error in Task A: {e}\n")
    import traceback
    traceback.print_exc()
    taskA_success = False
    sys.exit(1)

# Transfer files from Edge to Fog
print("="*70)
print("PHASE 2: Transferring files from Edge to Fog")
print("="*70)

fog_input_dir = f"/tmp/fog_input_{EXECUTION_ID}"
edge_files_dir = f"/home/{RASPI_USER}/edge_files_{EXECUTION_ID}"

# Create local directory
os.makedirs(fog_input_dir, exist_ok=True)
print(f"Created local directory: {fog_input_dir}")

# Transfer files from Raspberry Pi to localhost
try:
    transfer_start = time.time()
    
    scp_cmd = [
        'scp', '-r',
        '-P', str(RASPI_PORT),
        f'{RASPI_USER}@{RASPI_IP}:{edge_files_dir}/*',
        fog_input_dir + '/'
    ]
    
    print(f"Executing: scp -r -P {RASPI_PORT} {RASPI_USER}@{RASPI_IP}:{edge_files_dir}/* {fog_input_dir}/")
    result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0:
        transferred_files = os.listdir(fog_input_dir)
        print(f"✓ Successfully transferred {len(transferred_files)} files")
        print(f"  Files: {', '.join(sorted(transferred_files)[:5])}{' ...' if len(transferred_files) > 5 else ''}")
    else:
        print(f"✗ Transfer failed: {result.stderr}")
        sys.exit(1)
    
    transfer_end = time.time()
    transfer_duration = transfer_end - transfer_start
    print(f"Transfer completed in {transfer_duration:.2f}s\n")
    
except subprocess.TimeoutExpired:
    print("✗ Transfer timeout (120s)")
    sys.exit(1)
except Exception as e:
    print(f"✗ Transfer error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Execute Task B (Fog) in its own workflow
print("="*70)
print("PHASE 3: File Compression on Fog Node")
print("="*70)
try:
    workflow_b = Workflow("Fog-File-Compression-Nomad")
    workflow_b.add_task(taskB)
    workflow_b.run()
    workflow_success = True
    print("\n✓ Task B completed successfully")
    print("\nWorkflow completed successfully")
except Exception as e:
    workflow_success = False
    print(f"\n✗ Error in Task B: {e}")
    import traceback
    traceback.print_exc()

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

# ========== PERFORMANCE SUMMARY ==========
print("\n" + "="*70)
print("PERFORMANCE SUMMARY - EDGE-FOG DISTRIBUTED NOMAD PROCESSING")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Total Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS' if workflow_success else 'FAILED'}")
print("")
print("Architecture:")
print(f"  Edge Node (Raspberry Pi): Nomad @ {EDGE_NOMAD_ADDRESS}")
print(f"  Fog Node (PC): Nomad @ {FOG_NOMAD_ADDRESS}")
print("")
print("File Distribution:")
print("  1KB files: 4")
print("  1MB files: 3")
print("  10MB files: 3")
print("")
print("Processing Distribution:")
print(f"  Task A (File Generation): Edge Node ({RASPI_IP})")
print(f"  Transfer (SCP): Edge → Fog")
print(f"  Task B (Compression): Fog Node (localhost)")
print("")
print("Files Location:")
print(f"  Edge Generated: /home/{RASPI_USER}/edge_files_{EXECUTION_ID}/")
print(f"  Fog Input: /tmp/fog_input_{EXECUTION_ID}/")
print(f"  Fog Compressed: /tmp/fog_compressed_{EXECUTION_ID}/")
print("")
print("Metrics Files:")
print(f"  Task A (Edge): /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json")
print(f"  Task B (Fog): /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json")
print("")
print("Nomad Jobs:")
print(f"  Edge UI: {EDGE_NOMAD_ADDRESS}/ui")
print(f"  Fog UI: {FOG_NOMAD_ADDRESS}/ui")
print("")
print("Verification Commands:")
print(f"  View compressed files: ls -lh /tmp/fog_compressed_{EXECUTION_ID}/")
print(f"  View Task B metrics: cat /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json")
print(f"  View Task A metrics: ssh {RASPI_USER}@{RASPI_IP} 'cat /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json'")
print("="*70 + "\n")

# Allow time for cleanup
time.sleep(2)
sys.exit(0 if workflow_success else 1)