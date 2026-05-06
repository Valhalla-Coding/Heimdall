#!/usr/bin/env bash
# Heimdall -- start script

set -e

VENV=".venv"

# 1. Ensure python3-venv + pip are installed
if ! dpkg -s python3-venv >/dev/null 2>&1 || ! dpkg -s python3-pip >/dev/null 2>&1; then
  echo "-> Installing Python tools (one-time, needs sudo)..."
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-venv python3-pip libcap2-bin
fi

# 2. If venv exists but activate is missing, it's broken -- nuke and recreate
if [ -d "$VENV" ] && [ ! -f "$VENV/bin/activate" ]; then
  echo "-> Removing broken venv..."
  rm -rf "$VENV"
fi

# 3. Create venv if missing
if [ ! -d "$VENV" ]; then
  echo "-> Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# 4. Activate (set +e guards against shells that return non-zero from source)
set +e
source "$VENV/bin/activate"
set -e

# Confirm we're inside the venv
if [ -z "$VIRTUAL_ENV" ]; then
  echo "ERROR: Failed to activate virtual environment."
  exit 1
fi

# 5. Install deps (always inside venv, never touches system Python)
echo "-> Installing/updating dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt

# 6. Grant low-port binding (53 + 80) without sudo at runtime
PYTHON_BIN="$VENV/bin/python3"
if ! getcap "$PYTHON_BIN" 2>/dev/null | grep -q cap_net_bind_service; then
  echo "-> Granting cap_net_bind_service (needs sudo once)..."
  sudo setcap cap_net_bind_service=+eip "$PYTHON_BIN"
fi

# 7. Detect LAN IP
LAN_IP=$("$VENV/bin/python3" -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print(s.getsockname()[0])
s.close()
")
echo "-> Detected LAN IP: $LAN_IP"

# 8. Start management UI on port 8080
echo "-> Starting Heimdall on http://$LAN_IP:8080 ..."
PROXY_IP="$LAN_IP" DNS_PORT=53 \
  "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --log-level info &
MGMT_PID=$!

# 9. Start HTTP proxy on port 80
echo "-> Starting HTTP proxy on port 80 ..."
PROXY_IP="$LAN_IP" DNS_PORT=53 \
  "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 80 \
    --log-level warning &
PROXY_PID=$!

echo ""
echo "=============================="
echo " Heimdall is running!"
echo " Management UI : http://$LAN_IP:8080"
echo " HTTP proxy    : http://$LAN_IP:80"
echo " DNS server    : $LAN_IP:53 (UDP)"
echo "=============================="
echo " Point your router DNS Server 1 to: $LAN_IP"
echo " Then visit http://<yourdevice>.local from any LAN device."
echo ""
echo " Press Ctrl+C to stop."

wait $MGMT_PID $PROXY_PID
