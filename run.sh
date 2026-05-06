#!/usr/bin/env bash
# Heimdall -- start script

set -e

VENV=".venv"

# 1. Create venv if missing (auto-installs python3.X-venv if needed)
if [ ! -d "$VENV" ]; then
  echo "-> Creating virtual environment..."
  if ! python3 -m venv "$VENV" 2>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "-> Installing python${PY_VER}-venv (needs sudo)..."
    sudo apt-get install -y -qq "python${PY_VER}-venv"
    python3 -m venv "$VENV"
  fi
fi

# 2. Install deps
echo "-> Installing dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt

# 3. Grant port 53 binding capability (needed once after venv creation)
REAL_PY=$(readlink -f "$VENV/bin/python3")
if ! getcap "$REAL_PY" 2>/dev/null | grep -q cap_net_bind_service; then
  echo "-> Granting cap_net_bind_service to $REAL_PY (needs sudo)..."
  sudo setcap cap_net_bind_service=+eip "$REAL_PY"
fi

# 4. Detect LAN IP
LAN_IP=$("$VENV/bin/python3" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print(s.getsockname()[0])
s.close()
")

echo ""
echo "=============================="
echo " Heimdall is running!"
echo " Management UI : http://$LAN_IP:8080"
echo " DNS server    : $LAN_IP:53 (UDP)"
echo "=============================="
echo " Router DNS: set to $LAN_IP"
echo " Press Ctrl+C to stop."
echo ""

# 5. Start (port 8080 mgmt + port 53 DNS)
PROXY_IP="$LAN_IP" \
  "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8080 --log-level info
