from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.diagnostic import DiagnosticRun
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    latest = (
        db.query(DiagnosticRun)
        .filter(DiagnosticRun.user_id == user.id)
        .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
        .first()
    )
    recent = (
        db.query(DiagnosticRun)
        .filter(DiagnosticRun.user_id == user.id)
        .order_by(DiagnosticRun.created_at.desc(), DiagnosticRun.id.desc())
        .limit(10)
        .all()
    )

    return {
        "has_data": latest is not None,
        "latest": None if latest is None else {
            "id": latest.id,
            "created_at": latest.created_at,
            "health_score": latest.health_score,
            "gateway_reachable": latest.gateway_reachable,
            "internet_reachable": latest.internet_reachable,
            "latency_avg_ms": latest.latency_avg_ms,
            "packet_loss_pct": (
                None if (latest.result_json.get("packet_loss") or {}).get("icmp_unavailable")
                else latest.packet_loss_pct
            ),
            "dns_response_ms": latest.dns_response_ms,
            "top_finding": latest.top_finding,
            "recommendations": latest.result_json.get("recommendations", []),
            "devices_discovered": len((latest.result_json.get("devices") or {}).get("devices", [])),
            "device_discovery_status": (latest.result_json.get("devices") or {}).get("status", "unknown"),
            "simulated": bool((latest.result_json or {}).get("simulated", False)),
            "source": (latest.result_json or {}).get("source"),
        },
        "recent_tests": [
            {
                "id": r.id, "created_at": r.created_at, "health_score": r.health_score,
                "latency_avg_ms": r.latency_avg_ms,
                "packet_loss_pct": (
                    None if (r.result_json.get("packet_loss") or {}).get("icmp_unavailable")
                    else r.packet_loss_pct
                ),
                "simulated": bool((r.result_json or {}).get("simulated", False)),
                "source": (r.result_json or {}).get("source"),
            }
            for r in reversed(recent)
        ],
    }
