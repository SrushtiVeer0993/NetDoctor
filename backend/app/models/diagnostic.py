"""
Phase-1 persistence model for a full diagnostic run.
Mirrors the JSON shape produced by app.services.legacy_diagnostics.run_full_diagnosis,
plus a handful of flattened columns for cheap trend queries (history/analytics phases).
Packet captures, traceroute hops, monitoring sessions etc. are added in later phases
without needing to change this table.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DiagnosticRun(Base):
    __tablename__ = "diagnostic_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    health_score: Mapped[int] = mapped_column(Integer, nullable=False)
    gateway_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    internet_reachable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_avg_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dns_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_finding: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Full structured result (gateway/internet/latency/packet_loss/dns/websites/
    # devices/findings/recommendations) — kept as JSON so later phases (analytics,
    # anomaly detection, reports) can read it back without a schema migration.
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    user = relationship("User", back_populates="diagnostic_runs")
