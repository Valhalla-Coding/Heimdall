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

# ── 5. Grant Python permission to bind ports 53 and 80 (one-time) ────────────
PYTHON_BIN="$(realpath "$VENV/bin/python3")"
if ! getcap "$PYTHON_BIN" 2>/dev/null | grep -q "cap_net_bind_service"; then
  echo "→ Granting low-port (53, 80) permission to Python (one-time, needs sudo)..."
  sudo apt-get install -y -qq libcap2-bin 2>/dev/null || true
  sudo setcap 'cap_net_bind_service=+ep' "$PYTHON_BIN"
  echo "→ Done — won't need sudo again."
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
    print('127.0.0.1')
")

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         Reverse Proxy Manager            ║"
echo "  ║                                          ║"
echo "  ║  Setup  →  http://localhost:8080         ║"
echo "  ║  HTTP   →  http://${LAN_IP}            ║"
echo "  ║  DNS    →  ${LAN_IP}:53              ║"
echo "  ║                                          ║"
echo "  ║  1. Open http://localhost:8080           ║"
echo "  ║  2. Click '+ Add My Device'              ║"
echo "  ║  3. Set router DNS to ${LAN_IP}        ║"
echo "  ║  4. Visit {name}.local from any device   ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

export PROXY_IP="$LAN_IP"

# Port 80: public proxy (what *.local hits)
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 80 &
PID_80=$!

# Port 8080: management UI
"$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8080 --reload &
PID_8080=$!

trap "kill $PID_80 $PID_8080 2>/dev/null" EXIT INT TERM
wait $PID_80 $PID_8080
