"""Small Windows host agent for NetDoctor's predefined network diagnostics."""

import concurrent.futures
import hmac
import ipaddress
import json
import os
import re
import socket
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import islice
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SOURCE = "windows_host"
MAX_BODY_BYTES = 16_384
_TOKEN = os.environ.get("NETDOCTOR_AGENT_TOKEN", "")
_PORT = int(os.environ.get("NETDOCTOR_AGENT_PORT", "8765"))
_POWER_SHELL = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "$a=Get-NetAdapter -IncludeHidden; "
    "$i4=Get-NetIPInterface -AddressFamily IPv4; "
    "$i6=Get-NetIPInterface -AddressFamily IPv6; "
    "$r4=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
    "-PolicyStore ActiveStore; "
    "$r6=Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' "
    "-PolicyStore ActiveStore; "
    "$all=@(); foreach($r in $r4){$n=$a|Where-Object InterfaceIndex -eq "
    "$r.InterfaceIndex|Select-Object -First 1; $i=$i4|Where-Object "
    "InterfaceIndex -eq $r.InterfaceIndex|Select-Object -First 1; "
    "if($n -and $n.Status -eq 'Up' -and $i -and $r.NextHop "
    "-and $n.Name -notmatch '(?i)docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container' "
    "-and $n.InterfaceDescription -notmatch '(?i)docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container' "
    "-and $r.NextHop -ne '0.0.0.0' -and $r.NextHop -ne '::'){"
    "$all+=[pscustomobject]@{name=$n.Name;description=$n.InterfaceDescription;"
    "physical=[bool]$n.HardwareInterface;status=$n.Status;"
    "interface_index=[int]$n.InterfaceIndex;gateway=$r.NextHop;"
    "metric=([int]$r.RouteMetric+[int]$i.InterfaceMetric)}}}; "
    "$best=$all|Sort-Object metric|Select-Object -First 1; "
    "if($best){$c=Get-NetIPConfiguration -InterfaceIndex $best.interface_index; "
    "$v=$c.IPv4Address|Where-Object IPAddress -notlike '169.254.*'|"
    "Select-Object -First 1; $best|Add-Member -NotePropertyName local_ip "
    "-NotePropertyValue $v.IPAddress -Force; $best|Add-Member "
    "-NotePropertyName prefix -NotePropertyValue $v.PrefixLength -Force; "
    "$best|Add-Member -NotePropertyName dns "
    "-NotePropertyValue @($c.DnsServer.ServerAddresses) -Force}; "
    "$all6=@(); foreach($r in $r6){$n=$a|Where-Object InterfaceIndex -eq "
    "$r.InterfaceIndex|Select-Object -First 1; $i=$i6|Where-Object "
    "InterfaceIndex -eq $r.InterfaceIndex|Select-Object -First 1; "
    "if($n -and $n.Status -eq 'Up' -and $i -and $r.NextHop -and $r.NextHop -ne '::'){"
    "$all6+=[pscustomobject]@{gateway=$r.NextHop;name=$n.Name;"
    "metric=([int]$r.RouteMetric+[int]$i.InterfaceMetric)}}}; "
    "[pscustomobject]@{ipv4=@($best);ipv6=$all6}|ConvertTo-Json -Depth 5 -Compress"
)
_NEIGHBORS_PS = (
    "Get-NetNeighbor -AddressFamily IPv4 -ErrorAction Stop | "
    "Select-Object IPAddress,LinkLayerAddress,State,InterfaceIndex,InterfaceAlias | "
    "ConvertTo-Json -Depth 3 -Compress"
)
_SPEEDTEST_RUNS = 3
_SPEEDTEST_METHODOLOGY = (
    "Three single-stream HTTP transfers to Cloudflare speed test endpoints; "
    "download and upload report the median measured Mbps. Latency is an "
    "unloaded ICMP measurement; jitter is mean consecutive-ping variation. "
    "This is an estimate, not a multi-connection ISP speed test."
)
class AgentError(ValueError):
    pass


def _run_powershell(script):
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return json.loads(result.stdout.decode("utf-8-sig"))


def _get_network():
    data = _run_powershell(_POWER_SHELL)
    if not isinstance(data, dict):
        raise OSError("Windows did not return an active network configuration.")
    routes = data.get("ipv4") or []
    if isinstance(routes, dict):
        routes = [routes]
    ignored = re.compile(r"docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container", re.I)
    routes = [
        route for route in routes
        if isinstance(route, dict) and not ignored.search(
            f"{route.get('name', '')} {route.get('description', '')}"
        )
        and route.get("status") == "Up"
        and route.get("gateway") and route.get("local_ip")
    ]
    if not routes:
        # Get-NetRoute/Get-NetAdapter can be unavailable in restricted Windows
        # sessions. The built-in route.exe still exposes the active default
        # route and its source interface without requiring CIM access.
        return _get_network_from_route_table()
    routes.sort(key=lambda route: (int(route.get("metric", 2**31 - 1)), route.get("name", "")))
    route = routes[0] if routes else None
    ipv6 = data.get("ipv6")
    if isinstance(ipv6, list):
        ipv6 = min(ipv6, key=lambda entry: entry.get("metric", 2**31 - 1), default=None)
    connection_type = "unknown"
    if route:
        name = f"{route.get('name', '')} {route.get('description', '')}".lower()
        if "vpn" in name or "wireguard" in name or "tunnel" in name:
            connection_type = "vpn"
        elif "wi-fi" in name or "wireless" in name or "wlan" in name:
            connection_type = "wifi"
        elif route.get("physical"):
            connection_type = "ethernet"
        else:
            connection_type = "virtual"

    network = None
    if route:
        try:
            network = str(ipaddress.IPv4Network(
                f"{route['local_ip']}/{int(route['prefix'])}", strict=False
            ))
        except (KeyError, ValueError, TypeError):
            route = None
    summary = {
        "interface_name": route.get("name") if route else None,
        "connection_type": connection_type if route else "unknown",
        "local_ip": route.get("local_ip") if route else None,
        "subnet": network,
        "gateway": route.get("gateway") if route else None,
        "gateway_ip": route.get("gateway") if route else None,
        "gateway_ipv6": ipv6.get("gateway") if isinstance(ipv6, dict) else None,
        "interface_index": route.get("interface_index") if route else None,
        "dns_servers": route.get("dns", []) if route else [],
        "source": SOURCE,
    }
    return summary


def _get_network_from_route_table():
    result = subprocess.run(
        ["route.exe", "print", "-4"], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=10, check=True,
    )
    output = result.stdout.decode(errors="ignore")
    candidates = []
    for line in output.splitlines():
        match = re.match(
            r"\s*0\.0\.0\.0\s+0\.0\.0\.0\s+"
            r"(\d{1,3}(?:\.\d{1,3}){3})\s+"
            r"(\d{1,3}(?:\.\d{1,3}){3})\s+(\d+)\s*$",
            line,
        )
        if match:
            try:
                gateway = str(ipaddress.IPv4Address(match.group(1)))
                local_ip = str(ipaddress.IPv4Address(match.group(2)))
            except ipaddress.AddressValueError:
                continue
            candidates.append((int(match.group(3)), gateway, local_ip))
    if not candidates:
        raise OSError("Windows did not return an active IPv4 default route.")
    _, gateway, local_ip = min(candidates)

    adapter_name = None
    subnet = None
    ipconfig = subprocess.run(
        ["ipconfig.exe", "/all"], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=10, check=True,
    ).stdout.decode(errors="ignore")
    sections = re.split(r"(?m)^\s*((?:Ethernet|Wireless LAN) adapter .+):\s*$", ipconfig)
    for index in range(1, len(sections), 2):
        name = sections[index]
        details = sections[index + 1] if index + 1 < len(sections) else ""
        if local_ip not in details:
            continue
        adapter_name = name.rsplit(" ", 1)[-1]
        mask = re.search(
            r"(?mi)^\s*Subnet Mask[ .]*:\s*(\d{1,3}(?:\.\d{1,3}){3})\s*$",
            details,
        )
        if mask:
            try:
                subnet = str(ipaddress.IPv4Network(f"{local_ip}/{mask.group(1)}", strict=False))
            except ipaddress.AddressValueError:
                subnet = None
        break

    connection_type = "unknown"
    if adapter_name and re.search(r"wi-?fi|wireless|wlan", adapter_name, re.I):
        connection_type = "wifi"
    elif adapter_name and re.search(r"ethernet", adapter_name, re.I):
        connection_type = "ethernet"
    return {
        "interface_name": adapter_name,
        "connection_type": connection_type,
        "local_ip": local_ip,
        "subnet": subnet,
        "gateway": gateway,
        "gateway_ip": gateway,
        "gateway_ipv6": None,
        "interface_index": None,
        "dns_servers": [],
        "source": SOURCE,
    }


def _ping(target, count, timeout_ms):
    valid_hostname = bool(re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
        r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
        target,
    ))
    if not valid_hostname:
        try:
            ipaddress.ip_address(target)
        except ValueError:
            raise AgentError("Invalid ping target.") from None
    try:
        result = subprocess.run(
            ["ping.exe", "-n", str(count), "-w", str(timeout_ms), target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=count * timeout_ms / 1000 + 3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {
            "sent": 0, "received": 0, "samples": [],
            "error": "Ping timed out.", "error_type": "timeout",
        }
    except PermissionError as exc:
        return {
            "sent": 0, "received": 0, "samples": [],
            "error": str(exc), "error_type": "permission_denied",
        }
    except FileNotFoundError as exc:
        return {
            "sent": 0, "received": 0, "samples": [],
            "error": str(exc), "error_type": "unsupported",
        }
    except OSError as exc:
        return {
            "sent": 0, "received": 0, "samples": [],
            "error": str(exc), "error_type": "failed",
        }
    if result.returncode > 1:
        detail = result.stderr.decode(errors="ignore") or result.stdout.decode(errors="ignore")
        return {
            "sent": 0, "received": 0, "samples": [],
            "error": detail.strip() or "Ping utility failed.",
            "error_type": "tool_error",
        }
    output = result.stdout.decode(errors="ignore")
    samples = [
        float(value) for value in re.findall(r"time[=<]([\d.]+)\s*ms", output, re.I)
    ]
    return {"sent": count, "received": min(len(samples), count), "samples": samples[:count]}


def _packet_loss(target, count=5):
    result = _ping(target, count, 1200)
    sent = result["sent"]
    received = result["received"]
    return {
        "target": target, "sent": sent, "received": received,
        # With no echo replies we cannot distinguish packet loss from an ICMP
        # filter, so do not present 100% as a measured loss rate.
        "loss_pct": round((sent - received) / sent * 100, 1)
        if sent and received > 0 else None,
        "icmp_unavailable": sent > 0 and received == 0,
        "source": SOURCE,
        "error_type": result.get("error_type"),
        "error": result.get("error"),
    }


def _latency(target, count=4):
    result = _ping(target, count, 1200)
    samples = result["samples"]
    average = sum(samples) / len(samples) if samples else None
    return {
        "target": target,
        "min_ms": round(min(samples), 1) if samples else None,
        "max_ms": round(max(samples), 1) if samples else None,
        "avg_ms": round(average, 1) if average is not None else None,
        "jitter_ms": round(
            sum(abs(sample - average) for sample in samples) / len(samples), 1
        ) if len(samples) > 1 else (0.0 if samples else None),
        "sent": result["sent"], "received": result["received"],
        "samples": [round(sample, 1) for sample in samples],
        "source": SOURCE,
        "error_type": result.get("error_type"),
        "error": result.get("error"),
    }


def _monitor_measurement(target):
    # One ping run feeds both values so latency and loss describe the same window.
    result = _ping(target, 3, 800)
    samples = result["samples"]
    sent = result["sent"]
    received = result["received"]
    dns_start = time.perf_counter()
    try:
        socket.gethostbyname("google.com")
        dns_success = True
        dns_ms = round((time.perf_counter() - dns_start) * 1000, 1)
    except OSError:
        dns_success = False
        dns_ms = None

    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=2):
            internet = True
    except OSError:
        # A failed TCP probe alone is not sufficient evidence of an outage.
        internet = None

    return {
        "source": SOURCE,
        "target": target,
        "latency_ms": round(sum(samples) / len(samples), 1) if samples else None,
        "packet_loss_pct": round((sent - received) / sent * 100, 1)
        if sent and received > 0 else None,
        "sent": sent,
        "received": received,
        "icmp_unavailable": received == 0,
        "dns_ms": dns_ms,
        "dns_success": dns_success,
        "internet": internet,
    }


def _parse_netstat_endpoint(value, remote=False):
    value = value.strip()
    if value in {"", "*:*", "*.*"}:
        return None, None
    if value.startswith("[") and "]:" in value:
        address, port = value[1:].split("]:", 1)
    else:
        address, separator, port = value.rpartition(":")
        if not separator:
            return None, None
    if remote and address in {"*", "0.0.0.0", "::"} and port == "0":
        return None, None
    return address, port if port.isdigit() else None


def _connections():
    result = subprocess.run(
        ["netstat.exe", "-ano"], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=10, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    connections = []
    for line in result.stdout.decode(errors="ignore").splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0].upper() not in {"TCP", "UDP"}:
            continue
        protocol = fields[0].upper()
        local_ip, local_port = _parse_netstat_endpoint(fields[1])
        remote_ip, remote_port = _parse_netstat_endpoint(fields[2], remote=True)
        if not local_ip:
            continue
        state = fields[3].upper() if protocol == "TCP" and len(fields) > 3 else "STATELESS"
        connections.append({
            "protocol": protocol,
            "local_ip": local_ip,
            "local_port": local_port,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "state": state,
        })
        if len(connections) >= 5000:
            break
    return {"source": SOURCE, "connections": connections}


def _gateway(network=None):
    network = network or _get_network()
    gateway = network.get("gateway_ip")
    if not gateway:
        return {
            "reachable": None, "gateway_ip": None, "avg_ms": None,
            "icmp_unavailable": True, "source": SOURCE,
            "detail": "No active IPv4 default gateway is available.",
        }
    result = _ping(gateway, 3, 1200)
    samples = result["samples"]
    return {
        "reachable": None if result.get("error_type") else bool(samples),
        "gateway_ip": gateway,
        "avg_ms": round(sum(samples) / len(samples), 1) if samples else None,
        "icmp_unavailable": not bool(samples), "source": SOURCE,
        "error_type": result.get("error_type"),
        "detail": result.get("error"),
        "interface_name": network["interface_name"],
        "interface_type": network["connection_type"],
    }


def _internet(target):
    start = time.perf_counter()
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=3):
            reachable = True
    except OSError:
        reachable = None
    icmp = _ping(target, 2, 1200)
    icmp_samples = icmp["samples"]
    return {
        "reachable": reachable,
        "target": target,
        "avg_ms": round((time.perf_counter() - start) * 1000, 1) if reachable else None,
        "method": "tcp_connect_to_public_ip",
        "icmp_reachable": bool(icmp_samples),
        "icmp_unavailable": not bool(icmp_samples),
        "icmp_avg_ms": round(sum(icmp_samples) / len(icmp_samples), 1) if icmp_samples else None,
        "icmp_error_type": icmp.get("error_type"),
        "icmp_detail": icmp.get("error"),
        "source": SOURCE,
        "detail": None if reachable else "The TCP probe did not complete; this alone does not prove an internet outage.",
    }


def _dns(domain):
    start = time.perf_counter()
    try:
        addresses = socket.getaddrinfo(domain, None, family=socket.AF_UNSPEC)
        ip = addresses[0][4][0]
        return {
            "domain": domain, "resolved_ip": ip,
            "response_ms": round((time.perf_counter() - start) * 1000, 1),
            "success": True, "source": SOURCE,
        }
    except OSError as exc:
        return {
            "domain": domain, "resolved_ip": None, "response_ms": None,
            "success": False, "error": str(exc), "source": SOURCE,
        }


def _read_neighbors_from_arp(network_summary):
    local_ip = network_summary.get("local_ip")
    result = subprocess.run(
        ["arp.exe", "-a", "-N", local_ip],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True,
    )
    network = ipaddress.IPv4Network(network_summary["subnet"], strict=False)
    entries = []
    for line in result.stdout.decode(errors="ignore").splitlines():
        match = re.match(
            r"\s*(\d{1,3}(?:\.\d{1,3}){3})\s+"
            r"((?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})\s+(?:dynamic|static)\s*$",
            line, re.I,
        )
        if not match:
            continue
        try:
            address = ipaddress.IPv4Address(match.group(1))
        except ipaddress.AddressValueError:
            continue
        if (
            address not in network or str(address) == local_ip
            or (network.prefixlen < 31 and address in {network.network_address, network.broadcast_address})
        ):
            continue
        entries.append({
            "InterfaceIndex": network_summary.get("interface_index"),
            "IPAddress": str(address),
            "LinkLayerAddress": match.group(2),
        })
    return entries


def _website(url):
    start = time.perf_counter()
    try:
        parsed = urlsplit(url)
        try:
            literal_ip = ipaddress.ip_address(parsed.hostname or "")
            if not literal_ip.is_global:
                raise AgentError("Website checks may only target public addresses.")
        except ValueError:
            addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global for item in addresses
            ):
                raise AgentError("Website checks may only target public addresses.")
        request = Request(url, method="GET", headers={"User-Agent": "NetDoctor/1.0"})

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, new_url):
                return None

        with build_opener(NoRedirect()).open(request, timeout=6) as response:
            status = response.status
    except Exception as exc:
        status = getattr(exc, "code", None)
        if status is None:
            return {
                "url": url, "reachable": False, "status_code": None,
                "successful_request": False, "http_category": None,
                "error_type": "request_error", "response_ms": None,
                "error": str(exc), "source": SOURCE,
            }
    category = (
        "success" if 200 <= status < 300 else
        "redirect" if 300 <= status < 400 else
        "client_error" if 400 <= status < 500 else
        "server_error" if 500 <= status < 600 else "other"
    )
    return {
        "url": url, "reachable": True, "status_code": status,
        "successful_request": 200 <= status < 300,
        "http_category": category,
        "response_ms": round((time.perf_counter() - start) * 1000, 1),
        "source": SOURCE,
    }


def _measure_download(size_bytes):
    start = time.perf_counter()
    request = Request(
        f"https://speed.cloudflare.com/__down?bytes={size_bytes}",
        headers={"User-Agent": "NetDoctor/1.0", "Accept-Encoding": "identity"},
    )
    with build_opener().open(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"Download endpoint returned HTTP {response.status}.")
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
    elapsed = time.perf_counter() - start
    if total != size_bytes:
        raise OSError(f"Expected {size_bytes} download bytes, received {total}.")
    return {"success": True, "bytes": total, "seconds": elapsed, "mbps": round(total * 8 / elapsed / 1_000_000, 2)}


def _measure_upload(size_bytes):
    payload = os.urandom(size_bytes)
    start = time.perf_counter()
    request = Request(
        "https://speed.cloudflare.com/__up", data=payload,
        headers={"User-Agent": "NetDoctor/1.0", "Content-Type": "application/octet-stream"},
        method="POST",
    )
    with build_opener().open(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"Upload endpoint returned HTTP {response.status}.")
        response.read()
    elapsed = time.perf_counter() - start
    return {"success": True, "bytes": size_bytes, "seconds": elapsed, "mbps": round(size_bytes * 8 / elapsed / 1_000_000, 2)}


def _measure_transfer_runs(measure, size_bytes):
    runs = []
    errors = []
    for _ in range(_SPEEDTEST_RUNS):
        try:
            runs.append(measure(size_bytes))
        except Exception as exc:
            errors.append(str(exc))
            break
    if errors:
        return {
            "success": False, "mbps": None,
            "error": "; ".join(errors),
            "samples_mbps": [run["mbps"] for run in runs],
        }
    return {
        "success": True,
        "bytes": size_bytes,
        "seconds": round(statistics.median(run["seconds"] for run in runs), 3),
        "mbps": round(statistics.median(run["mbps"] for run in runs), 2),
        "samples_mbps": [run["mbps"] for run in runs],
    }


def _speedtest(options):
    download = _measure_transfer_runs(_measure_download, options["download_bytes"])
    upload = _measure_transfer_runs(_measure_upload, options["upload_bytes"])
    ping = _ping("1.1.1.1", 6, 1200)
    samples = ping["samples"]
    latency = round(sum(samples) / len(samples), 1) if samples else None
    jitter = (
        round(sum(abs(right - left) for left, right in zip(samples, samples[1:])) / (len(samples) - 1), 1)
        if len(samples) > 1 else None
    )
    return {
        "source": SOURCE,
        "methodology": _SPEEDTEST_METHODOLOGY,
        "download": download,
        "upload": upload,
        "latency_ms": latency,
        "jitter_ms": jitter,
    }


def _discovery(max_hosts):
    try:
        network_summary = _get_network()
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        return {
            "supported": False, "status": "failed", "devices": [],
            "detail": f"Could not detect the active Windows network: {exc}",
            "source": SOURCE,
        }
    subnet_text = network_summary.get("subnet")
    local_ip = network_summary.get("local_ip")
    interface_name = network_summary.get("interface_name")
    if not subnet_text or not local_ip or not interface_name:
        return {
            "supported": False, "status": "skipped", "devices": [],
            "detail": "No active IPv4 interface and subnet were available for host discovery.",
            "source": SOURCE,
        }
    network = ipaddress.IPv4Network(subnet_text, strict=False)
    addresses = list(islice(
        (address for address in network.hosts() if str(address) != local_ip),
        max_hosts,
    ))
    total_hosts = max(
        0,
        network.num_addresses - (2 if network.prefixlen < 31 else 0) - 1,
    )
    scan_complete = len(addresses) >= total_hosts
    errors = []
    error_types = set()
    responsive_addresses = set()

    def read_failure(status, detail):
        partial_devices = [
            {"ip": address, "mac": None, "status": "responsive"}
            for address in sorted(responsive_addresses)
        ]
        return {
            "supported": bool(partial_devices),
            "status": "partial" if partial_devices else status,
            "detail": detail,
            "scanned_hosts": len(addresses),
            "total_hosts": total_hosts,
            "scan_complete": False,
            "subnet": subnet_text,
            "interface_name": interface_name,
            "devices": partial_devices[:max_hosts],
            "source": SOURCE,
        }

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            futures = {
                executor.submit(_ping, str(address), 1, 250): address
                for address in addresses
            }
            for future in concurrent.futures.as_completed(futures, timeout=30):
                result = future.result()
                if result.get("received", 0) > 0:
                    responsive_addresses.add(str(futures[future]))
                if result.get("error"):
                    errors.append(result["error"])
                    error_types.add(result.get("error_type", "failed"))
    except concurrent.futures.TimeoutError:
        errors.append("Some local probes timed out.")
    except PermissionError:
        return read_failure(
            "permission_denied",
            "Permission was denied while probing the local network.",
        )
    try:
        raw = _run_powershell(_NEIGHBORS_PS)
        entries = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        try:
            entries = _read_neighbors_from_arp(network_summary)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return read_failure(
                "failed",
                f"Could not read Windows neighbors using PowerShell or arp.exe: {exc}",
            )
    devices = []
    for entry in entries:
        if entry.get("InterfaceIndex") is None:
            continue
        if entry.get("InterfaceIndex") != network_summary.get("interface_index"):
            continue
        try:
            address = ipaddress.IPv4Address(entry.get("IPAddress", ""))
        except ipaddress.AddressValueError:
            continue
        mac = str(entry.get("LinkLayerAddress", "")).lower()
        if (
            address not in network
            or (network.prefixlen < 31 and address in {network.network_address, network.broadcast_address})
            or not re.fullmatch(r"(?:[0-9a-f]{2}-){5}[0-9a-f]{2}", mac)
            or mac in {"00-00-00-00-00-00", "ff-ff-ff-ff-ff-ff"}
        ):
            continue
        if str(address) != local_ip:
            address_text = str(address)
            devices.append({
                "ip": address_text,
                "mac": mac.replace("-", ":"),
                "status": "responsive" if address_text in responsive_addresses else "neighbor_cache",
            })
    unique = {device["ip"]: device for device in devices}
    for address in responsive_addresses:
        unique[address] = {**unique.get(address, {}), "ip": address,
                           "mac": unique.get(address, {}).get("mac"),
                           "status": "responsive"}
    devices = list(unique.values())
    partial = bool(errors) or not scan_complete
    if errors and not devices and "permission_denied" in error_types:
        status = "permission_denied"
    elif errors and not devices and "unsupported" in error_types:
        status = "unsupported"
    elif partial:
        status = "partial"
    else:
        status = "success" if devices else "empty"
    return {
        "supported": True,
        "status": status,
        "detail": (
            f"Neighbor table returned {len(devices)} device(s); this is not a complete inventory."
            if devices and not partial else
            f"Partial discovery: scanned {len(addresses)} of {total_hosts} local addresses. {' '.join(dict.fromkeys(errors))}".strip()
            if partial else
            f"No entries were present in the active interface neighbor table. {' '.join(dict.fromkeys(errors))}".strip()
        ),
        "scanned_hosts": len(addresses),
        "total_hosts": total_hosts,
        "scan_complete": scan_complete,
        "subnet": subnet_text,
        "interface_name": interface_name,
        "devices": devices[:max_hosts],
        "source": SOURCE,
    }


def _valid_request(operation, payload):
    if not isinstance(payload, dict):
        raise AgentError("Request body must be a JSON object.")
    if operation == "interface":
        if payload:
            raise AgentError("The interface operation accepts no options.")
        return {}
    if operation == "connections":
        if payload:
            raise AgentError("The connections operation accepts no options.")
        return {}
    if operation == "discovery":
        if set(payload) - {"max_hosts"}:
            raise AgentError("Unexpected discovery request fields.")
        maximum = payload.get("max_hosts", 32)
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 1024:
            raise AgentError("max_hosts must be between 1 and 1024.")
        return {"max_hosts": maximum}
    if operation == "speedtest":
        if set(payload) - {"download_bytes", "upload_bytes"}:
            raise AgentError("Unexpected speed-test request fields.")
        download_bytes = payload.get("download_bytes", 10_000_000)
        upload_bytes = payload.get("upload_bytes", 5_000_000)
        if not isinstance(download_bytes, int) or isinstance(download_bytes, bool) or not 100_000 <= download_bytes <= 100_000_000:
            raise AgentError("download_bytes must be between 100 KB and 100 MB.")
        if not isinstance(upload_bytes, int) or isinstance(upload_bytes, bool) or not 100_000 <= upload_bytes <= 25_000_000:
            raise AgentError("upload_bytes must be between 100 KB and 25 MB.")
        return {"download_bytes": download_bytes, "upload_bytes": upload_bytes}
    if operation == "monitor":
        if set(payload) - {"target"}:
            raise AgentError("Unexpected monitoring request fields.")
        target = payload.get("target", "8.8.8.8")
        valid_hostname = isinstance(target, str) and bool(re.fullmatch(
            r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
            r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
            target,
        ))
        if not valid_hostname:
            try:
                ipaddress.ip_address(target)
            except (ValueError, TypeError):
                raise AgentError("Invalid monitoring target.") from None
        return {"target": target}
    if operation != "diagnostics":
        raise AgentError("Unsupported operation.")
    allowed = {"external_host", "dns_domain", "websites", "discover_devices", "max_hosts"}
    if set(payload) - allowed:
        raise AgentError("Unexpected diagnostics request fields.")
    host = payload.get("external_host", "8.8.8.8")
    valid_hostname = isinstance(host, str) and bool(re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
        r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
        host,
    ))
    if not valid_hostname:
        try:
            ipaddress.ip_address(host)
        except (ValueError, TypeError):
            raise AgentError("Invalid external diagnostic target.") from None
    domain = payload.get("dns_domain", "google.com")
    if not isinstance(domain, str) or not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
        r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
        domain,
    ):
        raise AgentError("Invalid DNS domain.")
    websites = payload.get("websites", [])
    if not isinstance(websites, list) or len(websites) > 10:
        raise AgentError("At most 10 website checks are supported.")
    for website in websites:
        parsed = urlsplit(website) if isinstance(website, str) else None
        if (
            parsed is None or parsed.scheme not in {"http", "https"}
            or not parsed.hostname or parsed.username or parsed.password
            or len(website) > 2048
        ):
            raise AgentError("Website checks require valid HTTP or HTTPS URLs.")
    discover = payload.get("discover_devices", False)
    maximum = payload.get("max_hosts", 32)
    if not isinstance(discover, bool):
        raise AgentError("discover_devices must be a boolean.")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 64:
        raise AgentError("max_hosts must be between 1 and 64.")
    return {
        "external_host": host, "dns_domain": domain, "websites": websites,
        "discover_devices": discover, "max_hosts": maximum,
    }


def _diagnostics(options):
    network = _get_network()
    gateway = _gateway(network)
    internet = _internet(options["external_host"])
    latency = _latency(options["external_host"])
    packet_loss = _packet_loss(options["external_host"])
    dns = _dns(options["dns_domain"])
    websites = [_website(url) for url in options["websites"]]
    devices = (
        _discovery(options["max_hosts"]) if options["discover_devices"] else {
            "supported": None, "status": "skipped", "devices": [],
            "detail": "Device discovery was not requested.", "source": SOURCE,
        }
    )
    for check in (gateway, internet, latency, packet_loss, dns, *websites):
        check.setdefault("source", SOURCE)
    return {
        "source": SOURCE,
        "gateway": gateway,
        "internet": internet,
        "latency": latency,
        "packet_loss": packet_loss,
        "dns": dns,
        "websites": websites,
        "devices": devices,
        "interface": network,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "NetDoctorHostAgent/1"
    timeout = 10

    def _json(self, status, result):
        body = json.dumps(result, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._handle_post()

    def _handle_post(self):
        operation = self.path.removeprefix("/v1/")
        if self.path not in {"/v1/diagnostics", "/v1/interface", "/v1/discovery", "/v1/speedtest", "/v1/monitor", "/v1/connections"}:
            self._json(404, {"detail": "Not found."})
            return
        expected = f"Bearer {_TOKEN}".encode()
        provided = self.headers.get("Authorization", "").encode()
        if not _TOKEN or not hmac.compare_digest(provided, expected):
            self._json(401, {"detail": "Unauthorized."})
            return
        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise AgentError("Invalid content length.") from None
            if length < 1 or length > MAX_BODY_BYTES:
                raise AgentError("Request body size is invalid.")
            payload = json.loads(self.rfile.read(length))
            options = _valid_request(operation, payload)
            if operation == "interface":
                result = _get_network()
            elif operation == "discovery":
                result = _discovery(options["max_hosts"])
            elif operation == "speedtest":
                result = _speedtest(options)
            elif operation == "monitor":
                result = _monitor_measurement(options["target"])
            elif operation == "connections":
                result = _connections()
            else:
                result = _diagnostics(options)
            self._json(200, result)
        except (AgentError, json.JSONDecodeError) as exc:
            self._json(400, {"detail": str(exc)})
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self._json(503, {"detail": f"Host diagnostic operation failed: {exc}"})

    def log_message(self, *_args):
        return


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def process_request(self, request, client_address):
        if not _REQUEST_SLOTS.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            _REQUEST_SLOTS.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            _REQUEST_SLOTS.release()


_REQUEST_SLOTS = threading.BoundedSemaphore(4)


def main():
    if len(_TOKEN) < 32:
        raise SystemExit("Set NETDOCTOR_AGENT_TOKEN to a random secret of at least 32 characters.")
    if not 1 <= _PORT <= 65535:
        raise SystemExit("NETDOCTOR_AGENT_PORT must be between 1 and 65535.")
    server = BoundedThreadingHTTPServer(("0.0.0.0", _PORT), Handler)
    print(f"NetDoctor Windows host agent listening on 0.0.0.0:{_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
