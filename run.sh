#!/usr/bin/env bash
# ── Heimdall — start script ───────────────────────────────────────────────────
set -e

VENV=".venv"

# ── 1. Ensure Python + venv are installed ────────────────────────────────────
if ! dpkg -s python3-venv &>/dev/null 2>&1; then
  echo "→ Installing Python (one-time, needs sudo)..."
  sudo apt-get update -qq
  sudo apt-get install -y python3 python3-venv python3-pip libcap2-bin
fi

# ── 2. Create venv if missing ─────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# ── 3. Activate ──────────────────────