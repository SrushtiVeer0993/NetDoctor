from fastapi import APIRouter, Depends
import ipaddress
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_or_create_settings
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitoring_interval_seconds: int | None = Field(default=None, ge=1, le=3600)
    default_ping_target: str | None = Field(default=None, min_length=1, max_length=253)
    default_dns_domain: str | None = Field(default=None, min_length=1, max_length=253)
    demo_mode: bool | None = None
    latency_alert_ms: float | None = Field(default=None, ge=0.1, le=10000, allow_inf_nan=False)
    packet_loss_alert_pct: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    alert_consecutive_checks: int | None = Field(default=None, ge=1, le=100)

    @field_validator("default_ping_target", "default_dns_domain")
    @classmethod
    def validate_network_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Target cannot be blank.")
        candidate = value.rstrip(".")
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            labels = candidate.split(".")
            if len(candidate) > 253 or any(
                not label or len(label) > 63
                or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is None
                for label in labels
            ):
                raise ValueError("Enter a valid IP address or hostname, without a URL or path.")
            return candidate


def _serialize(row):
    return {
        "monitoring_interval_seconds": row.monitoring_interval_seconds,
        "default_ping_target": row.default_ping_target,
        "default_dns_domain": row.default_dns_domain,
        "demo_mode": row.demo_mode,
        "latency_alert_ms": row.latency_alert_ms,
        "packet_loss_alert_pct": row.packet_loss_alert_pct,
        "alert_consecutive_checks": row.alert_consecutive_checks,
    }


@router.get("")
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _serialize(get_or_create_settings(db, user))


@router.put("")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = get_or_create_settings(db, user)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _serialize(row)
