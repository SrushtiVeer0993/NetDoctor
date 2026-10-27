"""
legacy_diagnostics.py
======================
Phase-1 measurement + rule-based analysis engine.

This is the original NetDoctor diagnostics.py, ported as-is (same functions,
same field names) so the new backend's persisted history stays compatible,
plus two spec-driven changes:

  1. check_gateway_connectivity() now returns an explicit
     "icmp_unavailable" flag instead of a bare reachable=False, so the
     diagnosis engine (and the frontend) can tell "gateway blocks ICMP"
     apart from "local network is actually down" (see NetDoctor spec
     section 4 "IMPORTANT GATEWAY LOGIC").
  2. diagnose() no longer treats gateway-unreachable-but-internet-reachable
     as a local-network failure; it reports it as an ICMP-filtering note
     instead, and only escalates to "possible local connectivity problem"
     when internet is unreachable too.

Later phases replace individual pieces of this (traceroute, active
connections, packet capture, interface info, speed test, anomaly
detection) without changing this module's public function names, so the
API layer written in Phase 1 keeps working.
"""

import concurrent.futures
import platform
import ipaddress
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timezone

import requests

IS_WINDOWS = platform.system().lower() == "windows"
PING_TIMEOUT_MS = 2000


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _ping_with_status(host, count=4, timeout_ms=PING_TIMEOUT_MS):
    try:
        if IS_WINDOWS:
            cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        else:
            timeout_s = max(1, int(round(timeout_ms / 1000)))
            cmd = ["ping", "-c", str(count), "-W", str(timeout_s), host]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=(count * timeout_ms / 1000.0) + 5,
        )
        if proc.returncode > 1:
            detail = proc.stderr.decode(errors="ignore") or proc.stdout.decode(errors="ignore")
            return {
                "output": None, "error_type": "tool_error",
                "error": detail.strip() or "Ping utility failed.",
            }
        return {"output": proc.stdout.decode(errors="ignore"), "error_type": None, "error": None}
    except PermissionError as exc:
        return {"output": None, "error_type": "permission_denied", "error": str(exc)}
    except FileNotFoundError as exc:
        return {"output": None, "error_type": "unsupported", "error": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"output": None, "error_type": "timeout", "error": str(exc)}
    except OSError as exc:
        return {"output": None, "error_type": "tool_error", "error": str(exc)}


def _ping(host, count=4, timeout_ms=PING_TIMEOUT_MS):
    return _ping_with_status(host, count, timeout_ms)["output"]


def _parse_ping_times(output):
    if not output:
        return []
    matches = re.findall(r"time[=<]([\d.]+)\s*ms", output, flags=re.IGNORECASE)
    return [float(m) for m in matches]


def measurement_source():
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return "docker_container"
    return f"{platform.system().lower()}_host"


def _get_default_gateway():
    try:
        if IS_WINDOWS:
            from app.network.windows import get_default_route

            route = get_default_route()
            return route.get("gateway") if route else None
        elif platform.system().lower() == "linux":
            out = subprocess.run(
                ["ip", "-4", "route", "show", "default"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True,
            ).stdout.decode(errors="ignore")
            routes = []
            for line in out.splitlines():
                match = re.search(r"\bvia\s+([0-9.]+)", line)
                metric = re.search(r"\bmetric\s+(\d+)", line)
                if match:
                    routes.append((int(metric.group(1)) if metric else 0, match.group(1)))
            return min(routes, default=(None, None))[1]
        else:
            out = subprocess.run(
                ["route", "-n", "get", "default"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True,
            ).stdout.decode(errors="ignore")
            match = re.search(r"\bgateway:\s*([0-9a-fA-F:.]+)", out)
            return match.group(1) if match else None
    except Exception:
        pass
    return None


def _get_local_subnet_prefix():
    network = _get_local_ipv4_network()
    return str(network) if network else None


def _get_local_ipv4_address():
    if IS_WINDOWS:
        try:
            from app.network.windows import get_default_route

            route = get_default_route()
            return route.get("local_ip") if route else None
        except (OSError, ValueError):
            return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        try:
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _get_local_ipv4_network():
    if IS_WINDOWS:
        try:
            from app.network.windows import get_default_route

            route = get_default_route()
            if route and route.get("local_ip") and route.get("prefix") is not None:
                return ipaddress.IPv4Network(
                    f"{route['local_ip']}/{int(route['prefix'])}", strict=False
                )
        except (OSError, ValueError, TypeError):
            return None
        return None
    local_ip = _get_local_ipv4_address()
    if not local_ip:
        return None

    try:
        if platform.system().lower() == "linux":
            output = subprocess.run(
                ["ip", "-o", "-f", "inet", "addr", "show", "scope", "global"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True,
            ).stdout.decode(errors="ignore")
            network = None
            for line in output.splitlines():
                match = re.search(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})", line)
                if match and match.group(1).split("/")[0] == local_ip:
                    network = ipaddress.IPv4Network(match.group(1), strict=False)
                    break
            if network is None:
                return None
        else:
            output = subprocess.run(
                ["ifconfig"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5, check=True,
            ).stdout.decode(errors="ignore")
            blocks = re.split(r"\n(?=\S)", output)
            network = None
            for block in blocks:
                if not re.search(rf"\binet\s+{re.escape(local_ip)}\b", block):
                    continue
                match = re.search(r"\bnetmask\s+(0x[0-9a-fA-F]+)", block)
                if match:
                    mask = ipaddress.IPv4Address(int(match.group(1), 16))
                    network = ipaddress.IPv4Network(f"{local_ip}/{mask}", strict=False)
                    break
            if network is None:
                return None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None

    address = ipaddress.IPv4Address(local_ip)
    if not address.is_private or address.is_link_local:
        return None
    return network


# ----------------------------------------------------------------------
# Measurements
# ----------------------------------------------------------------------

def check_gateway_connectivity():
    gateway = _get_default_gateway()
    if not gateway:
        return {
            "reachable": False, "gateway_ip": None, "avg_ms": None,
            "icmp_unavailable": True,
            "detail": "Could not determine default gateway",
        }

    measurement = _ping_with_status(gateway, count=2)
    output = measurement["output"]
    times = _parse_ping_times(output)
    tool_error = measurement["error_type"] is not None
    reachable = len(times) > 0
    return {
        "reachable": None if tool_error else reachable,
        "gateway_ip": gateway,
        "avg_ms": round(sum(times) / len(times), 1) if times else None,
        # ICMP not answering is not proof the gateway/router itself is down —
        # many routers/firewalls silently drop ICMP. The diagnosis engine
        # below treats this distinctly from a true local-network failure.
        "icmp_unavailable": not reachable,
        "error_type": measurement["error_type"],
        "detail": measurement["error"],
    }


def check_internet_connectivity(external_host="8.8.8.8"):
    measurement = _ping_with_status(external_host, count=2)
    output = measurement["output"]
    times = _parse_ping_times(output)
    try:
        start = time.perf_counter()
        with socket.create_connection(("1.1.1.1", 443), timeout=3):
            tcp_reachable = True
        tcp_response_ms = round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        tcp_reachable = None
        tcp_response_ms = None
    return {
        "reachable": tcp_reachable,
        "target": external_host,
        "avg_ms": tcp_response_ms,
        "method": "tcp_connect_to_public_ip",
        "icmp_reachable": bool(times) if not measurement["error_type"] else None,
        "icmp_unavailable": not bool(times),
        "icmp_avg_ms": round(sum(times) / len(times), 1) if times else None,
        "icmp_error_type": measurement["error_type"],
        "icmp_detail": measurement["error"],
    }


def measure_latency(host="8.8.8.8", count=8):
    measurement = _ping_with_status(host, count=count)
    output = measurement["output"]
    times = _parse_ping_times(output)
    if not times:
        return {"target": host, "min_ms": None, "max_ms": None, "avg_ms": None,
                 "jitter_ms": None, "sent": count if output is not None else 0,
                 "received": 0, "samples": [],
                 "error_type": measurement["error_type"], "error": measurement["error"]}
    avg = sum(times) / len(times)
    jitter = round(
        (sum(abs(t - avg) for t in times) / len(times)), 1
    ) if len(times) > 1 else 0.0
    return {
        "target": host,
        "min_ms": round(min(times), 1),
        "max_ms": round(max(times), 1),
        "avg_ms": round(avg, 1),
        "jitter_ms": jitter,
        "sent": count if output is not None else 0,
        "received": len(times),
        "samples": [round(t, 1) for t in times],
        "error_type": measurement["error_type"], "error": measurement["error"],
    }


def measure_packet_loss(host="8.8.8.8", count=10):
    measurement = _ping_with_status(host, count=count)
    output = measurement["output"]
    times = _parse_ping_times(output)
    sent = count if output is not None else 0
    received = min(len(times), sent)
    # No replies may mean ICMP is filtered; that is not enough evidence to
    # report a measured 100% packet-loss rate.
    loss_pct = round((sent - received) / sent * 100, 1) if sent > 0 and received > 0 else None
    return {
        "target": host, "sent": sent, "received": received, "loss_pct": loss_pct,
        "icmp_unavailable": sent > 0 and received == 0,
        "error_type": measurement["error_type"], "error": measurement["error"],
    }


def measure_dns_response_time(domain="google.com"):
    try:
        start = time.perf_counter()
        ip = socket.gethostbyname(domain)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"domain": domain, "resolved_ip": ip, "response_ms": elapsed_ms, "success": True}
    except Exception as exc:
        return {"domain": domain, "resolved_ip": None, "response_ms": None, "success": False, "error": str(exc)}


def test_websites(urls):
    results = []
    for url in urls:
        entry = {"url": url}
        try:
            start = time.perf_counter()
            resp = requests.get(url, timeout=6)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            # A non-200 response still means the server was reached —
            # see NetDoctor spec section 8 (do not treat 403/404/5xx as "site down").
            entry.update({
                "reachable": True,
                "status_code": resp.status_code,
                "successful_request": 200 <= resp.status_code < 300,
                "http_category": (
                    "success" if 200 <= resp.status_code < 300 else
                    "redirect" if 300 <= resp.status_code < 400 else
                    "client_error" if 400 <= resp.status_code < 500 else
                    "server_error" if 500 <= resp.status_code < 600 else "other"
                ),
                "response_ms": elapsed_ms,
            })
        except requests.Timeout as exc:
            entry.update({
                "reachable": False, "status_code": None,
                "successful_request": False, "http_category": None,
                "error_type": "timeout", "response_ms": None, "error": str(exc),
            })
        except requests.exceptions.SSLError as exc:
            entry.update({
                "reachable": False, "status_code": None,
                "successful_request": False, "http_category": None,
                "error_type": "tls_error", "response_ms": None, "error": str(exc),
            })
        except requests.ConnectionError as exc:
            message = repr(exc).lower()
            if any(marker in message for marker in (
                "nameresolutionerror", "getaddrinfo failed",
                "name or service not known", "temporary failure in name resolution",
            )):
                error_type = "dns_resolution"
            elif "connection refused" in message or "actively refused" in message:
                error_type = "connection_refused"
            else:
                error_type = "connection_error"
            entry.update({
                "reachable": False, "status_code": None,
                "successful_request": False, "http_category": None,
                "error_type": error_type, "response_ms": None, "error": str(exc),
            })
        except Exception as exc:
            entry.update({
                "reachable": False, "status_code": None,
                "successful_request": False, "http_category": None,
                "error_type": "request_error", "response_ms": None, "error": str(exc),
            })
        results.append(entry)
    return results


def discover_local_devices(max_hosts=1024):
    network = _get_local_ipv4_network()
    if network is None:
        return {
            "supported": False, "status": "unsupported", "devices": [],
            "detail": "Could not determine a private local IPv4 subnet with its mask.",
        }

    local_ip = _get_local_ipv4_address()
    max_hosts = max(1, min(int(max_hosts), 1024))
    addresses = list(
        address for address in network.hosts() if str(address) != local_ip
    )[:max_hosts]
    total_hosts = max(
        0,
        network.num_addresses - (2 if network.prefixlen < 31 else 0) - 1,
    )
    scan_complete = len(addresses) >= total_hosts
    responsive = set()
    errors = []

    def probe(address):
        if IS_WINDOWS:
            command = ["ping", "-n", "1", "-w", "250", str(address)]
        else:
            command = ["ping", "-c", "1", "-W", "1", str(address)]
        result = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
        return result.returncode == 0

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = {executor.submit(probe, address): str(address) for address in addresses}
            for future in concurrent.futures.as_completed(futures, timeout=35):
                try:
                    if future.result():
                        responsive.add(futures[future])
                except PermissionError:
                    return {
                        "supported": False, "status": "permission_denied", "devices": [],
                        "detail": "Permission was denied while probing the local network.",
                        "subnet": str(network), "source": measurement_source(),
                    }
                except FileNotFoundError:
                    return {
                        "supported": False, "status": "unsupported", "devices": [],
                        "detail": "The system ping utility is unavailable.",
                        "subnet": str(network), "source": measurement_source(),
                    }
                except (OSError, subprocess.SubprocessError) as exc:
                    errors.append(str(exc))
    except concurrent.futures.TimeoutError:
        errors.append("Some local probes did not finish before the scan timeout.")

    devices = []
    try:
        arp_out = subprocess.run(
            ["arp", "-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=True,
        ).stdout.decode(errors="ignore")
    except PermissionError:
        return {
            "supported": False, "status": "permission_denied", "devices": [],
            "detail": "Permission was denied while reading the ARP table.",
        }
    except FileNotFoundError:
        return {
            "supported": False, "status": "unsupported", "devices": [],
            "detail": "The system ARP utility is unavailable.",
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {
            "supported": False, "status": "failed", "devices": [],
            "detail": f"Could not read the local ARP table: {exc}",
        }

    try:
        for line in arp_out.splitlines():
            m = re.search(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*?([0-9a-fA-F]{2}[:-]"
                r"[0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})",
                line,
            )
            if not m:
                continue
            address_obj = ipaddress.IPv4Address(m.group(1))
            mac = m.group(2).replace("-", ":").lower()
            if (
                address_obj in network
                and str(address_obj) != local_ip
                and not (network.prefixlen < 31 and address_obj in {
                    network.network_address, network.broadcast_address,
                })
                and mac not in {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}
            ):
                address = m.group(1)
                devices.append({
                    "ip": address,
                    "mac": mac,
                    "status": "responsive" if address in responsive else "neighbor_cache",
                })
    except ValueError as exc:
        return {
            "supported": False, "status": "failed", "devices": [],
            "detail": f"Could not parse local ARP entries: {exc}",
        }

    devices = list({device["ip"]: device for device in devices}.values())
    status = "partial" if errors and devices else "failed" if errors else "success" if devices else "empty"
    if not scan_complete and status in {"success", "empty"}:
        status = "partial"
    detail = (
        f"Observed {len(devices)} neighbor(s) in {len(addresses)} of {total_hosts} local addresses; this is not a complete inventory."
        if devices and not errors else
        f"Partial discovery. {' '.join(dict.fromkeys(errors))}"
        if errors and devices else
        f"Local probes failed. {' '.join(dict.fromkeys(errors))}"
        if errors else
        "No neighbors were observed in the scanned subnet; devices that block ICMP may be absent."
    )
    return {
        "supported": True, "status": status, "devices": devices,
        "detail": detail, "scanned_hosts": len(addresses), "total_hosts": total_hosts,
        "scan_complete": scan_complete, "subnet": str(network),
        "source": measurement_source(),
    }


# ----------------------------------------------------------------------
# Health score (application-defined, not an industry-standard metric)
# ----------------------------------------------------------------------

def calculate_health_score(gateway, internet, latency, packet_loss, dns, websites):
    gateway = gateway or {}
    internet = internet or {}
    latency = latency or {}
    packet_loss = packet_loss or {}
    dns = dns or {}
    websites = websites or []

    website_proves_connectivity = any(w.get("reachable") is True for w in websites)
    if internet.get("reachable") is None and not website_proves_connectivity:
        return {"score": 50, "factors": {"connectivity": -50}}

    if internet.get("reachable") is False and not website_proves_connectivity:
        # Internet down is what actually matters to the user; an
        # ICMP-silent gateway alone should not tank the score (see gateway
        # logic notes above).
        if gateway.get("reachable") is True:
            base = 20
        elif gateway.get("reachable") is False and gateway.get("icmp_unavailable") is False:
            base = 5
        else:
            return {"score": 50, "factors": {"connectivity": -50}}
        return {"score": base, "factors": {"connectivity": base - 100}}

    score = 100.0
    factors = {}

    avg = latency.get("avg_ms")
    if avg is not None:
        if avg > 300:
            factors["latency"] = -30
        elif avg > 150:
            factors["latency"] = -18
        elif avg > 80:
            factors["latency"] = -8
        else:
            factors["latency"] = 0
    else:
        factors["latency"] = 0

    loss = None if packet_loss.get("icmp_unavailable") else packet_loss.get("loss_pct")
    if loss is None:
        factors["packet_loss"] = 0
    elif loss > 15:
        factors["packet_loss"] = -30
    elif loss > 5:
        factors["packet_loss"] = -18
    elif loss > 0:
        factors["packet_loss"] = -6
    else:
        factors["packet_loss"] = 0

    if dns.get("success") is False:
        factors["dns"] = -20
    elif dns.get("success") is None:
        factors["dns"] = 0
    elif dns.get("response_ms") is not None and dns["response_ms"] > 300:
        factors["dns"] = -10
    elif dns.get("response_ms") is not None and dns["response_ms"] > 120:
        factors["dns"] = -4
    else:
        factors["dns"] = 0

    factors["connectivity"] = 0
    if gateway.get("reachable") is False and gateway.get("icmp_unavailable") is False:
        factors["connectivity"] = -10

    if websites:
        unreachable = sum(1 for w in websites if not w.get("reachable"))
        slow = sum(1 for w in websites if w.get("reachable") and (w.get("response_ms") or 0) > 1500)
        factors["websites"] = -round(unreachable * (15 / len(websites)) + slow * (8 / len(websites)))
    else:
        factors["websites"] = 0

    missing_measurements = (
        int(gateway.get("reachable") is None and not gateway.get("icmp_unavailable"))
        + int(avg is None)
        + int(loss is None)
        + int(dns.get("success") is None)
        + sum(1 for site in websites if site.get("reachable") is None)
    )
    factors["measurement_completeness"] = -min(20, missing_measurements * 5)

    score += sum(factors.values())
    return {"score": max(0, min(100, round(score))), "factors": factors}


# ----------------------------------------------------------------------
# Diagnosis + recommendations (rule-based — never called "AI")
# ----------------------------------------------------------------------

def _finding(code, severity, confidence, evidence, text, recommendations=()):
    return {
        "code": code,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "text": text,
        "recommendations": list(recommendations),
    }


def diagnose(gateway, internet, latency, packet_loss, dns, websites):
    gateway = gateway or {}
    internet = internet or {}
    latency = latency or {}
    packet_loss = packet_loss or {}
    dns = dns or {}
    websites = websites or []
    findings = []

    gateway_icmp_note = None
    if gateway.get("icmp_unavailable") and gateway.get("reachable") is False:
        gateway_icmp_note = (
            "The gateway did not respond to ICMP. This does not necessarily mean the "
            "local network is broken — many routers, mobile hotspots and firewalls "
            "silently drop ICMP. Treat this as 'ICMP response unavailable', not proof "
            "of a local failure."
        )

    website_proves_connectivity = any(w.get("reachable") is True for w in websites)
    internet_icmp_unavailable = internet.get("reachable") is not True
    if internet_icmp_unavailable and not website_proves_connectivity:
        if internet.get("reachable") is None or (
            not gateway.get("reachable") and gateway.get("icmp_unavailable")
        ):
            findings.append(_finding(
                "connectivity_inconclusive", "info", "low",
                "Internet or gateway ICMP measurement is unavailable.",
                ("Connectivity could not be confirmed by the available ICMP measurements. "
                 "A device or network may block ICMP, so this result does not establish "
                 "that the connection is down."),
                ("Try opening a website or application, then rerun the diagnosis.",
                 "Check the device's Wi-Fi/Ethernet connection and gateway settings."),
            ))
            tool_errors = _diagnostic_tool_errors(gateway, internet, latency, packet_loss)
            if tool_errors:
                findings.append(_finding(
                    "diagnostic_tool_error", "info", "high",
                    "; ".join(tool_errors),
                    "One or more diagnostic tools could not complete their probe. This is a tool failure, not proof that the network is down.",
                    ("Check that the ping utility is installed and permitted, then rerun the affected check.",),
                ))
        elif not gateway.get("reachable"):
            findings.append(_finding(
                "connectivity_local", "critical", "medium",
                "Gateway unreachable AND internet unreachable.",
                ("Possible local connectivity problem: neither the router nor the "
                 "wider internet responded. This points to a local Wi-Fi/wired issue "
                 "rather than an ISP-only outage — though it is also consistent with "
                 "a fully disconnected adapter."),
                ("Check that Wi-Fi/Ethernet is connected on this device.",
                 "Restart the router and wait a minute before testing again.",
                 "Try a different device on the same network to isolate the problem."),
            ))
        else:
            findings.append(_finding(
                "connectivity_upstream", "critical", "medium",
                "Gateway reachable, internet unreachable.",
                ("Possible upstream/ISP or routing issue: the local router responds, "
                 "but nothing beyond it does. This is usually outside your local "
                 "network's control."),
                ("Contact your ISP to check for an outage in your area.",
                 "Check the router's WAN/Internet status light if it has one."),
            ))
        return {"findings": findings, "gateway_icmp_note": gateway_icmp_note}

    if internet_icmp_unavailable:
        findings.append(_finding(
            "internet_icmp_unavailable", "info", "high",
            "The internet ping target did not respond, but at least one website responded over HTTP.",
            ("Internet access is available over HTTP. The ping target may block ICMP, "
             "so its lack of response does not indicate an internet outage."),
            ("No action is needed if websites and applications work normally.",),
        ))

    if internet.get("icmp_unavailable") and internet.get("reachable") is True:
        if not internet.get("icmp_error_type"):
            findings.append(_finding(
                "internet_icmp_unavailable", "info", "high",
                "TCP connectivity succeeded while the external ICMP probe did not respond.",
                ("Internet access was confirmed with TCP. The ping target or network may block "
                 "ICMP; its lack of response does not indicate an internet outage."),
                ("No action is needed if the connection works normally.",),
            ))

    if gateway_icmp_note:
        findings.append(_finding(
            "gateway_icmp_unavailable", "info", "low",
            "Gateway ICMP failed, but internet is reachable.",
            gateway_icmp_note,
            ("No action is needed if the connection works; many routers and hotspots do not answer ICMP.",),
        ))

    loss = None if packet_loss.get("icmp_unavailable") else packet_loss.get("loss_pct")
    avg_latency = latency.get("avg_ms")
    dns_ok = dns.get("success")
    dns_slow = dns.get("response_ms") is not None and dns["response_ms"] > 200
    site_issues = [
        w for w in websites
        if (
            w.get("reachable") is False
            and w.get("error_type") not in {
                "dns_resolution", "timeout", "connection_refused", "tls_error",
            }
        )
        or (w.get("response_ms") is not None and w["response_ms"] > 1500)
    ]
    all_sites_bad = websites and len(site_issues) == len(websites)
    some_sites_bad = websites and 0 < len(site_issues) < len(websites)
    http_errors = [
        w for w in websites
        if w.get("reachable") is True and w.get("status_code") is not None
        and w["status_code"] >= 400
    ]
    redirects = [
        w for w in websites
        if w.get("reachable") is True and w.get("status_code") is not None
        and 300 <= w["status_code"] < 400
    ]

    link_recommendations = (
        "Move closer to the router or reduce Wi-Fi obstacles.",
        "Switch to 5GHz or a wired connection if available.",
        "Rerun the diagnosis after reconnecting, to compare results.",
    )
    if loss is not None and loss > 5 and avg_latency is not None and avg_latency > 100:
        findings.append(_finding(
            "unstable_connection", "warning", "medium",
            f"avg latency {avg_latency} ms, packet loss {loss}%.",
            ("Possible unstable connection or congestion: latency is elevated and "
             "packet loss is present at the same time. Commonly Wi-Fi interference, "
             "distance from the router, or a congested link."),
            link_recommendations,
        ))
    elif loss is not None and loss > 5:
        findings.append(_finding(
            "packet_loss", "warning", "medium",
            f"packet loss {loss}% with acceptable latency.",
            "Packet loss is elevated even though latency looks fine — often a flaky Wi-Fi link or a faulty cable/port.",
            link_recommendations,
        ))
    elif avg_latency is not None and avg_latency > 150:
        if loss is None:
            findings.append(_finding(
                "high_latency", "warning", "low",
                f"avg latency {avg_latency} ms; packet-loss measurement unavailable.",
                "Latency is high, but the packet-loss measurement was unavailable, so the cause cannot be narrowed down.",
                ("Rerun the diagnosis to collect packet-loss data.",
                 "Pause large downloads/streams on the same network and retest."),
            ))
        else:
            findings.append(_finding(
                "high_latency", "warning", "medium",
                f"avg latency {avg_latency} ms with low packet loss.",
                "Latency is high with low packet loss, which usually means congestion on the path rather than a broken link.",
                ("Pause large downloads/streams on the same network and retest.",
                 "Test again at a different time of day to check for peak-hour congestion."),
            ))

    if dns_ok is False:
        findings.append(_finding(
            "dns_failure", "critical", "high",
            "DNS resolution failed.",
            "Possible DNS/resolution-related problem: names are not resolving, so sites/apps may be unreachable even though the network itself is up.",
            ("Try a public DNS server (1.1.1.1 or 8.8.8.8) in your network settings.",
             "Flush the local DNS cache and rerun the diagnosis."),
        ))
    elif dns_slow:
        findings.append(_finding(
            "slow_dns", "warning", "medium",
            f"DNS response {dns['response_ms']} ms.",
            "DNS lookups are slow, which can make every new site feel slow to start loading.",
            ("Try a public DNS server (1.1.1.1 or 8.8.8.8) in your network settings.",
             "Flush the local DNS cache and rerun the diagnosis."),
        ))

    if http_errors:
        sites = ", ".join(
            f"{w['url']} (HTTP {w['status_code']})" for w in http_errors
        )
        has_server_error = any(w["status_code"] >= 500 for w in http_errors)
        findings.append(_finding(
            "website_http_error", "warning", "medium",
            f"HTTP error response received from: {sites}.",
            ("The server responded with an HTTP 5xx error, which indicates a possible "
             "server-side problem rather than a general network outage." if has_server_error
             else "The server responded with an HTTP 4xx error. The request or access was "
             "refused; this does not indicate a general network outage."),
            (("Retry later or contact the website operator if the server error persists.",)
             if has_server_error else
             ("Verify the URL and any required sign-in or access permissions.",)),
        ))

    transport_errors = {
        "dns_resolution": (
            "website_dns_failure", "The tested website hostname could not be resolved.",
            ("Check DNS availability and verify the hostname in the URL.",),
        ),
        "timeout": (
            "website_timeout", "The website request timed out; the cause may be transient or specific to that server.",
            ("Retry the website test later and compare with another network if the timeout persists.",),
        ),
        "connection_refused": (
            "website_connection_refused", "The website host refused the connection; this is not the same as a general network outage.",
            ("Verify that the URL and service are correct, then retry later.",),
        ),
        "tls_error": (
            "website_tls_error", "The secure connection to the website could not be established.",
            ("Check the URL and device clock, then retry; avoid bypassing certificate warnings.",),
        ),
    }
    for error_type, (code, description, suggestions) in transport_errors.items():
        affected = [w["url"] for w in websites if w.get("error_type") == error_type]
        if affected:
            findings.append(_finding(
                code, "warning" if error_type != "dns_resolution" else "info", "low",
                f"{error_type} while testing: {', '.join(affected)}.",
                description,
                suggestions,
            ))

    if redirects:
        sites = ", ".join(
            f"{w['url']} (HTTP {w['status_code']})" for w in redirects
        )
        findings.append(_finding(
            "website_redirect", "info", "medium",
            f"A redirect response was returned by: {sites}.",
            "The website returned a redirect instead of a final successful response.",
            ("Check the final destination URL or retry the request.",),
        ))

    if all_sites_bad and (loss is None or loss <= 5) and (
        avg_latency is None or avg_latency <= 100
    ):
        findings.append(_finding(
            "websites_unavailable", "warning", "low",
            "All tested websites slow/unreachable despite healthy low-level network.",
            "All tested websites are slow or unreachable even though the underlying network looks healthy — possibly ISP routing or a shared upstream issue.",
            ("Test the same sites from another network to isolate the issue.",
             "Retry later — the issue may be temporary or server-side."),
        ))
    elif some_sites_bad:
        names = ", ".join(w.get("url", "unknown site") for w in site_issues)
        findings.append(_finding(
            "some_websites_affected", "info", "low",
            f"Only some sites affected: {names}.",
            f"General connectivity looks fine, but these site(s) are slow or unreachable: {names}. Could be a slow path to that server or a server-side delay.",
            ("Test the same site from another network to confirm whether the issue is local.",
             "Retry later — the issue may be temporary or server-side."),
        ))

    missing = []
    if avg_latency is None:
        missing.append("latency")
    if loss is None:
        missing.append(
            "packet-loss (ICMP unavailable)"
            if packet_loss.get("icmp_unavailable") else "packet-loss"
        )
    if dns_ok is None:
        missing.append("DNS")
    if gateway.get("reachable") is None:
        missing.append("gateway")
    if any(w.get("reachable") is None for w in websites):
        missing.append("website")
    if missing:
        findings.append(_finding(
            "measurements_inconclusive", "info", "low",
            f"Missing or inconclusive measurements: {', '.join(missing)}.",
            ("Some measurements are unavailable, so the collected results do not "
             "confirm every aspect of network health."),
            ("Rerun the diagnosis to collect the missing measurements.",
             "Check whether local firewall or network settings block diagnostic probes."),
        ))
    tool_errors = _diagnostic_tool_errors(gateway, internet, latency, packet_loss)
    if tool_errors:
        findings.append(_finding(
            "diagnostic_tool_error", "info", "high",
            "; ".join(tool_errors),
            "One or more diagnostic tools could not complete their probe. This is a tool failure, not proof that the network is down.",
            ("Check that the ping utility is installed and permitted, then rerun the affected check.",),
        ))
    if not findings:
        tested_sites = " and tested websites" if websites else ""
        findings.append(_finding(
            "healthy", "healthy", "high",
            "All available measurements are within normal range.",
            ("No significant issues detected. Connectivity, latency, packet loss, DNS"
             f"{tested_sites} look healthy."),
            ("Connection looks healthy — no action needed right now.",),
        ))

    return {"findings": findings, "gateway_icmp_note": gateway_icmp_note}


def _diagnostic_tool_errors(gateway, internet, latency, packet_loss):
    errors = []
    for label, check in (
        ("gateway ping", gateway),
        ("internet ICMP probe", internet),
        ("latency ping", latency),
        ("packet-loss ping", packet_loss),
    ):
        error_type = check.get("error_type") or (
            check.get("icmp_error_type") if label == "internet ICMP probe" else None
        )
        if error_type:
            errors.append(f"{label}: {error_type}")
    return errors


def recommend(findings):
    recommendations = [
        recommendation
        for finding in findings
        for recommendation in finding.get("recommendations", [])
    ]
    if recommendations:
        return list(dict.fromkeys(recommendations))
    return ["Connection looks healthy — no action needed right now."]


# ----------------------------------------------------------------------
# Orchestration: Measure -> Analyze -> Diagnose -> Recommend
# ----------------------------------------------------------------------

def run_full_diagnosis(external_host="8.8.8.8", dns_domain="google.com",
                        websites=None, discover_devices=False):
    websites = websites or []

    gateway = check_gateway_connectivity()
    internet = check_internet_connectivity(external_host)
    latency = measure_latency(external_host)
    packet_loss = measure_packet_loss(external_host)
    dns = measure_dns_response_time(dns_domain)
    site_results = test_websites(websites) if websites else []
    devices = discover_local_devices() if discover_devices else {
        "supported": None, "status": "skipped", "devices": [],
        "detail": "Device discovery was not requested.",
    }

    source = measurement_source()
    for check in (gateway, internet, latency, packet_loss, dns, *site_results):
        check.setdefault("source", source)
    devices.setdefault("source", source)
    health = calculate_health_score(gateway, internet, latency, packet_loss, dns, site_results)
    diagnosis = diagnose(gateway, internet, latency, packet_loss, dns, site_results)
    recommendations = recommend(diagnosis["findings"])

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "gateway": gateway,
        "internet": internet,
        "latency": latency,
        "packet_loss": packet_loss,
        "dns": dns,
        "websites": site_results,
        "devices": devices,
        "health_score": health["score"],
        "health_score_factors": health["factors"],
        "findings": diagnosis["findings"],
        "recommendations": recommendations,
    }


def build_diagnosis(
    gateway, internet, latency, packet_loss, dns, websites, devices, source,
    host_agent=None,
):
    for check in (gateway, internet, latency, packet_loss, dns, *websites):
        check.setdefault("source", source)
    devices.setdefault("source", source)
    health = calculate_health_score(gateway, internet, latency, packet_loss, dns, websites)
    diagnosis = diagnose(gateway, internet, latency, packet_loss, dns, websites)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "host_agent": host_agent,
        "gateway": gateway,
        "internet": internet,
        "latency": latency,
        "packet_loss": packet_loss,
        "dns": dns,
        "websites": websites,
        "devices": devices,
        "health_score": health["score"],
        "health_score_factors": health["factors"],
        "findings": diagnosis["findings"],
        "recommendations": recommend(diagnosis["findings"]),
    }
