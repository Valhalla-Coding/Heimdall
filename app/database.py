"""
Database setup — SQLite via SQLAlchemy (sync core, simple & dependency-free).
The data.db file is created next to wherever you run the server from.
"""

from pathlib import Path
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone

DB_PATH = Path.cwd() / "data.db"
ENGINE = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


class Base(DeclarativeBase):
    pass


class Device(Base):
    """
    A device that has been seen on the network.
    Populated automatically when a proxied request arrives from a known hostname,
    or manually via the UI.
    """
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, unique=True, nullable=False, index=True)
    hostname = Column(String, nullable=False)          # e.g. "oden"
    label = Column(String, nullable=True)               # friendly override label
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    active = Column(Boolean, default=True)


class Route(Base):
    """
    A proxy route: custom_hostname → target ip:port.
    Example: ai_image.oden → 192.168.1.10:7860
    """
    __tablename__ = "routes"
    __table_args__ = (UniqueConstraint("subdomain", "device_id", name="uq_subdomain_device"),)

    id = Column(Integer, primary_key=True, index=True)
    # The full custom hostname, e.g. "ai_image.oden"
    hostname = Column(String, unique=True, nullable=False, index=True)
    # Friendly name shown in the UI
    label = Column(String, nullable=True)
    # Target to proxy to, e.g. "192.168.1.10:7860"
    target = Column(String, nullable=False)
    # Optional: which device_id this belongs to (for UI grouping)
    device_id = Column(Integer, nullable=True)
    subdomain = Column(String, nullable=True)   # "ai_image" portion
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=ENGINE)


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
