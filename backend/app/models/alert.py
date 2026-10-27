from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertRule(Base):
    """User-configured alert threshold (spec section 17)."""
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    metric: Mapped[str] = mapped_column(String(30), nullable=False)  # latency_ms | packet_loss_pct | dns_failure | internet_down
    operator: Mapped[str] = mapped_column(String(5), default=">")
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    consecutive_required: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertEvent(Base):
    """A fired alert, produced once a rule's consecutive-failure threshold is met."""
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id"), nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
