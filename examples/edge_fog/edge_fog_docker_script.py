#!/usr/bin/env python3
"""
Edge-Fog Distributed Processing Workflow with Dagon using Docker
Splits processing between Edge (Raspberry Pi) and Fog (PC) nodes
Task A: Generate 10 random files on Edge node (1KB, 1MB, 10MB)
Task B: Compress files on Fog node (PC) using Docker
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

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("Edge-Fog Distributed Docker Workflow - Performance Test")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node: {RASPI_IP}")
print(f"Fog Node: localhost (this machine)")
print(f"Total files: 10 (mixed sizes: 1KB, 1MB, 10MB)")
print("="*70 + "\n")

# ========== TASK A: File Generation on Edge (Writing Phase) ==========
taskA_command = f"""
TASK="A"
WORKFLOW="Edge-Fog-Docker-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

NUM_FILES=10
OUTPUT_DIR="/home/{RASPI_USER}/edge_files_${{EXECUTION_ID}}"
SIZES=(1024 1048576 10485760)
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_GENERATED=0

LOG_FILE="/home/{RASPI_USER}/edge_fog_taskA_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task A: File Generation on Edge"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Edge (Raspberry Pi Docker)"
echo "=========================================="

# Create output directory
mkdir -p "${{OUTPUT_DIR}}"
echo "Output directory created: ${{OUTPUT_DIR}}"
echo ""

# Generate files
for i in $(seq 1 $NUM_FILES); do
    # Distribute file sizes across the 10 files
    size_idx=$(((i - 1) % 3))
    size=${{SIZES[$size_idx]}}
    size_name=${{SIZE_NAMES[$size_idx]}}
    
    filename="${{OUTPUT_DIR}}/file_${{i}}_${{size_name}}.dat"
    
    echo "Generating file $i of $NUM_FILES (size: ${{size_name}})..."
    
    # Generate random file using dd with /dev/urandom
    if dd if=/dev/urandom of="$filename" bs="$size" count=1 status=none 2>/dev/null; then
        echo "  Created: $filename"
        FILES_GENERATED=$((FILES_GENERATED + 1))
    else
        echo "  ERROR creating: $filename"
        SUCCESS=0
    fi
done

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")

echo ""
echo "=========================================="
echo "Task A completed in ${{DURATION}} seconds"
echo "Files generated: ${{FILES_GENERATED}}/${{NUM_FILES}}"
echo "Log saved to: $LOG_FILE"
echo "=========================================="

# Save metrics
METRICS_FILE="/home/{RASPI_USER}/edge_fog_taskA_metrics_${{EXECUTION_ID}}.json"
cat > "${{METRICS_FILE}}" << EOF
{{
  "task": "A",
  "workflow": "Edge-Fog-Docker-File-Processing",
  "execution_id": "${{EXECUTION_ID}}",
  "duration_seconds": ${{DURATION}},
  "success": ${{SUCCESS}},
  "files_generated": ${{FILES_GENERATED}},
  "edge_directory": "${{OUTPUT_DIR}}",
  "node": "edge-docker"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

# Create Task A (Edge - Remote Docker)
taskA = DagonTask(
    TaskType.DOCKER,
    "A",
    taskA_command,
    image="ubuntu:22.04",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    working_dir=f"/home/{RASPI_USER}/docker_scratch_{EXECUTION_ID}/taskA",
    volume=f"/home/{RASPI_USER}:/home/{RASPI_USER}"
)

# ========== TASK B: File Compression on Fog (Reading Phase) ==========
taskB_command = f"""
TASK="B"
WORKFLOW="Edge-Fog-Docker-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

NUM_FILES=10
INPUT_DIR="/tmp/fog_input_${{EXECUTION_ID}}"
OUTPUT_DIR="/tmp/fog_compressed_${{EXECUTION_ID}}"
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_COMPRESSED=0

LOG_FILE="/tmp/edge_fog_taskB_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task B: File Compression on Fog"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Fog (PC Docker)"
echo "=========================================="

# Check if input directory exists
if [ ! -d "${{INPUT_DIR}}" ]; then
    echo "ERROR: Input directory not found: ${{INPUT_DIR}}"
    SUCCESS=0
    exit 1
fi

# Create output directory
mkdir -p "${{OUTPUT_DIR}}"
echo "Output directory created: ${{OUTPUT_DIR}}"
echo ""

echo "Running compression on Fog node..."
echo ""

for i in $(seq 1 $NUM_FILES); do
    size_idx=$(((i - 1) % 3))
    size_name=${{SIZE_NAMES[$size_idx]}}
    
    input_file="${{INPUT_DIR}}/file_${{i}}_${{size_name}}.dat"
    output_file="${{OUTPUT_DIR}}/file_${{i}}_${{size_name}}.gz"
    
    echo "Compressing file $i of $NUM_FILES..."
    
    if [ ! -f "$input_file" ]; then
        echo "  ERROR: File not found: $input_file"
        SUCCESS=0
        continue
    fi
    
    # Compress file using gzip
    if gzip -c "$input_file" > "$output_file" 2>&1; then
        if [ -f "$output_file" ]; then
            original_size=$(stat -c%s "$input_file" 2>/dev/null)
            compressed_size=$(stat -c%s "$output_file" 2>/dev/null)
            compression_ratio=$(awk "BEGIN {{printf \\"%.2f\\", ($original_size - $compressed_size) * 100 / $original_size}}")
            
            echo "  Compressed: $(basename $input_file) -> $(basename $output_file) (${{compression_ratio}}% reduction)"
            FILES_COMPRESSED=$((FILES_COMPRESSED + 1))
        else
            echo "  ERROR: Output file not created: $output_file"
            SUCCESS=0
        fi
    else
        echo "  ERROR: gzip command failed for: $input_file"
        SUCCESS=0
    fi
done

END_TS=$(date +%s.%N)
DURATION=$(awk "BEGIN {{print ${{END_TS}}-${{START_TS}}}}")

echo ""
echo "=========================================="
echo "Task B completed in ${{DURATION}} seconds"
echo "Files compressed: ${{FILES_COMPRESSED}}/${{NUM_FILES}}"
echo "Log saved to: $LOG_FILE"
echo "=========================================="

# Save metrics
METRICS_FILE="/tmp/edge_fog_taskB_metrics_${{EXECUTION_ID}}.json"
cat > "${{METRICS_FILE}}" << EOF
{{
  "task": "B",
  "workflow": "Edge-Fog-Docker-File-Processing",
  "execution_id": "${{EXECUTION_ID}}",
  "duration_seconds": ${{DURATION}},
  "success": ${{SUCCESS}},
  "files_compressed": ${{FILES_COMPRESSED}},
  "input_directory": "${{INPUT_DIR}}",
  "output_directory": "${{OUTPUT_DIR}}",
  "node": "fog-docker"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

# Create Task B (Fog - Local Docker)
taskB = DagonTask(
    TaskType.DOCKER,
    "B",
    taskB_command,
    image="ubuntu:22.04",
    working_dir=f"/tmp/docker_scratch_{EXECUTION_ID}/taskB",
    volume="/tmp:/tmp"
    # No ip, ssh_username - runs locally
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
    workflow_a = Workflow("Edge-File-Generation")
    workflow_a.add_task(taskA)
    workflow_a.run()
    print("\n✓ Task A completed successfully\n")
    taskA_success = True
except Exception as e:
    print(f"\n✗ Error in Task A: {e}\n")
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
    
    print(f"Executing: {' '.join(scp_cmd)}")
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
    sys.exit(1)

# Execute Task B (Fog) in its own workflow
print("="*70)
print("PHASE 3: File Compression on Fog Node")
print("="*70)
try:
    workflow_b = Workflow("Fog-File-Compression")
    workflow_b.add_task(taskB)
    workflow_b.run()
    workflow_success = True
    print("\n✓ Task B completed successfully")
    print("\nWorkflow completed successfully")
except Exception as e:
    workflow_success = False
    print(f"\n✗ Error in Task B: {e}")

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

# ========== PERFORMANCE SUMMARY ==========
print("\n" + "="*70)
print("PERFORMANCE SUMMARY - EDGE-FOG DISTRIBUTED DOCKER PROCESSING")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Total Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS' if workflow_success else 'FAILED'}")
print("")
print("Architecture:")
print(f"  Edge Node (Raspberry Pi): Docker container @ {RASPI_IP}")
print(f"  Fog Node (PC): Docker container @ localhost")
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
print("Verification Commands:")
print(f"  View compressed files: ls -lh /tmp/fog_compressed_{EXECUTION_ID}/")
print(f"  View Task B metrics: cat /tmp/edge_fog_taskB_metrics_{EXECUTION_ID}.json")
print(f"  View Task A metrics: ssh {RASPI_USER}@{RASPI_IP} 'cat /home/{RASPI_USER}/edge_fog_taskA_metrics_{EXECUTION_ID}.json'")
print("="*70 + "\n")

# Allow time for cleanup
time.sleep(2)
sys.exit(0)