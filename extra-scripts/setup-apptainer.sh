#!/usr/bin/env bash
set -e
echo "[Apptainer] Installing..."
# Detect and install according to the system
if command -v apptainer &> /dev/null || command -v singularity &> /dev/null; then
    echo "[Apptainer] Already installed"
elif [ -f /etc/debian_version ]; then
    sudo apt update && sudo apt install -y software-properties-common
    sudo add-apt-repository -y ppa:apptainer/ppa && sudo apt update
    sudo apt install -y apptainer
elif [ -f /etc/redhat-release ]; then
    sudo dnf install -y epel-release apptainer 2>/dev/null || sudo yum install -y epel-release singularity
else
    # Generic installation
    curl -s https://get.apptainer.org | bash
fi
# Configure directories and variables
echo "[Apptainer] Configuring environment..."
mkdir -p ~/.apptainer/{cache,tmp}
# Detect available command
APPTAINER_CMD="apptainer"
command -v apptainer &> /dev/null || APPTAINER_CMD="singularity"
# Configure variables permanently
cat >> ~/.bashrc << EOF
# Apptainer for DagOnStar
export APPTAINER_CACHEDIR=\$HOME/.apptainer/cache
export APPTAINER_TMPDIR=\$HOME/.apptainer/tmp
export APPTAINER_CMD=$APPTAINER_CMD
EOF
# Export for current session
export APPTAINER_CACHEDIR=$HOME/.apptainer/cache
export APPTAINER_TMPDIR=$HOME/.apptainer/tmp
export APPTAINER_CMD=$APPTAINER_CMD
# Install Python dependencies
pip install --quiet spython psutil filelock tqdm
echo "[Apptainer] Installation completed"
echo "Available command: $APPTAINER_CMD"
