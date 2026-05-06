"""
Entry point for the Reverse Proxy server.

Starts:
  - FastAPI app on port 8080  (web UI + REST API + HTTP proxy)
  - DNS server on port 5353   (UDP, no root required)
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .database import init_db
from .api import router as api_router
from .proxy import ReverseProxyMiddleware
from .dns_server import start_dns_server

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise the database
    init_db()

    # Start the DNS server in a background thread
    dns_thread = threading.Thread(target=start_dns_server, daemon=True)
    dns_thread.start()

    yield  # app is running

    # Nothing to clean up — DNS thread is a daemon and will die with the process


app = FastAPI(
    title="Reverse Proxy Manager",
    description="Web UI + HTTP reverse proxy + DNS server",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(ReverseProxyMiddleware)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(api_router)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Serve the SPA for all non-API routes ─────────────────────────────────────
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_ui(full_path: str):
    index = TEMPLATES_DIR / "index.html"
    return FileResponse(str(index))
