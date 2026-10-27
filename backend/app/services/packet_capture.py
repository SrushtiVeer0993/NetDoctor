"""
Packet Analyzer service (spec section 14).

Uses Scapy where supported. Capture happens ONLY in the backend — the
frontend never touches raw interfaces, it only calls these REST endpoints.
Requires administrator/root privileges and, in Docker, NET_RAW/NET_ADMIN
capabilities (already granted in docker-compose.yml). When unavailable —
scapy not installed, no privilege, unsupported OS — every function returns
{"supported": False, "error": "..."} rather than fabricating packets.

Captures are kept in memory for the life of the process plus a JSON
snapshot on disk (spec section 23: do not store large packet captures
directly in PostgreSQL — only metadata belongs there).
"""
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone

try:
    from scapy.all import AsyncSniffer, Ether, IP, IPv6, TCP, UDP, ICMP, DNS, conf
    SCAPY_AVAILABLE = True
    SCAPY_IMPORT_ERROR = None
except Exception as exc:
    SCAPY_AVAILABLE = False
    SCAPY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

CAPTURE_DIR = os.path.join(tempfile.gettempdir(), "netdoctor_captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)

_captures: dict[str, dict] = {}
_lock = threading.Lock()
DEFAULT_MAX_PACKETS = 500
MAX_ACTIVE_CAPTURES = 4
CAPTURE_RETENTION = timedelta(hours=24)


def _classify(pkt) -> str:
    dns_port = (
        pkt.haslayer(UDP) and (pkt[UDP].sport == 53 or pkt[UDP].dport == 53)
    ) or (
        pkt.haslayer(TCP) and (pkt[TCP].sport == 53 or pkt[TCP].dport == 53)
    )
    if pkt.haslayer(DNS) or dns_port:
        return "DNS"
    if pkt.haslayer(TCP):
        return "TCP"
    if pkt.haslayer(UDP):
        return "UDP"
    has_icmpv6 = any(layer.__name__.startswith("ICMPv6") for layer in pkt.layers())
    if pkt.haslayer(ICMP) or has_icmpv6:
        return "ICMP"
    return "OTHER"


def _summarize(pkt, index: int) -> dict:
    summary = {
        "index": index,
        "timestamp": datetime.fromtimestamp(float(pkt.time), timezone.utc).isoformat()
        if getattr(pkt, "time", None) is not None else datetime.now(timezone.utc).isoformat(),
        "protocol": _classify(pkt),
        "source": None, "destination": None,
        "source_port": None, "destination_port": None,
        "length": len(pkt),
        "parsed": {},
    }
    if pkt.haslayer(Ether):
        summary["parsed"]["ethernet"] = {"source_mac": pkt[Ether].src, "destination_mac": pkt[Ether].dst}
    if pkt.haslayer(IP):
        summary["source"] = pkt[IP].src
        summary["destination"] = pkt[IP].dst
        summary["parsed"]["ip"] = {"source_ip": pkt[IP].src, "destination_ip": pkt[IP].dst, "ttl": pkt[IP].ttl}
    elif pkt.haslayer(IPv6):
        summary["source"] = pkt[IPv6].src
        summary["destination"] = pkt[IPv6].dst
        summary["parsed"]["ipv6"] = {
            "source_ip": pkt[IPv6].src,
            "destination_ip": pkt[IPv6].dst,
            "hop_limit": pkt[IPv6].hlim,
        }
    if pkt.haslayer(TCP):
        summary["source_port"] = int(pkt[TCP].sport)
        summary["destination_port"] = int(pkt[TCP].dport)
        summary["parsed"]["tcp"] = {
            "source_port": int(pkt[TCP].sport), "destination_port": int(pkt[TCP].dport),
            "flags": str(pkt[TCP].flags),
        }
    elif pkt.haslayer(UDP):
        summary["source_port"] = int(pkt[UDP].sport)
        summary["destination_port"] = int(pkt[UDP].dport)
        summary["parsed"]["udp"] = {"source_port": int(pkt[UDP].sport), "destination_port": int(pkt[UDP].dport)}
    return summary


def start_capture(
    interface: str | None = None,
    duration_seconds: int = 30,
    max_packets: int = DEFAULT_MAX_PACKETS,
    owner_id: int | None = None,
):
    if not SCAPY_AVAILABLE:
        return {
            "supported": False,
            "error": f"Scapy packet capture dependencies could not be loaded: {SCAPY_IMPORT_ERROR}",
        }
    if os.name == "nt" and not conf.use_pcap:
        return {
            "supported": False,
            "error": "Npcap is required for packet capture on Windows. Install Npcap, then restart the backend as Administrator.",
        }

    _prune_expired_captures()
    capture_id = uuid.uuid4().hex[:8]
    packets_store: list[dict] = []
    counter = {"n": 0}

    def on_packet(pkt):
        if counter["n"] >= max_packets:
            return
        try:
            summary = _summarize(pkt, counter["n"])
        except Exception:
            return
        counter["n"] += 1
        with _lock:
            packets_store.append(summary)

    with _lock:
        active_count = sum(
            1 for capture in _captures.values()
            if capture["status"] in ("starting", "running")
            and getattr(capture.get("sniffer"), "running", True)
        )
        if active_count >= MAX_ACTIVE_CAPTURES:
            return {
                "supported": False,
                "error": f"At most {MAX_ACTIVE_CAPTURES} packet captures may run at once.",
            }
        _captures[capture_id] = {
            "sniffer": None, "packets": packets_store,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "starting", "interface": interface, "owner_id": owner_id,
        }

    try:
        sniffer = AsyncSniffer(iface=interface, prn=on_packet, store=False, timeout=duration_seconds)
        sniffer.start()
    except PermissionError:
        with _lock:
            _captures.pop(capture_id, None)
        return {"supported": False, "error": "Permission denied — packet capture requires administrator/root privileges."}
    except Exception as exc:
        with _lock:
            _captures.pop(capture_id, None)
        return {"supported": False, "error": str(exc)}

    with _lock:
        _captures[capture_id]["sniffer"] = sniffer
        _captures[capture_id]["status"] = "running"
    return {"supported": True, "capture_id": capture_id, "status": "running"}


def _get_owned_capture(capture_id: str, owner_id: int | None):
    with _lock:
        entry = _captures.get(capture_id)
        if not entry or entry.get("owner_id") != owner_id:
            return None
        return entry


def _prune_expired_captures():
    cutoff = datetime.now(timezone.utc) - CAPTURE_RETENTION
    expired = []
    with _lock:
        for capture_id, entry in list(_captures.items()):
            started_at = datetime.fromisoformat(entry["started_at"])
            if entry["status"] != "running" and started_at < cutoff:
                expired.append(capture_id)
                del _captures[capture_id]
    for capture_id in expired:
        try:
            os.remove(os.path.join(CAPTURE_DIR, f"{capture_id}.json"))
        except FileNotFoundError:
            pass


def stop_capture(capture_id: str, owner_id: int | None = None):
    entry = _get_owned_capture(capture_id, owner_id)
    if not entry:
        return {"stopped": False, "error": "capture not found"}
    if entry["sniffer"] is None:
        return {"stopped": False, "error": "capture is still starting"}
    if not getattr(entry["sniffer"], "running", False):
        entry["status"] = "stopped"
        _persist(capture_id)
        return {"stopped": True}
    try:
        entry["sniffer"].stop()
    except Exception as exc:
        if getattr(entry["sniffer"], "running", False):
            return {"stopped": False, "error": f"Could not stop packet capture: {exc}"}
    entry["status"] = "stopped"
    _persist(capture_id)
    return {"stopped": True}


def get_status(capture_id: str, owner_id: int | None = None):
    entry = _get_owned_capture(capture_id, owner_id)
    if not entry:
        return None
    previous_status = entry["status"]
    is_running = getattr(entry["sniffer"], "running", previous_status == "running")
    entry["status"] = "running" if is_running else "stopped"
    counts: dict[str, int] = {}
    for p in entry["packets"]:
        counts[p["protocol"]] = counts.get(p["protocol"], 0) + 1
    status = {
        "capture_id": capture_id, "status": entry["status"], "started_at": entry["started_at"],
        "total_packets": len(entry["packets"]), "protocol_counts": counts, "interface": entry["interface"],
    }
    if previous_status == "running" and entry["status"] == "stopped":
        _persist(capture_id)
    return status


def get_packets(
    capture_id: str,
    protocol_filter: str | None = None,
    limit: int = 500,
    owner_id: int | None = None,
):
    entry = _get_owned_capture(capture_id, owner_id)
    if not entry:
        return []
    packets = entry["packets"]
    if protocol_filter and protocol_filter != "ALL":
        packets = [p for p in packets if p["protocol"] == protocol_filter]
    return packets[-limit:]


def _persist(capture_id: str):
    with _lock:
        entry = _captures.get(capture_id)
        if not entry:
            return
        snapshot = {
            "capture_id": capture_id,
            "started_at": entry["started_at"],
            "packets": list(entry["packets"]),
        }
    path = os.path.join(CAPTURE_DIR, f"{capture_id}.json")
    with open(path, "w") as f:
        json.dump(snapshot, f)
