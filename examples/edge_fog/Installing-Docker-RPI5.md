a

# Docker Installation Guide for Raspberry Pi 5

Installing Docker on a **Raspberry Pi 5** is straightforward because the Pi 5's **ARM64** architecture is fully supported by the official Docker convenience script.

Follow this step-by-step guide to get Docker and Docker Compose running.

---

## 1. Update Your System

Before starting, ensure your package list and existing software are up to date. Open your terminal (or SSH in) and run:

```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Install Docker

Run the official Docker convenience script to install Docker and Docker Compose:

```bash
curl -sSL https://get.docker.com | sh
```

## 3. Add Your User to the Docker Group

By default, Docker commands require sudo. To run Docker as your current user (usually pi or your custom username), add yourself to the docker group:

```bash
sudo usermod -aG docker $USER
```

Note: For this change to take effect, you must log out and log back in, or simply reboot your Pi: sudo reboot.

## 4. Verify the Installation

After logging back in, test that Docker is working by running the "Hello World" container:

```bash
docker run hello-world
```

If you see a message saying "Hello from Docker!", the installation was successful.
