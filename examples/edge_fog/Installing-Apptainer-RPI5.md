# Installing Apptainer on Raspberry Pi 5

Guide to install Apptainer 1.4.4 on Raspberry Pi 5 with Debian 13 (Trixie) ARM64.

## System Information

- **Hardware**: Raspberry Pi 5
- **Operating System**: Debian GNU/Linux 13 (Trixie)
- **Architecture**: aarch64 (ARM64)
- **Apptainer Version**: 1.4.4

## Prerequisites

Ensure you have root access (sudo) and internet connection.

## Step 1: Update the System

```bash
sudo apt update
sudo apt upgrade -y
```

## Step 2: Install System Dependencies

### Basic build dependencies

```bash
sudo apt install -y \
    build-essential \
    libseccomp-dev \
    pkg-config \
    uidmap \
    squashfs-tools \
    squashfuse \
    fuse2fs \
    fuse-overlayfs \
    fakeroot \
    cryptsetup \
    curl \
    git
```

### FUSE dependencies

```bash
sudo apt install -y \
    autoconf \
    automake \
    libtool \
    libfuse3-dev \
    zlib1g-dev \
    liblzo2-dev \
    liblz4-dev \
    liblzma-dev \
    libzstd-dev
```

### Linking tools

```bash
sudo apt install -y \
    binutils \
    binutils-gold \
    binutils-aarch64-linux-gnu \
    gcc \
    g++
```

## Step 3: Install Go

Apptainer requires Go to compile. Install Go 1.22.0 or higher:

```bash
# Download Go for ARM64
cd /tmp
wget https://go.dev/dl/go1.22.0.linux-arm64.tar.gz

# Remove previous Go installation if it exists
sudo rm -rf /usr/local/go

# Extract and install Go
sudo tar -C /usr/local -xzf go1.22.0.linux-arm64.tar.gz

# Add Go to PATH
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Verify installation
go version
```

You should see: `go version go1.22.0 linux/arm64`

## Step 4: Download Apptainer

```bash
# Define Apptainer version
export VERSION=1.4.4

# Download source code
cd /tmp
wget https://github.com/apptainer/apptainer/releases/download/v${VERSION}/apptainer-${VERSION}.tar.gz

# Extract the file
tar -xzf apptainer-${VERSION}.tar.gz
cd apptainer-${VERSION}
```

## Step 5: Configure and Compile Apptainer

### Configure the project

```bash
./mconfig --prefix=/usr/local
```

This step may take between 5-15 minutes.

### Compile Apptainer

```bash
cd builddir
make -j4
```

The `-j4` option uses the 4 cores of the Raspberry Pi 5 for parallel compilation. This step may take between 15-30 minutes.

## Step 6: Install Apptainer

```bash
sudo make install
```

## Step 7: Compile and Install FUSE Dependencies

FUSE dependencies are necessary to mount file systems inside containers.

```bash
# Return to Apptainer base directory
cd /tmp/apptainer-${VERSION}

# Download dependencies
./scripts/download-dependencies

# Compile dependencies (may take 10-20 minutes)
./scripts/compile-dependencies

# Install dependencies
sudo ./scripts/install-dependencies
```

## Step 8: Verify Installation

```bash
# View installed version
apptainer version
```

You should see: `1.4.4`

### Test Apptainer

```bash
# Run a test container
apptainer run docker://hello-world

# Run a compatible ARM64 image
apptainer run docker://arm64v8/ubuntu:latest cat /etc/os-release
```

## Common Troubleshooting

### Error: "cannot find 'ld'"

If you receive this error during compilation:

```bash
sudo apt install -y binutils-gold
```

### Error: Timeout when downloading images

If you have network issues when downloading Docker images:

1. Verify your internet connection
2. Try again later
3. Use alternative mirrors if necessary

### Error: "nodev" mount option warning

This is just a warning and should not prevent normal operation. It appears because `/tmp` is mounted with the `nodev` option.

## Basic Apptainer Usage

### Run a container

```bash
apptainer run docker://ubuntu:latest
```

### Create a SIF image from Docker

```bash
apptainer pull docker://ubuntu:latest
```

### Execute commands in a container

```bash
apptainer exec docker://ubuntu:latest cat /etc/os-release
```

### Interactive shell

```bash
apptainer shell docker://ubuntu:latest
```

## Important Notes

1. **ARM64 Architecture**: Make sure to use images compatible with ARM64/aarch64. Look for images tagged as `arm64v8/` or verify they support ARM architecture.

2. **Disk space**: Compiling Apptainer and its dependencies requires approximately 1-2 GB of free space.

3. **Compilation time**: The complete process may take between 30-60 minutes on a Raspberry Pi 5.

4. **Memory**: It is recommended to have at least 2 GB of available RAM during compilation.

## Cleanup (Optional)

After successful installation, you can remove compilation files:

```bash
cd /tmp
rm -rf apptainer-${VERSION}
rm -f apptainer-${VERSION}.tar.gz
rm -f go1.22.0.linux-arm64.tar.gz
```

## Uninstallation

If you need to uninstall Apptainer:

```bash
# Remove binaries and configuration files
sudo rm -rf /usr/local/bin/apptainer
sudo rm -rf /usr/local/bin/singularity
sudo rm -rf /usr/local/libexec/apptainer
sudo rm -rf /usr/local/etc/apptainer
sudo rm -rf /usr/local/share/man/man1/apptainer*
sudo rm -rf /usr/local/share/man/man1/singularity*
sudo rm -rf /usr/local/share/bash-completion/completions/apptainer
sudo rm -rf /usr/local/share/bash-completion/completions/singularity
sudo rm -rf /usr/local/var/apptainer
```

## References

- [Official Apptainer Repository](https://github.com/apptainer/apptainer)
- [Apptainer Documentation](https://apptainer.org/docs/)
- [Official Installation Guide](https://github.com/apptainer/apptainer/blob/main/INSTALL.md)