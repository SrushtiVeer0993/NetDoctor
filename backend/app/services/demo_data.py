"""
DEMO MODE (spec section 33).

Every function here is clearly named demo_* and every result it produces
carries "simulated": true, so simulated and real measurements are never
mixed without a label (spec's explicit requirement). Nothing outside this
module and the endpoints that check the demo flag is allowed to invent
data — see spec section 32 ("no fake networking results unless the
application is explicitly running in DEMO MODE").
"""
import random
from datetime import datetime, timezone


def demo_full_diagnosis(
    external_host="8.8.8.8",
    dns_domain="google.com",
    websites=None,
    discover_devices=False,
):
    websites = websites or []
    latency_avg = round(random.uniform(18, 45), 1)
    jitter = round(random.uniform(1, 6), 1)
    loss = round(random.choice([0, 0, 0, 0, 2]), 1)

    site_results = [
        {
            "url": url, "reachable": True, "status_code": 200,
            "successful_request": True, "response_ms": round(random.uniform(80, 400), 1),
        }
        for url in websites
    ]

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
        "gateway": {"reachable": True, "gateway_ip": "192.168.1.1", "avg_ms": round(random.uniform(1, 4), 1), "icmp_unavailable": False},
        "internet": {"reachable": True, "target": external_host, "avg_ms": latency_avg},
        "latency": {
            "target": external_host, "min_ms": round(latency_avg - jitter, 1),
            "max_ms": round(latency_avg + jitter * 2, 1), "avg_ms": latency_avg,
            "jitter_ms": jitter, "sent": 8, "received": 8,
            "samples": [round(latency_avg + random.uniform(-jitter, jitter), 1) for _ in range(8)],
        },
        "packet_loss": {"target": external_host, "sent": 10, "received": 10 - int(loss / 10), "loss_pct": loss},
        "dns": {"domain": dns_domain, "resolved_ip": "142.250.190.14", "response_ms": round(random.uniform(5, 25), 1), "success": True},
        "websites": site_results,
        "devices": {
            "supported": True if discover_devices else None,
            "status": "completed" if discover_devices else "skipped",
            "devices": demo_devices() if discover_devices else [],
            "detail": None if discover_devices else "Device discovery was not requested.",
        },
        "health_score": 96,
        "health_score_factors": {"latency": 0, "packet_loss": 0, "dns": 0, "connectivity": 0, "websites": 0},
        "findings": [{
            "severity": "healthy", "confidence": "high",
            "evidence": "Simulated measurements within normal range.",
            "text": "No significant issues detected. (DEMO MODE — results are simulated for demonstration.)",
        }],
        "recommendations": ["Connection looks healthy — no action needed right now."],
    }
    return result


def demo_devices():
    names = [("192.168.1.1", "router", "aa:bb:cc:00:00:01"), ("192.168.1.12", "laptop", "aa:bb:cc:00:00:02"),
              ("192.168.1.18", "phone", "aa:bb:cc:00:00:03"), ("192.168.1.24", "smart-tv", "aa:bb:cc:00:00:04")]
    return [{"ip": ip, "mac": mac, "hostname": name} for ip, name, mac in names]


def demo_traceroute(target):
    hops = [
        {"hop": 1, "ip": "192.168.1.1", "hostname": None, "latency_ms": 1.2, "status": "responded"},
        {"hop": 2, "ip": "10.10.0.1", "hostname": None, "latency_ms": 8.4, "status": "responded"},
        {"hop": 3, "ip": None, "hostname": None, "latency_ms": None, "status": "no_response"},
        {"hop": 4, "ip": "203.0.113.5", "hostname": None, "latency_ms": 24.1, "status": "responded"},
        {"hop": 5, "ip": "198.51.100.9", "hostname": None, "latency_ms": 31.7, "status": "responded"},
    ]
    return {"supported": True, "simulated": True, "target": target, "hops": hops}


def demo_connections():
    conns = [
        {"protocol": "TCP", "local_ip": "192.168.1.12", "local_port": "51342", "remote_ip": "142.250.190.14", "remote_port": "443", "state": "ESTABLISHED"},
        {"protocol": "TCP", "local_ip": "192.168.1.12", "local_port": "8000", "remote_ip": None, "remote_port": None, "state": "LISTENING"},
        {"protocol": "UDP", "local_ip": "192.168.1.12", "local_port": "68", "remote_ip": None, "remote_port": None, "state": "STATELESS"},
        {"protocol": "TCP", "local_ip": "192.168.1.12", "local_port": "51344", "remote_ip": "104.18.2.5", "remote_port": "443", "state": "TIME_WAIT"},
    ]
    return {"supported": True, "simulated": True, "connections": conns}


def demo_speed_test():
    return {
        "simulated": True,
        "methodology": "Simulated result (DEMO MODE) — no real network transfer performed.",
        "download": {"success": True, "bytes": 12_500_000, "seconds": 1.4, "mbps": round(random.uniform(60, 180), 1)},
        "upload": {"success": True, "bytes": 5_000_000, "seconds": 1.1, "mbps": round(random.uniform(15, 40), 1)},
        "latency_ms": round(random.uniform(15, 35), 1),
        "jitter_ms": round(random.uniform(1, 5), 1),
    }


def demo_monitor_measurement():
    return {
        "latency_ms": round(random.uniform(18, 45), 1),
        "packet_loss_pct": random.choice([0.0, 0.0, 0.0, 2.0]),
        "dns_ms": round(random.uniform(5, 25), 1),
        "internet_up": True,
        "simulated": True,
    }


def demo_interface_summary():
    return {
        "simulated": True, "interface_name": "wlan0 (demo)", "connection_type": "wifi",
        "local_ip": "192.168.1.12", "subnet": "192.168.1.", "gateway": "192.168.1.1",
        "dns_servers": ["1.1.1.1", "8.8.8.8"], "mac_address": "aa:bb:cc:00:00:02",
        "ssid": "Demo-WiFi-5G", "signal_dbm": -52, "frequency_mhz": 5220, "link_speed_mbps": 433.0,
    }


def demo_packets(count: int = 40):
    import random as _r
    protocols = ["TCP", "TCP", "TCP", "UDP", "DNS", "ICMP"]
    packets = []
    for i in range(count):
        proto = _r.choice(protocols)
        src = f"192.168.1.{_r.randint(2, 40)}"
        dst = _r.choice(["142.250.190.14", "104.18.2.5", "1.1.1.1", "8.8.8.8"])
        entry = {
            "index": i, "timestamp": datetime.now(timezone.utc).isoformat(), "protocol": proto,
            "source": src, "destination": dst,
            "source_port": _r.randint(1024, 65000) if proto in ("TCP", "UDP", "DNS") else None,
            "destination_port": 443 if proto == "TCP" else (53 if proto == "DNS" else None),
            "length": _r.randint(64, 1500),
            "parsed": {
                "ethernet": {"source_mac": "aa:bb:cc:00:00:02", "destination_mac": "aa:bb:cc:00:00:01"},
                "ip": {"source_ip": src, "destination_ip": dst, "ttl": 64},
            },
        }
        packets.append(entry)
    return {
        "simulated": True, "capture_id": "demo", "status": "stopped",
        "total_packets": len(packets), "packets": packets,
        "protocol_counts": {p: sum(1 for pkt in packets if pkt["protocol"] == p) for p in set(protocols)},
    }
