#!/usr/bin/env python3
"""
Edge-Only Processing Workflow with Dagon using Nomad
Performs file generation and compression entirely on the Edge node (Raspberry Pi)
via HashiCorp Nomad orchestration
Task A: Generate 10 random files with different sizes (1KB, 1MB, 10MB)
Task B: Read and compress the generated files on the SAME Raspberry Pi via Nomad
"""

import json, configparser, logging, time, sys
from dagon import Workflow
from dagon.task import DagonTask, TaskType

# Read SSH configuration
config = configparser.ConfigParser()
config.read('dagon.ini')

# Configuration from dagon.ini
RASPI_IP = config.get('ssh', 'raspi_ip')
RASPI_USER = config.get('ssh', 'raspi_user')

# Use raspi_port if available, otherwise default to 22
try:
    RASPI_PORT = config.getint('ssh', 'raspi_port')
except (configparser.NoOptionError, ValueError):
    RASPI_PORT = 22

# Nomad configuration (assumes Nomad is running on the same Raspberry Pi)
try:
    NOMAD_ADDRESS = config.get('nomad', 'address')
except (configparser.NoOptionError, configparser.NoSectionError):
    NOMAD_ADDRESS = f"http://{RASPI_IP}:4646"

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("EDGE-ONLY Nomad Workflow - Performance Test")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node: {RASPI_IP}")
print(f"Nomad Address: {NOMAD_ADDRESS}")
print(f"Total files: 10 (mixed sizes: 1KB, 1MB, 10MB)")
print(f"Architecture: ALL processing via Nomad (Edge node)")
print("="*70 + "\n")

# Create workflow
workflow = Workflow("Edge-Only-Nomad-File-Processing")

# ========== TASK A: File Generation (Writing Phase) ==========
taskA_command = f"""
set -e
TASK=A
EXECUTION_ID={EXECUTION_ID}
NUM_FILES=10
OUTPUT_DIR=/home/{RASPI_USER}/edge_only_files_{EXECUTION_ID}
LOG_FILE=/home/{RASPI_USER}/edge_only_taskA_{EXECUTION_ID}.log

exec > >(tee -a $LOG_FILE) 2>&1

echo ==========================================
echo Starting Task A: File Generation
echo Execution ID: {EXECUTION_ID}
echo Date: $(date)
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
cat > /home/{RASPI_USER}/edge_only_taskA_metrics_{EXECUTION_ID}.json << 'JSONEOF'
{{
  "task": "A",
  "workflow": "Edge-Only-Nomad",
  "execution_id": "{EXECUTION_ID}",
  "duration_seconds": DURATION_PLACEHOLDER,
  "success": 1,
  "files_generated": FILES_PLACEHOLDER,
  "output_directory": "OUTPUT_PLACEHOLDER",
  "node": "edge-nomad"
}}
JSONEOF

sed -i "s/DURATION_PLACEHOLDER/$DURATION/" /home/{RASPI_USER}/edge_only_taskA_metrics_{EXECUTION_ID}.json
sed -i "s/FILES_PLACEHOLDER/$FILES_GENERATED/" /home/{RASPI_USER}/edge_only_taskA_metrics_{EXECUTION_ID}.json
sed -i "s|OUTPUT_PLACEHOLDER|$OUTPUT_DIR|" /home/{RASPI_USER}/edge_only_taskA_metrics_{EXECUTION_ID}.json
"""

taskA = DagonTask(
    TaskType.NOMAD,
    "A",
    taskA_command,
    image="ubuntu:22.04",
    nomad_address=NOMAD_ADDRESS,
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT,
    volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    cpu=200,  # 200 MHz
    memory=512  # 512 MB
)

workflow.add_task(taskA)


# ========== TASK B: File Compression (Reading Phase) ==========
taskB_command = f"""
set -e
TASK=B
EXECUTION_ID={EXECUTION_ID}
INPUT_DIR=/home/{RASPI_USER}/edge_only_files_{EXECUTION_ID}
OUTPUT_DIR=/home/{RASPI_USER}/edge_only_compressed_{EXECUTION_ID}
LOG_FILE=/home/{RASPI_USER}/edge_only_taskB_{EXECUTION_ID}.log

exec > >(tee -a $LOG_FILE) 2>&1

echo ==========================================
echo Starting Task B: File Compression
echo Execution ID: {EXECUTION_ID}
echo Date: $(date)
echo ==========================================

if [ ! -d $INPUT_DIR ]; then
    echo ERROR: Input directory not found
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
            echo Compressed successfully
        else
            echo ERROR compressing file
        fi
    fi
done

END=$(date +%s)
DURATION=$((END - START))

echo ==========================================
echo Task B completed in $DURATION seconds
echo Files compressed: $FILES_COMPRESSED
echo ==========================================

cat > /home/{RASPI_USER}/edge_only_taskB_metrics_{EXECUTION_ID}.json << 'JSONEOF'
{{
  "task": "B",
  "workflow": "Edge-Only-Nomad",
  "execution_id": "{EXECUTION_ID}",
  "duration_seconds": DUR_PH,
  "success": 1,
  "files_compressed": FC_PH,
  "node": "edge-nomad"
}}
JSONEOF

sed -i "s/DUR_PH/$DURATION/" /home/{RASPI_USER}/edge_only_taskB_metrics_{EXECUTION_ID}.json
sed -i "s/FC_PH/$FILES_COMPRESSED/" /home/{RASPI_USER}/edge_only_taskB_metrics_{EXECUTION_ID}.json
"""

taskB = DagonTask(
    TaskType.NOMAD,
    "B",
    taskB_command,
    image="ubuntu:22.04",
    nomad_address=NOMAD_ADDRESS,
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT,
    volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}",
    cpu=200,  # 200 MHz
    memory=512  # 512 MB
)

workflow.add_task(taskB)
taskB.add_dependency_to(taskA)


# ========== WORKFLOW EXECUTION ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')

print("Starting workflow execution...\n")
workflow_start = time.time()

try:
    workflow.run()
    workflow_success = True
    print("\nWorkflow completed successfully")
except Exception as e:
    workflow_success = False
    print(f"\nError in workflow: {e}")
    import traceback
    traceback.print_exc()

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

# ========== PERFORMANCE SUMMARY ==========
print("\n" + "="*70)
print("PERFORMANCE SUMMARY - EDGE NOMAD PROCESSING")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Total Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS' if workflow_success else 'FAILED'}")
print("")
print("Architecture: ALL tasks via Nomad (Edge)")
print("")
print("File Distribution:")
print("  1KB files: 4")
print("  1MB files: 3")
print("  10MB files: 3")
print("")
print("Files Location (all on Raspberry Pi):")
print(f"  Generated: /home/{RASPI_USER}/edge_only_files_{EXECUTION_ID}/")
print(f"  Compressed: /home/{RASPI_USER}/edge_only_compressed_{EXECUTION_ID}/")
print("")
print("Metrics Files (on Raspberry Pi):")
print(f"  Task A: /home/{RASPI_USER}/edge_only_taskA_metrics_{EXECUTION_ID}.json")
print(f"  Task B: /home/{RASPI_USER}/edge_only_taskB_metrics_{EXECUTION_ID}.json")
print("")
print("Nomad Job IDs:")
print(f"  Task A: Check Nomad UI at {NOMAD_ADDRESS}/ui")
print(f"  Task B: Check Nomad UI at {NOMAD_ADDRESS}/ui")
print("="*70 + "\n")

# Allow time for cleanup
time.sleep(2)
sys.exit(0 if workflow_success else 1)