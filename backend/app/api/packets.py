from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, resolve_demo_mode
from app.db.session import get_db
from app.models.user import User
from app.network import interface as net
from app.services import demo_data, packet_capture as engine
from app.services import host_agent

router = APIRouter(prefix="/api/packet-capture", tags=["packets"])


class StartCaptureRequest(BaseModel):
    interface: str | None = None
    duration_seconds: int = Field(default=30, ge=1, le=300)
    max_packets: int = Field(default=300, ge=1, le=5000)


@router.post("/start")
def start(payload: StartCaptureRequest, demo: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if resolve_demo_mode(demo, db, user):
        return {"supported": True, "simulated": True, "capture_id": "demo", "status": "running"}
    result = engine.start_capture(payload.interface, payload.duration_seconds, payload.max_packets, owner_id=user.id)
    result["simulated"] = False
    result["source"] = (
        "docker_container" if host_agent.is_running_in_docker()
        else "windows_host" if net.CURRENT_OS == "windows"
        else "backend_runtime"
    )
    return result


@router.post("/stop")
def stop(capture_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if capture_id == "demo":
        return {"stopped": True}
    return engine.stop_capture(capture_id, owner_id=user.id)


@router.get("/status/{capture_id}")
def status(capture_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if capture_id == "demo":
        demo = demo_data.demo_packets()
        return {"capture_id": "demo", "status": "stopped", "started_at": demo["packets"][0]["timestamp"],
                "total_packets": demo["total_packets"], "protocol_counts": demo["protocol_counts"], "interface": None}
    result = engine.get_status(capture_id, owner_id=user.id)
    return result or {"error": "capture not found"}


@router.get("/packets/{capture_id}")
def packets(capture_id: str, protocol: str = "ALL", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if capture_id == "demo":
        demo = demo_data.demo_packets()
        pkts = demo["packets"]
        if protocol != "ALL":
            pkts = [p for p in pkts if p["protocol"] == protocol]
        return {"packets": pkts}
    return {"packets": engine.get_packets(capture_id, protocol, owner_id=user.id)}
