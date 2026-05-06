"""
REST API routes for managing devices and proxy routes.
"""

import socket
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, Device, Route

router = APIRouter(prefix="/api")


# -- Pydantic schemas ---------------------------------------------------------

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
    hostname: str
    target: str
    label: Optional[str] = None
    device_id: Optional[int] = None
    enabled: bool = True


class RouteUpdate(BaseModel):
    hostname: Optional[str] = None
    target: Optional[str] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None
    device_id: Optional[int] = None


# -- Device endpoints ---------------------------------------------------------

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


# -- Route endpoints ----------------------------------------------------------

@router.get("/routes", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.hostname).all()


@router.post("/routes", response_model=RouteOut, status_code=201)
def create_route(body: RouteCreate, db: Session = Depends(get_db)):
    existing = db.query(Route).filter(Route.hostname == body.hostname).first()
    if existing:
        raise HTTPException(status_code=409, detail="A route for this hostname already exists.")
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


# -- Self-registration ("Add My Device") -------------------------------------

def _get_lan_ip() -> str:
    """Detect this machine's LAN IP via a UDP connect trick (no packets sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class SelfRegister(BaseModel):
    hostname: str
    label: Optional[str] = None


@router.get("/self-info")
def self_info():
    """Return detected hostname + IP so the UI can pre-fill the form."""
    raw = socket.gethostname().lower().replace(" ", "-")
    short = raw.split(".")[0]
    return {"hostname": short, "ip": _get_lan_ip()}


@router.post("/devices/self", response_model=DeviceOut, status_code=201)
def register_self(body: SelfRegister, db: Session = Depends(get_db)):
    """
    One-click self-registration: detects this machine's IP, creates a Device
    record, and adds hostname.local + www.hostname.local routes automatically.
    """
    ip = _get_lan_ip()
    hostname = body.hostname.lower().strip()
    label = body.label or hostname.capitalize()

    # Upsert device
    device = db.query(Device).filter(Device.ip == ip).first()
    if not device:
        device = Device(ip=ip, hostname=hostname, label=label,
                        last_seen=datetime.now(timezone.utc))
        db.add(device)
        db.commit()
        db.refresh(device)
    else:
        device.hostname = hostname
        device.label = label
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(device)

    # Create hostname.local route (landing page) if missing
    root = f"{hostname}.local"
    if not db.query(Route).filter(Route.hostname == root).first():
        db.add(Route(hostname=root, target=f"{ip}:8080",
                     label=f"{label} — Home", device_id=device.id,
                     subdomain=hostname, enabled=True))

    # Create www.hostname.local route if missing
    www = f"www.{hostname}.local"
    if not db.query(Route).filter(Route.hostname == www).first():
        db.add(Route(hostname=www, target=f"{ip}:8080",
                     label=f"{label} — www", device_id=device.id,
                     subdomain="www", enabled=True))

    db.commit()
    db.refresh(device)
    return device
