#!/bin/bash
# Script de verificación rápida del estado de Nomad
# check_nomad.sh

echo "======================================"
echo "Verificación de Nomad para Dagon"
echo "======================================"
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para verificar con ✓ o ✗
check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

# 1. Verificar que Nomad está instalado
echo "1. Verificando instalación de Nomad..."
if command -v nomad &> /dev/null; then
    VERSION=$(nomad version | head -n1)
    check_status 0 "Nomad instalado: $VERSION"
    NOMAD_PATH=$(which nomad)
    echo "   Ubicación: $NOMAD_PATH"
else
    check_status 1 "Nomad NO está instalado"
    exit 1
fi
echo ""

# 2. Verificar servicio systemd
echo "2. Verificando servicio systemd..."
if systemctl is-active --quiet nomad; then
    check_status 0 "Servicio Nomad está activo"
else
    check_status 1 "Servicio Nomad NO está activo"
    echo "   Intenta: sudo systemctl start nomad"
fi

if systemctl is-enabled --quiet nomad; then
    check_status 0 "Servicio Nomad está habilitado (auto-inicio)"
else
    check_status 1 "Servicio Nomad NO está habilitado"
    echo "   Intenta: sudo systemctl enable nomad"
fi
echo ""

# 3. Verificar Docker
echo "3. Verificando Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    check_status 0 "Docker instalado: $DOCKER_VERSION"
    
    if docker ps &> /dev/null; then
        check_status 0 "Docker está funcionando"
    else
        check_status 1 "Docker requiere permisos root"
        echo "   Ejecuta: sudo usermod -aG docker $USER"
        echo "   Luego cierra sesión y vuelve a entrar"
    fi
else
    check_status 1 "Docker NO está instalado"
    echo "   Instala con: curl -fsSL https://get.docker.com | sh"
fi
echo ""

# 4. Verificar API de Nomad
echo "4. Verificando API de Nomad..."
if curl -s -f http://localhost:4646/v1/status/leader > /dev/null 2>&1; then
    LEADER=$(curl -s http://localhost:4646/v1/status/leader)
    check_status 0 "API de Nomad respondiendo"
    echo "   Leader: $LEADER"
else
    check_status 1 "API de Nomad NO responde"
    echo "   Verifica logs con: sudo journalctl -u nomad -n 50"
fi
echo ""

# 5. Verificar configuración
echo "5. Verificando archivos de configuración..."
if [ -f /etc/nomad.d/nomad.hcl ]; then
    check_status 0 "Archivo de configuración existe: /etc/nomad.d/nomad.hcl"
else
    check_status 1 "Archivo de configuración NO encontrado"
    echo "   Ejecuta: ./configure_nomad.sh"
fi

if [ -d /opt/nomad/data ]; then
    check_status 0 "Directorio de datos existe: /opt/nomad/data"
else
    check_status 1 "Directorio de datos NO existe"
fi
echo ""

# 6. Verificar nodos
echo "6. Verificando nodos de Nomad..."
NODE_COUNT=$(nomad node status 2>/dev/null | grep -c "ready" || echo "0")
if [ "$NODE_COUNT" -gt 0 ]; then
    check_status 0 "Nodos detectados: $NODE_COUNT"
    echo ""
    nomad node status
else
    check_status 1 "No hay nodos disponibles"
fi
echo ""

# 7. Verificar servidor
echo "7. Verificando servidor Nomad..."
if nomad server members &> /dev/null; then
    check_status 0 "Servidor Nomad operativo"
    echo ""
    nomad server members
else
    check_status 1 "Servidor Nomad no disponible"
fi
echo ""

# 8. Información de red
echo "8. Información de red..."
IP=$(hostname -I | awk '{print $1}')
echo "   IP local: $IP"
echo "   API: http://$IP:4646"
echo "   Web UI: http://$IP:4646/ui"
echo ""

# 9. Verificar puerto
echo "9. Verificando puerto 4646..."
if sudo netstat -tlnp 2>/dev/null | grep -q ":4646"; then
    check_status 0 "Puerto 4646 está abierto"
    sudo netstat -tlnp | grep 4646
else
    check_status 1 "Puerto 4646 no está en uso"
fi
echo ""

# 10. Estado de recursos
echo "10. Estado de recursos del sistema..."
echo "   CPU:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print "      Uso: " 100 - $1 "%"}'
echo "   Memoria:"
free -h | awk '/^Mem:/ {print "      Total: " $2 ", Usado: " $3 ", Libre: " $4}'
echo ""

# Resumen final
echo "======================================"
echo "RESUMEN"
echo "======================================"

ISSUES=0

# Contar problemas
if ! command -v nomad &> /dev/null; then ((ISSUES++)); fi
if ! systemctl is-active --quiet nomad; then ((ISSUES++)); fi
if ! command -v docker &> /dev/null; then ((ISSUES++)); fi
if ! curl -s -f http://localhost:4646/v1/status/leader > /dev/null 2>&1; then ((ISSUES++)); fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ Todo está funcionando correctamente${NC}"
    echo ""
    echo "Puedes ejecutar los tests de Dagon:"
    echo "  python test_nomad_integration.py"
    echo "  python edge_nomad_script.py"
else
    echo -e "${YELLOW}⚠ Se encontraron $ISSUES problema(s)${NC}"
    echo ""
    echo "Pasos sugeridos:"
    if ! command -v nomad &> /dev/null; then
        echo "  1. Instalar Nomad"
    fi
    if ! systemctl is-active --quiet nomad; then
        echo "  2. Iniciar servicio: sudo systemctl start nomad"
    fi
    if ! command -v docker &> /dev/null; then
        echo "  3. Instalar Docker"
    fi
    if ! curl -s -f http://localhost:4646/v1/status/leader > /dev/null 2>&1; then
        echo "  4. Verificar logs: sudo journalctl -u nomad -f"
    fi
fi

echo ""
echo "Para más ayuda:"
echo "  - Ver logs: sudo journalctl -u nomad -f"
echo "  - Ver archivo de log: tail -f /var/log/nomad/nomad.log"
echo "  - Configurar Nomad: ./configure_nomad.sh"
echo "======================================"
