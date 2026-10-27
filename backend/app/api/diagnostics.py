from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, resolve_demo_mode
from app.db.session import get_db
from app.models.diagnostic import DiagnosticRun
from app.models.user import User
from app.schemas.diagnostics import DiagnosisRequest, DiagnosisResult, DiagnosisSummary
from app.services import demo_data
from app.services import host_agent
from app.services import legacy_diagnostics as engine
from app.services.host_agent import HostAgentError

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _persist(db: Session, user: User, result: dict) -> DiagnosticRun:
    top_finding = result["findings"][0]["text"] if result.get("findings") else None
    packet_loss = result.get("packet_loss") or {}
    run = DiagnosticRun(
        user_id=user.id,
        health_score=result["health_score"],
        gateway_reachable=result["gateway"].get("reachable"),
        internet_reachable=result["internet"].get("reachable"),
        latency_avg_ms=result["latency"].get("avg_ms"),
        packet_loss_pct=None if packet_loss.get("icmp_unavailable") else packet_loss.get("loss_pct"),
        dns_response_ms=result["dns"].get("response_ms"),
        top_finding=top_finding,
        result_json=result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post("/full", response_model=DiagnosisResult)
def run_full_diagnosis(
    payload: DiagnosisRequest,
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if resolve_demo_mode(demo, db, user):
        result = demo_data.demo_full_diagnosis(
            external_host=payload.external_host,
            dns_domain=payload.dns_domain,
            websites=payload.websites,
            discover_devices=payload.discover_devices,
        )
    else:
        try:
            host_result = host_agent.run_diagnostics(
                external_host=payload.external_host,
                dns_domain=payload.dns_domain,
                websites=payload.websites,
                discover_devices=payload.discover_devices,
            )
        except HostAgentError as exc:
            result = engine.run_full_diagnosis(
                external_host=payload.external_host,
                dns_domain=payload.dns_domain,
                websites=payload.websites,
                discover_devices=(
                    payload.discover_devices and not host_agent.is_running_in_docker()
                ),
            )
            result["host_agent"] = {"available": False, "detail": str(exc)}
            if payload.discover_devices and host_agent.is_running_in_docker():
                result["devices"] = {
                    "supported": None,
                    "status": "skipped",
                    "devices": [],
                    "detail": (
                        "Windows host discovery was not run because the host agent is "
                        f"unavailable: {exc}"
                    ),
                    "source": result["source"],
                }
        else:
            result = engine.build_diagnosis(
                gateway=host_result.gateway.model_dump(),
                internet=host_result.internet.model_dump(),
                latency=host_result.latency.model_dump(),
                packet_loss=host_result.packet_loss.model_dump(),
                dns=host_result.dns.model_dump(),
                websites=[site.model_dump() for site in host_result.websites],
                devices=host_result.devices.model_dump(),
                source="windows_host",
                host_agent={"available": True, "detail": None},
            )
        result.setdefault("source", engine.measurement_source())
        result["simulated"] = False
        if not payload.discover_devices and result["devices"].get("status") != "skipped":
            result["devices"] = {
                "status": "skipped",
                "supported": None,
                "devices": [],
                "detail": "Device discovery was not requested.",
                "source": result["source"],
            }
    run = _persist(db, user, result)
    return DiagnosisResult(
        id=run.id, created_at=run.created_at, health_score=run.health_score,
        gateway_reachable=run.gateway_reachable, internet_reachable=run.internet_reachable,
        latency_avg_ms=run.latency_avg_ms,
        packet_loss_pct=(
            None if (run.result_json.get("packet_loss") or {}).get("icmp_unavailable")
            else run.packet_loss_pct
        ),
        dns_response_ms=run.dns_response_ms, top_finding=run.top_finding,
        result_json=run.result_json,
    )


@router.post("/ping", response_model=dict)
def ping_only(
    payload: DiagnosisRequest,
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Lightweight endpoint (no persistence) for quick checks / live-monitor polling
    # in later phases — kept separate from /full so it stays cheap.
    if resolve_demo_mode(demo, db, user):
        simulated = demo_data.demo_full_diagnosis(
            external_host=payload.external_host, dns_domain=payload.dns_domain
        )
        return {
            "latency": simulated["latency"],
            "packet_loss": simulated["packet_loss"],
            "simulated": True,
        }
    return {
        "latency": engine.measure_latency(payload.external_host),
        "packet_loss": engine.measure_packet_loss(payload.external_host),
        "simulated": False,
        "source": engine.measurement_source(),
    }


@router.get("/history", response_model=list[DiagnosisSummary])
def history(
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs = (
        db.query(DiagnosticRun)
        .filter(DiagnosticRun.user_id == user.id)
        .order_by(DiagnosticRun.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(runs))


@router.get("/history/{run_id}", response_model=DiagnosisResult)
def history_detail(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from fastapi import HTTPException

    run = (
        db.query(DiagnosticRun)
        .filter(DiagnosticRun.id == run_id, DiagnosticRun.user_id == user.id)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Diagnostic run not found")
    return DiagnosisResult(
        id=run.id, created_at=run.created_at, health_score=run.health_score,
        gateway_reachable=run.gateway_reachable, internet_reachable=run.internet_reachable,
        latency_avg_ms=run.latency_avg_ms,
        packet_loss_pct=(
            None if (run.result_json.get("packet_loss") or {}).get("icmp_unavailable")
            else run.packet_loss_pct
        ),
        dns_response_ms=run.dns_response_ms, top_finding=run.top_finding,
        result_json=run.result_json,
    )
