from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)

    monitoring_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    default_ping_target: Mapped[str] = mapped_column(String(255), default="8.8.8.8")
    default_dns_domain: Mapped[str] = mapped_column(String(255), default="google.com")
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=False)

    latency_alert_ms: Mapped[float] = mapped_column(Float, default=150.0)
    packet_loss_alert_pct: Mapped[float] = mapped_column(Float, default=5.0)
    alert_consecutive_checks: Mapped[int] = mapped_column(Integer, default=3)
