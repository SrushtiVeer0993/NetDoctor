from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    target: Mapped[str] = mapped_column(String(255), default="8.8.8.8")
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown", server_default="unknown")

    measurements = relationship("MonitoringMeasurement", back_populates="session", cascade="all, delete-orphan")


class MonitoringMeasurement(Base):
    __tablename__ = "monitoring_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("monitoring_sessions.id"), nullable=False, index=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dns_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    internet_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    session = relationship("MonitoringSession", back_populates="measurements")
