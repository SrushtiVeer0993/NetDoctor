from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, resolve_demo_mode
from app.core.config import settings
from app.db.session import get_db
from app.models.speedtest import SpeedTestRun
from app.models.user import User
from app.schemas.network import SpeedTestRequest
from app.services.legacy_diagnostics import measurement_source
from app.services import demo_data, host_agent, speedtest as engine
from app.services.host_agent import HostAgentError

router = APIRouter(prefix="/api/speedtest", tags=["speedtest"])


@router.post("")
def run_speed_test(
    payload: SpeedTestRequest,
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if resolve_demo_mode(demo, db, user):
        result = demo_data.demo_speed_test()
    else:
        if host_agent.is_running_in_docker() and settings.HOST_AGENT_TOKEN:
            try:
                result = host_agent.run_speed_test(
                    payload.download_bytes, payload.upload_bytes,
                ).model_dump()
            except HostAgentError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Windows host speed test is unavailable: {exc}",
                ) from exc
        else:
            result = engine.run_speed_test(payload.download_bytes, payload.upload_bytes)
            result["source"] = measurement_source()
        result["simulated"] = False

    if result.get("source"):
        source_label = {
            "windows_host": "Windows host",
            "docker_container": "Docker container (not the Windows host)",
            "backend_runtime": "backend runtime",
        }.get(result["source"], result["source"])
        result["methodology"] += f" Measurement source: {source_label}."

    run = SpeedTestRun(
        user_id=user.id,
        download_mbps=result["download"].get("mbps"),
        upload_mbps=result["upload"].get("mbps"),
        latency_ms=result.get("latency_ms"),
        jitter_ms=result.get("jitter_ms"),
        methodology=result["methodology"],
        simulated=result["simulated"],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    result["id"] = run.id
    result["created_at"] = run.created_at
    return result


@router.get("/history")
def speed_test_history(limit: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    runs = (
        db.query(SpeedTestRun)
        .filter(SpeedTestRun.user_id == user.id)
        .order_by(SpeedTestRun.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {"id": r.id, "created_at": r.created_at, "download_mbps": r.download_mbps, "upload_mbps": r.upload_mbps,
         "latency_ms": r.latency_ms, "jitter_ms": r.jitter_ms, "simulated": r.simulated}
        for r in reversed(runs)
    ]
