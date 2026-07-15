#!/usr/bin/env python3
"""
Edge-Only Processing Workflow with Dagon using Kubernetes (K3S)
Performs file generation and compression entirely on the Edge node (Raspberry Pi)
Task A: Generate 10 random files with different sizes (1KB, 1MB, 10MB)
Task B: Read and compress the generated files on the SAME Raspberry Pi via Kubernetes
"""

import json, configparser, logging, time, sys
from dagon import Workflow
from dagon.task import DagonTask, TaskType

# Read SSH configuration
config = configparser.ConfigParser()
config.read('dagon.ini')

# We use the same configuration keys as edge_apptainer_script.py
RASPI_IP = config.get('ssh', 'raspi_ip')
RASPI_USER = config.get('ssh', 'raspi_user')
RASPI_PORT = config.getint('ssh', 'raspi_port')

EXECUTION_ID = time.strftime("%Y%m%d_%H%M%S")

print("="*70)
print("EDGE-ONLY Kubernetes Workflow - Performance Test")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Edge Node: {RASPI_IP}")
print(f"Total files: 10 (mixed sizes: 1KB, 1MB, 10MB)")
print(f"Architecture: ALL processing on Kubernetes (Edge node)")
print("="*70 + "\n")

# Create workflow
workflow = Workflow("Edge-Only-K8s-File-Processing")

# ========== TASK A: File Generation (Writing Phase) ==========
taskA_command = f"""
TASK="A"
WORKFLOW="Edge-Only-K8s-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

NUM_FILES=10
OUTPUT_DIR="generated_files"
SIZES=(1024 1048576 10485760)
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_GENERATED=0

LOG_FILE="taskA_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task A: File Generation (K8S)"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Kubernetes Pod on Edge"
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
echo "Log saved to pod: $LOG_FILE"
echo "=========================================="

# Save metrics
METRICS_FILE="taskA_metrics_${{EXECUTION_ID}}.json"
cat > "${{METRICS_FILE}}" << EOF
{{
  "task": "A",
  "workflow": "${{WORKFLOW}}",
  "execution_id": "${{EXECUTION_ID}}",
  "duration_seconds": ${{DURATION}},
  "success": ${{SUCCESS}},
  "files_generated": ${{FILES_GENERATED}},
  "output_directory": "${{OUTPUT_DIR}}",
  "node": "edge-k8s"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

taskA = DagonTask(
    TaskType.KUBERNETES,
    "A",
    taskA_command,
    image="alpine:latest",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
)

workflow.add_task(taskA)


# ========== TASK B: File Compression (Reading Phase) ==========
# We use workflow:///A/generated_files to get the directory from Task A
taskB_command = f"""
TASK="B"
WORKFLOW="Edge-Only-K8s-File-Processing"
EXECUTION_ID="{EXECUTION_ID}"

SRC_DIR="workflow:///A/generated_files"
NUM_FILES=10
INPUT_DIR="input_files"
OUTPUT_DIR="compressed_files"
SIZE_NAMES=("1KB" "1MB" "10MB")

START_TS=$(date +%s.%N)
SUCCESS=1
FILES_COMPRESSED=0

LOG_FILE="taskB_${{EXECUTION_ID}}.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Starting Task B: File Compression (K8S)"
echo "Execution ID: ${{EXECUTION_ID}}"
echo "Date: $(date)"
echo "Node: Kubernetes Pod on Edge"
echo "=========================================="

# Prepare input directory by copying from Task A's output
echo "Fetching files from Task A..."
mkdir -p "${{INPUT_DIR}}"
cp -rv ${{SRC_DIR}}/* "${{INPUT_DIR}}/"

# Check if input directory is empty
if [ -z "$(ls -A ${{INPUT_DIR}})" ]; then
    echo "ERROR: No files found in ${{INPUT_DIR}}"
    SUCCESS=0
    exit 1
fi

# Create output directory
mkdir -p "${{OUTPUT_DIR}}"
echo "Output directory created: ${{OUTPUT_DIR}}"
echo ""

# Check if gzip is available
if ! command -v gzip &> /dev/null; then
    echo "Installing gzip..."
    apk add --no-cache gzip bash coreutils
fi

echo "Running compression on Kubernetes pod..."
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
echo "Log saved to pod: $LOG_FILE"
echo "=========================================="

# Save metrics
METRICS_FILE="taskB_metrics_${{EXECUTION_ID}}.json"
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
  "node": "edge-k8s"
}}
EOF

echo "Metrics saved to: ${{METRICS_FILE}}"
"""

taskB = DagonTask(
    TaskType.KUBERNETES,
    "B",
    taskB_command,
    image="alpine:latest",
    ip=RASPI_IP,
    ssh_username=RASPI_USER,
    ssh_port=RASPI_PORT
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

workflow_end = time.time()
workflow_duration = workflow_end - workflow_start

# ========== PERFORMANCE SUMMARY ==========
print("\n" + "="*70)
print("PERFORMANCE SUMMARY - EDGE KUBERNETES PROCESSING")
print("="*70)
print(f"Execution ID: {EXECUTION_ID}")
print(f"Total Duration: {workflow_duration:.2f}s")
print(f"Status: {'SUCCESS' if workflow_success else 'FAILED'}")
print("")
print("Architecture: ALL tasks on K3S Pods (Edge)")
print("")
print("File Distribution:")
print("  1KB files: 4")
print("  1MB files: 3")
print("  10MB files: 3")
print("")
print("Files Location (inside Pods):")
print(f"  Generated: Task A working directory /generated_files/")
print(f"  Compressed: Task B working directory /compressed_files/")
print("")
print("Metrics stored in Pods.")
print("="*70 + "\n")

# Allow time for cleanup
time.sleep(2)
sys.exit(0)
