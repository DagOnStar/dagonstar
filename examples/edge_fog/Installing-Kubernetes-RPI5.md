# Installing K3s on Raspberry Pi 5 with Debian 13 (Trixie) ARM64

## 1. Prepare the system

First, update your system:

```bash
sudo apt update
sudo apt upgrade -y
```

## 2. Enable cgroups (required for Kubernetes)

Edit the boot configuration file:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Add at the end of the line (without creating a new line):

```bash
cgroup_memory=1 cgroup_enable=memory
```

Save the changes with **Ctrl+O**, **Enter**, and **Ctrl+X**.

Reboot your Raspberry Pi:

```bash
sudo reboot
```

Wait for it to restart completely (approximately 2-3 minutes).

## 3. Install K3s

After the reboot, install K3s using the official script:

```bash
curl -sfL https://get.k3s.io | sh -
```

The script will automatically download and install K3s. This process may take several minutes.

To install a specific version:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.28.5+k3s1 sh -
```

Once completed, K3s should be running as a systemd service.

## 4. Verify the installation

Check that K3s is running correctly:

```bash
sudo systemctl status k3s
```

You should see the service is active and running.

Verify your available nodes:

```bash
sudo k3s kubectl get nodes
```

This should display your Raspberry Pi as a ready node.

Check the system pods:

```bash
sudo k3s kubectl get pods -A
```

## 5. Configure kubectl (optional but recommended)

### Option A: Use an alias (simpler)

Add an alias to your `.bashrc` file to execute kubectl without sudo:

```bash
echo "alias kubectl='sudo k3s kubectl'" >> ~/.bashrc
source ~/.bashrc
```

Now you can use `kubectl` directly without typing `sudo k3s kubectl`.

### Option B: Copy kubeconfig (recommended)

To use kubectl without sudo and have the configuration in your user account:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

Set the KUBECONFIG environment variable for your session and permanently:

```bash
export KUBECONFIG=$HOME/.kube/config
echo "export KUBECONFIG=$HOME/.kube/config" >> ~/.bashrc
```

Reload your shell configuration:

```bash
source ~/.bashrc
```

Verify it works:

```bash
kubectl get nodes
```

You should see your node without needing sudo. This configuration works with all Kubernetes tools and is portable across different environments.

---

## Uninstall Kubernetes (k3s)
sudo /usr/local/bin/k3s-uninstall.sh

## Clean up leftovers
sudo rm -rf /etc/rancher/
sudo rm -rf /var/lib/rancher/
sudo rm -rf /usr/local/bin/k3s*
sudo rm -rf ~/.kube/