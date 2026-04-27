#!/bin/bash
# Quick startup script for hardware mode testing
# Usage: ./start_hardware_mode.sh

set -e

PROJECT_ROOT="/home/lester/Documents/smart-microgrid-manager"
VENV="$PROJECT_ROOT/.venv"

echo "🔧 Smart Microgrid Manager - Hardware Mode Startup"
echo "=================================================="

# Check virtual environment
if [ ! -d "$VENV" ]; then
  echo "❌ Virtual environment not found at $VENV"
  exit 1
fi

# Activate venv
source "$VENV/bin/activate"

echo "✅ Virtual environment activated"
echo ""

# Check MySQL
echo "📊 Checking MySQL..."
if mysql -u root -pVirus1738 -e "SELECT 1 FROM smart_microgrid.battery_readings LIMIT 1" &>/dev/null; then
  echo "✅ MySQL connected"
else
  echo "⚠️  MySQL connection failed. Backend will try anyway..."
fi

echo ""

# Check MQTT
echo "🔌 Checking MQTT Broker..."
if timeout 2 bash -c 'cat < /dev/null > /dev/tcp/localhost/1883' 2>/dev/null; then
  echo "✅ MQTT Broker (Mosquitto) running on localhost:1883"
else
  echo "❌ MQTT Broker not reachable on localhost:1883"
  echo "   Start Mosquitto: sudo systemctl start mosquitto"
  exit 1
fi

echo ""
echo "=================================================="
echo "🚀 Starting Backend (Hardware Mode)"
echo "=================================================="
echo ""
echo "API will be available at:"
echo "  📍 http://localhost:8001"
echo "  📊 API Docs: http://localhost:8001/docs"
echo ""
echo "In another terminal, run:"
echo "  1. mosquitto_sub -t 'microgrid/#' -v  (Monitor MQTT)"
echo "  2. cd webui && npm run dev               (Start Web UI)"
echo ""
echo "Press Ctrl+C to stop backend"
echo ""
echo "=================================================="

cd "$PROJECT_ROOT/backend"
PYTHONPATH=.. uvicorn app.main:app --reload --port 8001
