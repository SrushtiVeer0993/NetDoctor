"""
Live monitoring (spec section 16) — REST for session start/stop/history,
WebSocket for the streamed measurements themselves.

Browsers can't attach custom headers to a WebSocket handshake, so the JWT
is passed as a query parameter on the /ws/monitor connection instead of
the Authorization header the REST endpoints use.
"""
import asyncio
import ipaddress
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_or_create_settings, resolve_demo_mode
from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal, get_db
from app.models.monitoring import MonitoringMeasurement, MonitoringSession
from app.models.user import User
from app.services import legacy_diagnostics as engine
from app.services import demo_data
from app.services import host_agent
from app.services.host_agent import HostAgentError
from app.services.alerts import ConsecutiveTracker, evaluate_measurement
from app.models.alert import AlertEvent

router = APIRouter(tags=["monitoring"])

_MAX_CONCURRENT_MEASUREMENTS = 4
_MEASUREMENT_SLOTS = BoundedSemaphore(_MAX_CONCURRENT_MEASUREMENTS)
_MEASUREMENT_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT_MEASUREMENTS,
    thread_name_prefix="monitoring",
)
_STOP_CHECK_INTERVAL_SECONDS = 1


def _measure_target(target: str, use_host_agent: bool):
    if use_host_agent:
        result = host_agent.run_monitor_measurement(target)
        return result.model_dump()

    # Derive latency and loss from one sample set, rather than separate ping runs.
    ping = engine._ping_with_status(target, count=3, timeout_ms=800)
    samples = engine._parse_ping_times(ping["output"])
    sent = 3 if ping["output"] is not None else 0
    received = min(len(samples), sent)
    latency = round(sum(samples) / len(samples), 1) if samples else None
    loss = round((sent - received) / sent * 100, 1) if sent and received > 0 else None
    dns = engine.measure_dns_response_time()
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=2):
            internet = True
    except OSError:
        # One failed TCP probe is inconclusive; don't call the internet down.
        internet = None
    return {
        "source": engine.measurement_source(),
        "target": target,
        "latency_ms": latency,
        "packet_loss_pct": loss,
        "sent": sent,
        "received": received,
        "icmp_unavailable": received == 0,
        "dns_ms": dns["response_ms"],
        "dns_success": dns["success"],
        "internet": internet,
    }


async def _measure_target_async(
    target: str, use_host_agent: bool, db: Session, session_id: int
):
    while not _MEASUREMENT_SLOTS.acquire(blocking=False):
        if not _session_is_active(db, session_id):
            return None
        await asyncio.sleep(0.05)

    try:
        future = _MEASUREMENT_EXECUTOR.submit(_measure_target, target, use_host_agent)
    except BaseException:
        _MEASUREMENT_SLOTS.release()
        raise

    future.add_done_callback(lambda _: _MEASUREMENT_SLOTS.release())
    wrapped = asyncio.wrap_future(future)
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout=1)
        except asyncio.TimeoutError:
            if not _session_is_active(db, session_id):
                return None


def _session_is_active(db: Session, session_id: int) -> bool:
    return (
        db.query(MonitoringSession.id)
        .filter(MonitoringSession.id == session_id, MonitoringSession.ended_at.is_(None))
        .first()
        is not None
    )


async def _wait_until_next_measurement(
    db: Session, session_id: int, deadline: float
) -> bool:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _session_is_active(db, session_id)
        await asyncio.sleep(min(remaining, _STOP_CHECK_INTERVAL_SECONDS))
        if not _session_is_active(db, session_id):
            return False


@router.post("/api/monitoring/start")
def start_session(
    interval_seconds: int | None = Query(default=None, ge=1, le=3600),
    target: str | None = Query(default=None, min_length=1, max_length=253),
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user_settings = get_or_create_settings(db, user)
    simulated = resolve_demo_mode(demo, db, user)
    interval_seconds = interval_seconds or user_settings.monitoring_interval_seconds
    target = target or user_settings.default_ping_target or "8.8.8.8"
    if not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
        r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
        target,
    ):
        try:
            ipaddress.ip_address(target)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Invalid monitoring target.") from None
    use_host_agent = bool(
        not simulated and host_agent.is_running_in_docker()
        and settings.HOST_AGENT_URL and settings.HOST_AGENT_TOKEN
    )
    source = "simulated" if simulated else (
        "windows_host" if use_host_agent else engine.measurement_source()
    )
    session = MonitoringSession(
        user_id=user.id, interval_seconds=interval_seconds, target=target,
        simulated=simulated,
        source=source,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id, "interval_seconds": interval_seconds,
        "target": target, "simulated": simulated, "source": source,
    }


@router.post("/api/monitoring/stop")
def stop_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(MonitoringSession).filter(
        MonitoringSession.id == session_id, MonitoringSession.user_id == user.id
    ).first()
    if session and session.ended_at is None:
        db.query(MonitoringSession).filter(
            MonitoringSession.id == session_id,
            MonitoringSession.user_id == user.id,
            MonitoringSession.ended_at.is_(None),
        ).update(
            {MonitoringSession.ended_at: datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
    return {"stopped": bool(session)}


@router.get("/api/monitoring/{session_id}/measurements")
def get_measurements(session_id: int, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.query(MonitoringSession).filter(
        MonitoringSession.id == session_id, MonitoringSession.user_id == user.id
    ).first()
    if not session:
        return {"measurements": []}
    rows = (
        db.query(MonitoringMeasurement)
        .filter(MonitoringMeasurement.session_id == session_id)
        .order_by(MonitoringMeasurement.id.desc())
        .limit(limit)
        .all()
    )
    return {"measurements": [
        {"timestamp": r.timestamp, "latency_ms": r.latency_ms, "packet_loss_pct": r.packet_loss_pct,
         "dns_ms": r.dns_ms, "internet_up": r.internet_up, "simulated": r.simulated,
         "source": session.source}
        for r in reversed(rows)
    ]}


@router.websocket("/ws/monitor")
async def monitor_ws(websocket: WebSocket, session_id: int = Query(...), token: str = Query(...)):
    email = decode_access_token(token)
    if not email:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    session = None
    try:
        user = db.query(User).filter(User.email == email).first()
        session = db.query(MonitoringSession).filter(
            MonitoringSession.id == session_id, MonitoringSession.user_id == user.id
        ).first() if user else None
        if not user or not session:
            await websocket.close(code=4404)
            return

        await websocket.accept()
        user_settings = get_or_create_settings(db, user)
        tracker = ConsecutiveTracker()
        next_measurement_at = time.monotonic()

        while _session_is_active(db, session.id):
            if session.simulated:
                simulated = demo_data.demo_monitor_measurement()
                latency = {"avg_ms": simulated["latency_ms"], "received": 1 if simulated["internet_up"] else 0}
                loss = {"loss_pct": simulated["packet_loss_pct"]}
                dns = {"response_ms": simulated["dns_ms"], "success": True}
                internet_result = {"reachable": simulated["internet_up"]}
            else:
                try:
                    measurement_data = await _measure_target_async(
                        session.target,
                        use_host_agent=(
                            host_agent.is_running_in_docker()
                            and session.source == "windows_host"
                        ),
                        db=db,
                        session_id=session.id,
                    )
                except HostAgentError as exc:
                    await websocket.send_json({"error": str(exc), "source": session.source})
                    break
                if measurement_data is None:
                    break
                latency = {"avg_ms": measurement_data["latency_ms"]}
                loss = {
                    "loss_pct": measurement_data["packet_loss_pct"],
                    "icmp_unavailable": measurement_data["icmp_unavailable"],
                }
                dns = {
                    "response_ms": measurement_data["dns_ms"],
                    "success": measurement_data["dns_success"],
                }
                internet_result = {"reachable": measurement_data["internet"]}
            if not _session_is_active(db, session.id):
                break
            internet = internet_result["reachable"]
            measured_loss = None if loss.get("icmp_unavailable") else loss["loss_pct"]

            measurement = MonitoringMeasurement(
                session_id=session.id,
                latency_ms=latency["avg_ms"],
                packet_loss_pct=measured_loss,
                dns_ms=dns["response_ms"],
                internet_up=internet,
                simulated=session.simulated,
            )
            db.add(measurement)
            db.commit()

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency["avg_ms"],
                "packet_loss": measured_loss,
                "icmp_unavailable": bool(loss.get("icmp_unavailable")),
                "dns_ms": dns["response_ms"],
                "dns_success": dns["success"],
                "internet": internet,
                "simulated": session.simulated,
                "source": session.source,
            }

            fired = [] if session.simulated else evaluate_measurement(
                {"latency_ms": latency["avg_ms"], "packet_loss_pct": measured_loss,
                 "dns_success": dns["success"], "internet_up": internet},
                user_settings, tracker,
            )
            for alert in fired:
                event = AlertEvent(user_id=user.id, rule_id=None, metric=alert["metric"],
                                    current_value=alert["current_value"], baseline_value=alert["baseline_value"],
                                    message=alert["message"])
                db.add(event)
            if fired:
                db.commit()
                payload["alerts"] = fired

            await websocket.send_json(payload)
            next_measurement_at += session.interval_seconds
            if next_measurement_at < time.monotonic():
                next_measurement_at = time.monotonic()
            if not await _wait_until_next_measurement(db, session.id, next_measurement_at):
                break
        await websocket.close()
    except WebSocketDisconnect:
        pass
    finally:
        try:
            if session:
                db.query(MonitoringSession).filter(
                    MonitoringSession.id == session.id,
                    MonitoringSession.ended_at.is_(None),
                ).update(
                    {MonitoringSession.ended_at: datetime.now(timezone.utc)},
                    synchronize_session=False,
                )
                db.commit()
        finally:
            db.close()
