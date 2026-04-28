#!/usr/bin/env python3
"""
Edge-Only Processing Workflow with Dagon
Performs file generation and compression entirely on the Edge node (Raspberry Pi)
Task A: Generate 10 random files with different sizes (1KB, 1MB, 10MB)
Task B: Read and compress the generated files on the SAME Raspberry Pi
"""

import json, configparser, logging, time
from dagon import Workflow
from dagon.task import DagonTask, TaskType

# Read SSH configuration
config = configparser.ConfigParser()
config.read('dagon.ini')

RASPI_IP = config.get('ssh', 'raspi_ip')
RASPI_USER = config.get('ssh', 'raspi_user')
RASPI_PORT = config.getint('ssh', 'raspi_port')

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("EDGE-ONLY Processing Workflow - Performance Test")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node: {RASPI_IP}")
print(f"Total files: 10 (mixed sizes: 1KB, 1MB, 10MB)")
print(f"Architecture: ALL processing on Raspberry Pi (Edge only)")
print("="*70 + "\n")

# Create workflow
workflow = Workflow("Edge-Only-File-Processing")

# ========== TASK A: File Generation (Writing Phase) ==========
taskA_command = f"""
TASK="A"
WORKFLOW="Edge-Only-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

NUM_FILES=10
OUTPUT_DIR="/home/raspi/edge_only_files_${{EXECUTION_ID}}"
SIZES=(1024 1048576 10485760)
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_GENERATED=0

LOG_FILE="/home/raspi/edge_only_taskA_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task A: File Generation (EDGE)"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Raspberry Pi (Edge)"
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
METRICS_FILE="/home/raspi/edge_only_taskA_metrics_${{EXECUTION_ID}}.json"
cat > "${{METRICS_FILE}}" << EOF
{{
  "task": "A",
  "workflow": "${{WORKFLOW}}",
  "execution_id": "${{EXECUTION_ID}}",
  "duration_seconds": ${{DURATION}},
  "success": ${{SUCCESS}},
  "files_generated": ${{FILES_GENERATED}},
  "output_directory": "${{OUTPUT_DIR}}",
  "node": "edge"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

taskA = DagonTask(
    TaskType.APPTAINER,
    "A",
    taskA_command,
    image="docker://bash:5",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

taskA.extra_args = [
    "--bind", "/home/raspi:/home/raspi",
    "--writable-tmpfs"
]

workflow.add_task(taskA)


# ========== TASK B: File Compression (Reading Phase) ==========
taskB_command = f"""
TASK="B"
WORKFLOW="Edge-Only-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

NUM_FILES=10
INPUT_DIR="/home/raspi/edge_only_files_${{EXECUTION_ID}}"
OUTPUT_DIR="/home/raspi/edge_only_compressed_${{EXECUTION_ID}}"
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_COMPRESSED=0

LOG_FILE="/home/raspi/edge_only_taskB_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task B: File Compression (EDGE)"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Raspberry Pi (Edge)"
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

# Check if gzip is available (should be in all images)
if ! command -v gzip &> /dev/null; then
    echo "ERROR: gzip not available"
    SUCCESS=0
    exit 1
else
    echo "Using gzip for compression"
fi

echo ""

# Compress files
echo "Running compression on Edge node..."
echo "Looking for files in: ${{INPUT_DIR}}"
ls -lh "${{INPUT_DIR}}" 2>&1 || echo "Directory listing failed"
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
METRICS_FILE="/home/raspi/edge_only_taskB_metrics_${{EXECUTION_ID}}.json"
cat > "${{METRICS_FILE}}" << EOF
{{
  "task": "B",
  "workflow": "${{WORKFLOW}}",
  "execution_id": "${{EXECUTION_ID}}",
  "duration_seconds": ${{DURATION}},
  "success": ${{SUCCESS}},
  "files_compressed": ${{FILES_COMPRESSED}},
  "input_directory": "${{INPUT_DIR}}",
  "output_directory": "${{OUTPUT_DIR}}",
  "node": "edge"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

taskB = DagonTask(
    TaskType.APPTAINER,
    "B",
    taskB_command,
    image="docker://ubuntu:22.04",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

taskB.extra_args = [
    "--bind", "/home/raspi:/home/raspi",
    "--writable-tmpfs"
]

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

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

# ========== PERFORMANCE SUMMARY ==========
print("\n" + "="*70)
print("PERFORMANCE SUMMARY - EDGE-ONLY PROCESSING")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Total Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS' if workflow_success else 'FAILED'}")
print("")
print("Architecture: ALL tasks on Raspberry Pi (Edge)")
print("")
print("File Distribution:")
print("  1KB files: 4")
print("  1MB files: 3")
print("  10MB files: 3")
print("")
print("Files Location (all on Raspberry Pi):")
print(f"  Generated: /home/raspi/edge_only_files_{EXECUTION_ID}/")
print(f"  Compressed: /home/raspi/edge_only_compressed_{EXECUTION_ID}/")
print("")
print("Metrics Files (on Raspberry Pi):")
print(f"  Task A: /home/raspi/edge_only_taskA_metrics_{EXECUTION_ID}.json")
print(f"  Task B: /home/raspi/edge_only_taskB_metrics_{EXECUTION_ID}.json")
print("="*70 + "\n")