from datetime import datetime, timezone
import ipaddress
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, resolve_demo_mode
from app.db.session import get_db
from app.models.device import NetworkDevice
from app.models.traceroute import TracerouteHop, TracerouteRun
from app.models.user import User
from app.network import interface as net
from app.schemas.network import DiscoverDevicesRequest, TracerouteRequest
from app.services import demo_data
from app.services import host_agent
from app.services.host_agent import HostAgentError
from app.services.legacy_diagnostics import discover_local_devices, measurement_source

router = APIRouter(prefix="/api/network", tags=["network"])
logger = logging.getLogger(__name__)


def _interface_summary():
    try:
        summary = host_agent.get_interface().model_dump()
        summary["simulated"] = False
        summary["host_agent"] = {"available": True, "detail": None}
        return summary
    except HostAgentError as exc:
        logger.info("Using backend interface data because Windows host agent is unavailable: %s", exc)
        summary = net.get_active_interface_summary()
        summary["source"] = measurement_source()
        summary["simulated"] = False
        summary["host_agent"] = {"available": False, "detail": str(exc)}
        return summary


@router.get("/interfaces")
def get_interfaces(demo: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if resolve_demo_mode(demo, db, user):
        return demo_data.demo_interface_summary()
    return _interface_summary()


@router.get("/gateway")
def get_gateway(demo: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if resolve_demo_mode(demo, db, user):
        return {"gateway": demo_data.demo_interface_summary()["gateway"], "simulated": True}
    summary = _interface_summary()
    return {
        "gateway": summary.get("gateway"),
        "gateway_ipv6": summary.get("gateway_ipv6"),
        "interface_name": summary.get("interface_name"),
        "source": summary.get("source"),
        "host_agent": summary.get("host_agent"),
        "simulated": False,
    }


@router.get("/connections")
def get_connections(demo: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if resolve_demo_mode(demo, db, user):
        return demo_data.demo_connections()
    try:
        result = host_agent.get_connections().model_dump()
        result.update({"supported": True, "simulated": False})
        return result
    except HostAgentError as exc:
        if host_agent.is_running_in_docker():
            return {
                "supported": False,
                "simulated": False,
                "source": "docker_container",
                "connections": [],
                "error": f"Windows host connections are unavailable: {exc}",
            }
    result = net.active_connections()
    result["simulated"] = False
    result["source"] = "windows_host" if net.CURRENT_OS == "windows" else "backend_runtime"
    return result


@router.post("/traceroute")
def run_traceroute(
    payload: TracerouteRequest,
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if resolve_demo_mode(demo, db, user):
        result = demo_data.demo_traceroute(payload.target)
    else:
        raw = net.traceroute(payload.target)
        result = {"supported": raw["supported"], "simulated": False, "target": payload.target,
                   "hops": raw["hops"], "error": raw.get("error"),
                   "destination_reached": raw.get("destination_reached")}

    run = TracerouteRun(user_id=user.id, target=payload.target, supported=result["supported"])
    db.add(run)
    db.commit()
    db.refresh(run)
    for h in result.get("hops", []):
        db.add(TracerouteHop(
            run_id=run.id, hop_number=h["hop"], ip=h.get("ip"), hostname=h.get("hostname"),
            latency_ms=h.get("latency_ms"), status=h.get("status", "no_response"),
        ))
    db.commit()

    result["run_id"] = run.id
    return result


@router.get("/traceroute/history")
def traceroute_history(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    runs = (
        db.query(TracerouteRun)
        .filter(TracerouteRun.user_id == user.id)
        .order_by(TracerouteRun.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {"id": r.id, "created_at": r.created_at, "target": r.target, "supported": r.supported, "hop_count": len(r.hops)}
        for r in runs
    ]


@router.post("/discover")
def discover_devices(
    payload: DiscoverDevicesRequest,
    demo: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if resolve_demo_mode(demo, db, user):
        devices = demo_data.demo_devices()
        simulated = True
        supported = True
        status = "completed"
        detail = None
        source = "simulated"
        subnet = None
        scanned_hosts = None
        total_hosts = None
        scan_complete = None
    else:
        try:
            result = host_agent.discover_devices(max_hosts=payload.max_hosts).model_dump()
            devices = result["devices"]
            simulated = False
            supported = result["supported"]
            status = result["status"]
            detail = result.get("detail")
            source = result["source"]
            subnet = result.get("subnet")
            scanned_hosts = result.get("scanned_hosts")
            total_hosts = result.get("total_hosts")
            scan_complete = result.get("scan_complete")
        except HostAgentError as exc:
            if host_agent.is_running_in_docker():
                devices = []
                simulated = False
                supported = None
                status = "skipped"
                detail = f"Windows host discovery was skipped because the host agent is unavailable: {exc}"
                source = "docker_container"
                subnet = None
                scanned_hosts = 0
                total_hosts = None
                scan_complete = False
            else:
                raw = discover_local_devices(max_hosts=payload.max_hosts)
                devices = raw["devices"]
                simulated = False
                supported = raw["supported"]
                status = raw.get("status", "success" if supported else "unsupported")
                detail = raw.get("detail")
                source = raw.get("source", measurement_source())
                subnet = raw.get("subnet")
                scanned_hosts = raw.get("scanned_hosts")
                total_hosts = raw.get("total_hosts")
                scan_complete = raw.get("scan_complete")

    if status in {"success", "empty", "partial"} and subnet:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            if network.version != 4:
                raise ValueError("Discovery subnet must be IPv4.")
            devices = [
                device for device in devices
                if ipaddress.ip_address(device["ip"]) in network
            ]
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Ignoring malformed local discovery results: %s", exc)
            devices = []
            status = "failed"
            detail = "Discovery returned invalid subnet or device addresses."
        if status in {"success", "empty"} and scan_complete is True:
            existing_rows = db.query(NetworkDevice).filter(
                NetworkDevice.user_id == user.id,
                NetworkDevice.subnet == subnet,
            ).all()
            observed_ips = {device["ip"] for device in devices}
            for existing in existing_rows:
                if existing.ip not in observed_ips:
                    existing.status = "not_seen"
        for d in devices:
            existing = db.query(NetworkDevice).filter(
                NetworkDevice.user_id == user.id,
                NetworkDevice.subnet == subnet,
                NetworkDevice.ip == d["ip"],
            ).first()
            device_status = d.get("status") or "neighbor_cache"
            if existing:
                existing.mac = d.get("mac") or existing.mac
                existing.hostname = d.get("hostname") or existing.hostname
                existing.status = device_status
                if device_status == "responsive":
                    existing.last_seen = now
            else:
                db.add(NetworkDevice(user_id=user.id, ip=d["ip"], mac=d.get("mac"), hostname=d.get("hostname"),
                                      subnet=subnet, status=device_status, first_seen=now, last_seen=now))
        db.commit()

    return {
        "supported": supported, "simulated": simulated, "status": status,
        "detail": detail, "devices": devices, "source": source,
        "subnet": subnet, "scanned_hosts": scanned_hosts,
        "total_hosts": total_hosts,
        "scan_complete": scan_complete,
    }


@router.get("/devices")
def list_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    devices = (
        db.query(NetworkDevice)
        .filter(NetworkDevice.user_id == user.id)
        .order_by(NetworkDevice.last_seen.desc())
        .all()
    )
    return [
        {"id": d.id, "ip": d.ip, "mac": d.mac, "hostname": d.hostname, "status": d.status,
         "response_ms": d.response_ms, "first_seen": d.first_seen, "last_seen": d.last_seen}
        for d in devices
    ]


@router.get("/map")
def network_map(demo: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Combined shape for the Network Map page: active interface and saved
    observations from its subnet. Does not trigger a
    new scan — call POST /api/network/discover first (spec section 11: only
    perform discovery on the user's local network, never an internet-wide
    scan).
    """
    is_demo = resolve_demo_mode(demo, db, user)
    summary = demo_data.demo_interface_summary() if is_demo else _interface_summary()

    devices = (
        db.query(NetworkDevice)
        .filter(
            NetworkDevice.user_id == user.id,
            NetworkDevice.subnet == summary.get("subnet"),
        )
        .order_by(NetworkDevice.last_seen.desc())
        .limit(1024)
        .all()
    ) if summary.get("subnet") else []
    device_list = [
        {"id": d.id, "ip": d.ip, "mac": d.mac, "hostname": d.hostname,
         "status": d.status, "last_seen": d.last_seen, "subnet": d.subnet}
        for d in devices
    ] if not is_demo else demo_data.demo_devices()

    return {
        "simulated": is_demo,
        "local_ip": summary.get("local_ip"),
        "gateway": summary.get("gateway"),
        "subnet": summary.get("subnet"),
        "interface_name": summary.get("interface_name"),
        "gateway_ipv6": summary.get("gateway_ipv6"),
        "source": "simulated" if is_demo else summary.get("source"),
        "host_agent": None if is_demo else summary.get("host_agent"),
        "devices": device_list,
    }
