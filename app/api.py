"""
REST API routes for managing devices and proxy routes.
"""

import os
import socket
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, Device, Route

router = APIRouter(prefix="/api")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DeviceOut(BaseModel):
    id: int
    ip: str
    hostname: str
    label: Optional[str]
    last_seen: datetime
    active: bool

    class Config:
        from_attributes = True


class DeviceCreate(BaseModel):
    ip: str
    hostname: str
    label: Optional[str] = None


class DeviceUpdate(BaseModel):
    hostname: Optional[str] = None
    label: Optional[str] = None
    active: Optional[bool] = None


class RouteOut(BaseModel):
    id: int
    hostname: str
    label: Optional[str]
    target: str
    device_id: Optional[int]
    subdomain: Optional[str]
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RouteCreate(BaseModel):
    hostname: str           # e.g. "ai_image.oden"
    target: str             # e.g. "192.168.1.10:7860"
    label: Optional[str] = None
    device_id: Optional[int] = None
    enabled: bool = True


class RouteUpdate(BaseModel):
    hostname: Optional[str] = None
    target: Optional[str] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None
    device_id: Optional[int] = None


# ── Device endpoints ──────────────────────────────────────────────────────────

@router.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return db.query(Device).order_by(Device.hostname).all()


@router.post("/devices", response_model=DeviceOut, status_code=201)
def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    existing = db.query(Device).filter(Device.ip == body.ip).first()
    if existing:
        raise HTTPException(status_code=409, detail="A device with this IP already exists.")
    device = Device(
        ip=body.ip,
        hostname=body.hostname,
        label=body.label,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(device, field, value)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    db.delete(device)
    db.commit()


# ── Route endpoints ───────────────────────────────────────────────────────────

@router.get("/routes", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.hostname).all()


@router.post("/routes", response_model=RouteOut, status_code=201)
def create_route(body: RouteCreate, db: Session = Depends(get_db)):
    existing = db.query(Route).filter(Route.hostname == body.hostname).first()
    if existing:
        raise HTTPException(status_code=409, detail="A route for this hostname already exists.")
    # Derive subdomain (everything before the first dot)
    subdomain = body.hostname.split(".")[0] if "." in body.hostname else None
    route = Route(
        hostname=body.hostname,
        target=body.target,
        label=body.label,
        device_id=body.device_id,
        subdomain=subdomain,
        enabled=body.enabled,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.put("/routes/{route_id}", response_model=RouteOut)
def update_route(route_id: int, body: RouteUpdate, db: Session = Depends(get_db)):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(route, field, value)
    if body.hostname:
        route.subdomain = body.hostname.split(".")[0] if "." in body.hostname else None
    db.commit()
    db.refresh(route)
    return route


@router.delete("/routes/{route_id}", status_code=204)
def delete_route(route_id: int, db: Session = Depends(get_db)):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")
    db.delete(route)
    db.commit()


# ── "Add My Device" ───────────────────────────────────────────────────────────

class SelfDeviceRequest(BaseModel):
    hostname: Optional[str] = None   # override; defaults to system hostname
    label: Optional[str] = None


@router.post("/devices/self", status_code=201)
def register_self(body: SelfDeviceRequest, db: Session = Depends(get_db)):
    """
    Register the machine running the proxy as a device.
    Auto-detects hostname and LAN IP.
    Creates a *.local DNS route and a landing-page route automatically.
    """
    # Detect hostname
    hostname = (body.hostname or socket.gethostname()).lower()
    local_hostname = f"{hostname}.local"

    # Detect LAN IP (connect to a public address to find the outbound interface)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "127.0.0.1"

    # Create or update the device record
    device = db.query(Device).filter(Device.ip == lan_ip).first()
    if not device:
        device = Device(
            ip=lan_ip,
            hostname=hostname,
            label=body.label or hostname.capitalize(),
            last_seen=datetime.now(timezone.utc),
            active=True,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
    else:
        device.hostname = hostname
        device.label = body.label or device.label or hostname.capitalize()
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(device)

    created_routes = []

    # Route: hostname.local → management UI (port 8080)
    mgmt_hostname = local_hostname
    if not db.query(Route).filter(Route.hostname == mgmt_hostname).first():
        route = Route(
            hostname=mgmt_hostname,
            target=f"{lan_ip}:8080",
            label=f"{hostname.capitalize()} (management)",
            device_id=device.id,
            subdomain=hostname,
            enabled=True,
        )
        db.add(route)
        created_routes.append(mgmt_hostname)

    # Route: www.hostname.local → landing page (same proxy, /web/ path)
    www_hostname = f"www.{local_hostname}"
    if not db.query(Route).filter(Route.hostname == www_hostname).first():
        route = Route(
            hostname=www_hostname,
            target=f"{lan_ip}:8080",
            label=f"{hostname.capitalize()} (landing page)",
            device_id=device.id,
            subdomain="www",
            enabled=True,
        )
        db.add(route)
        created_routes.append(www_hostname)

    db.commit()

    return {
        "device": {
            "id": device.id,
            "hostname": device.hostname,
            "local_hostname": local_hostname,
            "ip": device.ip,
            "label": device.label,
        },
        "routes_created": created_routes,
        "message": (
            f"Registered as {local_hostname} → {lan_ip}. "
            f"Make sure your router DNS points to {lan_ip} so other devices resolve it."
        ),
    }


# ── Self info (for UI pre-fill) ───────────────────────────────────────────────

@router.get("/self-info")
def self_info():
    """Returns the detected hostname and LAN IP of this machine."""
    hostname = socket.gethostname().lower()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "127.0.0.1"
    return {"hostname": hostname, "ip": lan_ip, "local_hostname": f"{hostname}.local"}


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok"}
