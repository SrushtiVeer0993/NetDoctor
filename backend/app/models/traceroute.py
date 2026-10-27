from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TracerouteRun(Base):
    __tablename__ = "traceroute_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    target: Mapped[str] = mapped_column(String(255), nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, default=True)

    hops = relationship("TracerouteHop", back_populates="run", cascade="all, delete-orphan", order_by="TracerouteHop.hop_number")


class TracerouteHop(Base):
    __tablename__ = "traceroute_hops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("traceroute_runs.id"), nullable=False, index=True)

    hop_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="no_response")

    run = relationship("TracerouteRun", back_populates="hops")
