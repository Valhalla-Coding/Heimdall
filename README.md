# Reverse Proxy Manager

A self-hosted HTTP reverse proxy with a dark web UI, SQLite-backed route storage, and a built-in DNS server — so custom hostnames like `ai_image.oden` just work.

## Quick start (WSL / Ubuntu)

```bash
bash run.sh
```

Open **http://localhost:8080** in your browser.

## Components

| Component | Port | Description |
|-----------|------|-------------|
| Web UI + REST API | **8080** | Manage devices & routes |
| HTTP Proxy | **8080** | Reverse-proxies requests by Host header |
| DNS Server | **5353 UDP** | Resolves custom hostnames → 127.0.0.1 |

## Setting up the `ai_image.oden` example

1. **Add a Device** — go to Devices → Add Device:
   - IP: `192.168.1.10` (your PC's LAN IP — `ip addr` to find it)
   - Hostname: `oden`

2. **Add a Route** — go to Routes → Add Route:
   - Custom Hostname: `ai_image.oden`
   - Target: `192.168.1.10:7860`
   - Device: oden
   - Label: `AI Image Gen`

3. **Point your DNS at the proxy**:

   ```bash
   # WSL2 / Ubuntu — per-interface (replace eth0 with your interface)
   resolvectl dns eth0 127.0.0.1
   resolvectl domain eth0 ~.

   # Or add to /etc/hosts for quick testing (no DNS needed):
   echo "127.0.0.1  ai_image.oden" | sudo tee -a /etc/hosts
   ```

   On **Windows** (to use from the host), add to `C:\Windows\System32\drivers\etc\hosts`:
   ```
   127.0.0.1  ai_image.oden
   ```

4. Visit `http://ai_image.oden` — the proxy forwards it to `192.168.1.10:7860`.

## DNS note

The DNS server runs on port **5353** (no root required). If you want it on port 53 for full system-wide resolution:

```bash
# Linux — redirect 53 → 5353 (run once, doesn't persist)
sudo iptables -t nat -A OUTPUT -p udp --dport 53 -j REDIRECT --to-port 5353
sudo iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-port 5353
```

## File layout

```
.
├── app/
│   ├── main.py        # FastAPI app + startup
│   ├── api.py         # REST endpoints
│   ├── database.py    # SQLAlchemy models (SQLite)
│   ├── proxy.py       # HTTP reverse-proxy middleware
│   └── dns_server.py  # Built-in DNS server (dnslib)
├── static/
│   ├── css/style.css
│   └── js/app.js
├── templates/
│   └── index.html
├── requirements.txt
├── run.sh
└── data.db            # Created automatically (gitignored)
```

## Future / Autorun integration

When moving to Ubuntu server with [Autorun](https://github.com/Valhalla-Coding/Autorun), point it at `run.sh` or set up a systemd service:

```ini
[Unit]
Description=Reverse Proxy Manager
After=network.target

[Service]
WorkingDirectory=/opt/reverse-proxy
ExecStart=/opt/reverse-proxy/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```
