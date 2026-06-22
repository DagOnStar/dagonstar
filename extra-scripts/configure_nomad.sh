#!/bin/bash
# Script de configuración de Nomad para Raspberry Pi
# Para usar cuando Nomad ya está instalado via apt

set -e

echo "=========================================="
echo "Configuración de Nomad para Dagon"
echo "=========================================="
echo ""

# Verificar que Nomad está instalado
if ! command -v nomad &> /dev/null; then
    echo "ERROR: Nomad no está instalado"
    echo "Instálalo con:"
    echo "  curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg"
    echo "  echo 'deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main' | sudo tee /etc/apt/sources.list.d/hashicorp.list"
    echo "  sudo apt update && sudo apt install nomad"
    exit 1
fi

echo "Nomad detectado:"
nomad version
echo ""

# Verificar Docker
echo "Verificando Docker..."
if ! command -v docker &> /dev/null; then
    echo "Docker no encontrado. Instalando..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "Docker instalado correctamente"
    echo "NOTA: Debes cerrar sesión e iniciar de nuevo para usar Docker sin sudo"
else
    echo "Docker ya está instalado"
    docker --version
fi
echo ""

# Crear directorios necesarios
echo "Creando directorios de configuración..."
sudo mkdir -p /etc/nomad.d
sudo mkdir -p /opt/nomad/data
sudo mkdir -p /var/log/nomad
sudo chmod 755 /opt/nomad/data
sudo chmod 755 /var/log/nomad
echo "Directorios creados"
echo ""

# Detectar interfaz de red principal
NETWORK_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
echo "Interfaz de red detectada: $NETWORK_INTERFACE"
echo ""

# Crear archivo de configuración
echo "Creando archivo de configuración de Nomad..."
sudo tee /etc/nomad.d/nomad.hcl > /dev/null <<EOF
# Configuración de Nomad para Raspberry Pi con Dagon
# Generado automáticamente por configure_nomad.sh

datacenter = "dc1"
data_dir = "/opt/nomad/data"

# Configuración del servidor
server {
  enabled = true
  bootstrap_expect = 1
}

# Configuración del cliente
client {
  enabled = true
  
  network_interface = "$NETWORK_INTERFACE"
  
  # Habilitar driver raw_exec (opcional)
  options {
    "driver.raw_exec.enable" = "1"
  }
  
  # Volúmenes del host disponibles para los jobs
  host_volume "home" {
    path = "/home"
    read_only = false
  }
  
  host_volume "tmp" {
    path = "/tmp"
    read_only = false
  }
  
  host_volume "data" {
    path = "/data"
    read_only = false
  }
  
  # Reservar recursos para el sistema
  reserved {
    cpu = 500      # 500 MHz reservados
    memory = 512   # 512 MB reservados
  }
}

# Configuración del plugin Docker
plugin "docker" {
  config {
    # Habilitar montaje de volúmenes
    volumes {
      enabled = true
    }
    
    # No permitir contenedores privilegiados por seguridad
    allow_privileged = false
    
    # Capabilities permitidas
    allow_caps = [
      "CHOWN", "DAC_OVERRIDE", "FSETID", "FOWNER", 
      "MKNOD", "NET_RAW", "SETGID", "SETUID", 
      "SETFCAP", "SETPCAP", "NET_BIND_SERVICE", 
      "SYS_CHROOT", "KILL", "AUDIT_WRITE"
    ]
    
    # Garbage collection de imágenes y contenedores
    gc {
      image = true
      image_delay = "5m"
      container = true
    }
    
    # Límites de pull de imágenes
    pull_activity_timeout = "5m"
  }
}

# Telemetría para monitoreo
telemetry {
  publish_allocation_metrics = true
  publish_node_metrics = true
  prometheus_metrics = true
}

# Configuración de logs
log_level = "INFO"
log_file = "/var/log/nomad/nomad.log"
log_rotate_max_files = 5
EOF

echo "Configuración creada en /etc/nomad.d/nomad.hcl"
echo ""

# Verificar si ya existe el servicio systemd
if [ -f /lib/systemd/system/nomad.service ]; then
    echo "Servicio systemd de Nomad ya existe (instalado por apt)"
else
    # Crear servicio systemd (por si acaso)
    echo "Creando servicio systemd..."
    sudo tee /etc/systemd/system/nomad.service > /dev/null <<EOF
[Unit]
Description=Nomad
Documentation=https://www.nomadproject.io/docs/
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
Group=root
ExecReload=/bin/kill -HUP \$MAINPID
ExecStart=/usr/bin/nomad agent -config=/etc/nomad.d
KillMode=process
Restart=on-failure
RestartSec=2
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
fi

# Recargar systemd y habilitar servicio
echo "Habilitando servicio Nomad..."
sudo systemctl daemon-reload
sudo systemctl enable nomad
sudo systemctl restart nomad

# Esperar a que Nomad esté listo
echo ""
echo "Esperando a que Nomad esté listo..."
sleep 3

# Verificar estado
echo ""
echo "=========================================="
echo "Estado del servicio:"
sudo systemctl status nomad --no-pager -l || true
echo ""
echo "=========================================="

# Obtener IP
IP=$(hostname -I | awk '{print $1}')

# Verificar que Nomad responde
echo ""
echo "Verificando conectividad con Nomad API..."
sleep 2

if curl -s "http://localhost:4646/v1/status/leader" > /dev/null 2>&1; then
    echo "✓ Nomad API está respondiendo correctamente"
else
    echo "⚠ Nomad API no está respondiendo todavía"
    echo "  Espera unos segundos y verifica con: curl http://localhost:4646/v1/status/leader"
fi

echo ""
echo "=========================================="
echo "¡Configuración completada!"
echo "=========================================="
echo ""
echo "Información de Nomad:"
echo "  Versión: $(nomad version | head -n1)"
echo "  API: http://$IP:4646"
echo "  Web UI: http://$IP:4646/ui"
echo ""
echo "Comandos útiles:"
echo "  - Ver estado: sudo systemctl status nomad"
echo "  - Ver logs: sudo journalctl -u nomad -f"
echo "  - Ver logs archivo: tail -f /var/log/nomad/nomad.log"
echo "  - Listar jobs: nomad job status"
echo "  - Ver nodos: nomad node status"
echo "  - Ver servidor: nomad server members"
echo ""
echo "Configuración para dagon.ini:"
echo ""
echo "[nomad]"
echo "address = http://$IP:4646"
echo "datacenter = dc1"
echo "region = global"
echo ""

# Verificar Docker
if groups $USER | grep -q docker; then
    echo "✓ Usuario '$USER' está en el grupo docker"
else
    echo "⚠ Usuario '$USER' NO está en el grupo docker"
    echo "  Ejecuta: sudo usermod -aG docker $USER"
    echo "  Luego cierra sesión e inicia de nuevo"
fi

echo ""
echo "Para probar la configuración:"
echo "  nomad node status"
echo "  curl http://localhost:4646/v1/status/leader"
echo ""
