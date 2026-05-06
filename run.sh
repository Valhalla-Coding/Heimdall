#!/usr/bin/env bash
# ── Reverse Proxy — start script ─────────────────────────────────────────────
set -e

VENV=".venv"

# ── 1. Ensure Python + venv are installed ────────────────────────────────────
if ! python3 -m venv --help &>/dev/null 2>&1; then
  echo "→ Installing python3-venv..."
  sudo apt-get update -qq && sudo apt-get install -y python3-venv python3-full
fi

# ── 2. Create venv if missing ─────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# ── 3. Activate ───────────────────────────────────────────────────────────────
source "$VENV/bin/activate"

# ── 4. Install / upgrade deps ─────────────────────────────────────────────────
echo "→ Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── 5. Install socat (forwards port 53 → 5353, no root needed at runtime) ────
if ! command -v socat &>/dev/null; then
  echo "→ Installing socat (one-time)..."
  sudo apt-get install -y -qq socat
fi

# ── 6. Detect LAN IP ─────────────────────────────────────────────────────────
LAN_IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
    s.close()
except:
    print('192.168.1.10')
")

# ── 7. Grant Python permission to bind port 80 (one-time) ────────────────────
PYTHON_BIN="$(realpath "$VENV/bin/python3")"
if ! getcap "$PYTHON_BIN" 2>/dev/null | grep -q "cap_net_bind_service"; then
  echo "→ Granting port 80 permission to Python (one-time, needs sudo)..."
  sudo apt-get install -y -qq libcap2-bin 2>/dev/null || true
  sudo setcap 'cap_net_bind_service=+ep' "$PYTHON_BIN"
fi

# ── 8. Forward port 53 → 5353 via socat (needs sudo for port 53 bind) ────────
# Kill any old socat forwarders first
pkill -f "socat.*UDP.*53" 2>/dev/null || true
echo "→ Starting DNS forwarder 53 → 5353 (needs sudo for port 53)..."
sudo socat UDP4-RECVFROM:53,fork UDP4-SENDTO:127.0.0.1:5353 &
SOCAT_PID=$!

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         Reverse Proxy Manager            ║"
echo "  ║  UI   →  http://localhost:8080           ║"
echo "  ║  HTTP →  http://${LAN_IP} (port 80)  ║"
echo "  ║  DNS  →  ${LAN_IP}:53                ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

export PROXY_IP="$LAN_IP"

# Port 80: public-facing proxy
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 80 &
PID_80=$!

# Port 8080: management UI with hot-reload
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8080 --reload &
PID_8080=$!

trap "kill $PID_80 $PID_8080 $SOCAT_PID 2>/dev/null; sudo pkill -f 'socat.*UDP.*53' 2>/dev/null" EXIT INT TERM
wait $PID_80 $PID_8080
