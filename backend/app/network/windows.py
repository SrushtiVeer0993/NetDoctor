"""Windows-specific commands: ipconfig, tracert, netstat, netsh."""
import ipaddress
import json
import re
import statistics
import subprocess


_DEFAULT_ROUTE_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "$a=Get-NetAdapter -IncludeHidden; "
    "$i4=Get-NetIPInterface -AddressFamily IPv4; "
    "$i6=Get-NetIPInterface -AddressFamily IPv6; "
    "$r=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
    "-PolicyStore ActiveStore; "
    "$all=@(); foreach($x in $r){$n=$a|Where-Object InterfaceIndex -eq "
    "$x.InterfaceIndex|Select-Object -First 1; $m=$i4|Where-Object "
    "InterfaceIndex -eq $x.InterfaceIndex|Select-Object -First 1; "
    "if($n -and $n.Status -eq 'Up' -and $m -and $x.NextHop "
    "-and $n.Name -notmatch '(?i)docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container' "
    "-and $n.InterfaceDescription -notmatch '(?i)docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container' "
    "-and $x.NextHop -ne '0.0.0.0'){"
    "$all+=[pscustomobject]@{name=$n.Name;description=$n.InterfaceDescription;"
    "status=$n.Status;physical=[bool]$n.HardwareInterface;"
    "interface_index=[int]$n.InterfaceIndex;gateway=$x.NextHop;"
    "metric=([int]$x.RouteMetric+[int]$m.InterfaceMetric)}}}; "
    "$best=$all|Sort-Object metric|Select-Object -First 1; "
    "if($best){$c=Get-NetIPConfiguration -InterfaceIndex $best.interface_index; "
    "$v=$c.IPv4Address|Where-Object IPAddress -notlike '169.254.*'|"
    "Select-Object -First 1; $best|Add-Member -NotePropertyName local_ip "
    "-NotePropertyValue $v.IPAddress -Force; $best|Add-Member "
    "-NotePropertyName prefix -NotePropertyValue $v.PrefixLength -Force; "
    "$best|Add-Member -NotePropertyName dns "
    "-NotePropertyValue @($c.DnsServer.ServerAddresses) -Force}; "
    "$r6=Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' "
    "-PolicyStore ActiveStore; $v6=@(); foreach($x in $r6){$n=$a|"
    "Where-Object InterfaceIndex -eq $x.InterfaceIndex|Select-Object -First 1;"
    "$m=$i6|Where-Object InterfaceIndex -eq $x.InterfaceIndex|Select-Object -First 1;"
    "if($n -and $n.Status -eq 'Up' -and $m -and $x.NextHop -and $x.NextHop -ne '::'){"
    "$v6+=[pscustomobject]@{gateway=$x.NextHop;name=$n.Name;"
    "metric=([int]$x.RouteMetric+[int]$m.InterfaceMetric)}}};"
    "[pscustomobject]@{ipv4=@($best);ipv6=$v6}|ConvertTo-Json -Depth 5 -Compress"
)
_IGNORED_ADAPTERS = re.compile(
    r"docker|wsl|hyper-v|vEthernet|virtualbox|vmware|loopback|container", re.I
)


def get_default_route():
    """Return the best active Windows default route, excluding Docker/WSL adapters."""
    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                "-Command", _DEFAULT_ROUTE_SCRIPT,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = json.loads(result.stdout.decode("utf-8-sig"))
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None

    candidates = data.get("ipv4") or []
    if isinstance(candidates, dict):
        candidates = [candidates]
    candidates = [
        route for route in candidates
        if isinstance(route, dict)
        and route.get("status") == "Up"
        and route.get("gateway")
        and route.get("local_ip")
        and not _IGNORED_ADAPTERS.search(
            f"{route.get('name', '')} {route.get('description', '')}"
        )
    ]
    candidates.sort(
        key=lambda route: (int(route.get("metric", 2**31 - 1)), route.get("name", ""))
    )
    route = candidates[0] if candidates else None
    ipv6 = data.get("ipv6")
    return {
        **(route or {}),
        "gateway_ipv6": ipv6.get("gateway") if isinstance(ipv6, dict) else None,
    } if route else {
        "gateway_ipv6": ipv6.get("gateway") if isinstance(ipv6, dict) else None,
    }


def list_interfaces():
    interfaces = []
    try:
        out = subprocess.run(["ipconfig"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        blocks = re.split(r"\r?\n\r?\n", out)
        for block in blocks:
            name_m = re.search(r"^(.+?adapter.+?):", block, flags=re.MULTILINE)
            ip_m = re.search(r"IPv4 Address[ .]*:\s*([\d.]+)", block)
            if name_m and ip_m:
                interfaces.append({"name": name_m.group(1).strip(), "ip": ip_m.group(1)})
    except Exception:
        pass
    return interfaces


def get_mac_address(interface_name):
    try:
        out = subprocess.run(["getmac", "/v", "/fo", "csv"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        for line in out.splitlines()[1:]:
            fields = [f.strip('"') for f in line.split(",")]
            if len(fields) >= 3 and interface_name.lower() in fields[0].lower():
                return fields[2]
    except Exception:
        pass
    return None


def get_dns_servers():
    servers = []
    try:
        out = subprocess.run(["ipconfig", "/all"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        for m in re.finditer(r"DNS Servers[ .]*:\s*([\d.]+)", out):
            servers.append(m.group(1))
    except Exception:
        pass
    return servers


def get_wifi_info(interface_name):
    info = {"ssid": None, "signal_dbm": None, "frequency_mhz": None, "link_speed_mbps": None}
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        ssid_m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, flags=re.MULTILINE)
        signal_m = re.search(r"Signal\s*:\s*(\d+)%", out)
        rate_m = re.search(r"Receive rate \(Mbps\)\s*:\s*([\d.]+)", out)
        chan_m = re.search(r"Channel\s*:\s*(\d+)", out)
        if ssid_m:
            info["ssid"] = ssid_m.group(1).strip()
        if signal_m:
            # netsh reports signal quality as a %, not dBm — approximate mapping.
            pct = int(signal_m.group(1))
            info["signal_dbm"] = round((pct / 2) - 100)
        if rate_m:
            info["link_speed_mbps"] = float(rate_m.group(1))
        if chan_m:
            info["frequency_mhz"] = None  # channel number, not frequency; left for a future phase
    except Exception:
        pass
    return info


def traceroute(target, max_hops=30):
    hops = []
    try:
        proc = subprocess.run(
            ["tracert", "-4", "-d", "-h", str(max_hops), "-w", "2000", target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max_hops * 2 + 15,
        )
        output = proc.stdout.decode(errors="ignore")
        for line in output.splitlines():
            m = re.match(r"\s*(\d+)\s+(.*)", line)
            if not m or not m.group(1).isdigit():
                continue
            hop_num = int(m.group(1))
            rest = m.group(2)
            if "Request timed out" in rest or "*" in rest and not re.search(r"\d", rest):
                hops.append({"hop": hop_num, "ip": None, "hostname": None, "latency_ms": None, "status": "no_response"})
                continue
            ip_m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", rest)
            time_m = re.findall(r"(<\s*)?([\d]+(?:\.[\d]+)?)\s*ms", rest, re.I)
            samples = [float(value) / 2 if less_than else float(value) for less_than, value in time_m]
            hop_ip = ip_m.group(1) if ip_m else None
            if hop_ip:
                try:
                    hop_ip = str(ipaddress.IPv4Address(hop_ip))
                except ipaddress.AddressValueError:
                    hop_ip = None
            hops.append({
                "hop": hop_num,
                "ip": hop_ip,
                "hostname": None,
                "latency_ms": round(statistics.median(samples), 1) if samples else None,
                "status": "responded" if hop_ip else "no_response",
            })
        if proc.returncode and not hops:
            detail = proc.stderr.decode(errors="ignore").strip() or output.strip()
            return {"supported": True, "hops": [], "error": detail or "Traceroute returned no hop data."}
    except FileNotFoundError:
        return {"supported": False, "hops": [], "error": "tracert binary not available on this system"}
    except Exception as exc:
        return {"supported": False, "hops": [], "error": str(exc)}
    destination_reached = bool(re.search(r"\bTrace complete\.", output, re.I))
    if destination_reached:
        for hop in reversed(hops):
            if hop["ip"]:
                hop["status"] = "destination"
                break
    return {"supported": True, "hops": hops, "destination_reached": destination_reached}


def _parse_netstat_endpoint(value, remote=False):
    value = value.strip()
    if value in {"", "*:*"}:
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


def active_connections():
    conns = []
    try:
        out = subprocess.run(
            ["netstat", "-ano"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, check=True,
        ).stdout.decode(errors="ignore")
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0] not in ("TCP", "UDP"):
                continue
            proto = parts[0]
            local_ip, local_port = _parse_netstat_endpoint(parts[1])
            remote_ip, remote_port = _parse_netstat_endpoint(parts[2], remote=True)
            state = parts[3].upper() if proto == "TCP" and len(parts) > 3 else "STATELESS"
            if not local_ip:
                continue
            conns.append({
                "protocol": proto,
                "local_ip": local_ip,
                "local_port": local_port,
                "remote_ip": remote_ip,
                "remote_port": remote_port,
                "state": state,
            })
    except FileNotFoundError:
        return {"supported": False, "connections": [], "error": "netstat binary not available on this system"}
    except Exception as exc:
        return {"supported": False, "connections": [], "error": str(exc)}
    return {"supported": True, "connections": conns}
