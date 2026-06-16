"""
models.py — Modelos SQLAlchemy

Tabela principal: measurements
Armazena leituras de sensores industriais (temperatura, pressão, etc).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Measurement(Base):
    __tablename__ = "measurements"

    # ── Identificação ──────────────────────────────────────────────────────
    id          = Column(Integer, primary_key=True, autoincrement=True)
    asset_id    = Column(String(50), nullable=False, index=True)   # ex: "MD01BR01"
    sensor_id   = Column(String(50), nullable=True,  index=True)   # ex: "TEMP_01"
    sensor_type = Column(String(50), nullable=True)                # ex: "temperature"

    # ── Leituras ───────────────────────────────────────────────────────────
    value       = Column(Float,   nullable=True)   # valor principal da leitura
    temperature = Column(Float,   nullable=True)   # °C
    pressure    = Column(Float,   nullable=True)   # bar / kPa
    humidity    = Column(Float,   nullable=True)   # %
    vibration   = Column(Float,   nullable=True)   # mm/s
    current     = Column(Float,   nullable=True)   # A
    voltage     = Column(Float,   nullable=True)   # V
    flow        = Column(Float,   nullable=True)   # m³/h

    # ── Unidade e status ───────────────────────────────────────────────────
    unit        = Column(String(20), nullable=True)   # ex: "°C", "bar", "%"
    status      = Column(String(20), nullable=True)   # ex: "ok", "alarm", "fault"
    is_alarm    = Column(Boolean, default=False, nullable=False)

    # ── Timestamp ──────────────────────────────────────────────────────────
    timestamp   = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── Índices compostos para queries frequentes ──────────────────────────
    __table_args__ = (
        Index("ix_asset_timestamp", "asset_id", "timestamp"),
        Index("ix_asset_sensor",    "asset_id", "sensor_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Measurement id={self.id} asset={self.asset_id} "
            f"sensor={self.sensor_id} value={self.value} ts={self.timestamp}>"
        )