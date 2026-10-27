"""Linux-specific commands: ip, traceroute, ss."""
import re
import socket
import subprocess


def list_interfaces():
    interfaces = []
    try:
        out = subprocess.run(["ip", "-o", "addr", "show"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        seen = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[1]
            if name in seen or name == "lo":
                continue
            if "inet" not in parts:
                continue
            idx = parts.index("inet") if "inet" in parts else None
            ip = parts[idx + 1].split("/")[0] if idx is not None else None
            seen.add(name)
            interfaces.append({"name": name, "ip": ip})
    except Exception:
        pass
    return interfaces


def get_mac_address(interface_name):
    try:
        with open(f"/sys/class/net/{interface_name}/address") as f:
            return f.read().strip()
    except Exception:
        return None


def get_dns_servers():
    servers = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.startswith("nameserver"):
                    servers.append(line.split()[1])
    except Exception:
        pass
    return servers


def get_wifi_info(interface_name):
    """Best-effort SSID/signal via `iw`. Returns Nones if unavailable/unsupported."""
    info = {"ssid": None, "signal_dbm": None, "frequency_mhz": None, "link_speed_mbps": None}
    try:
        out = subprocess.run(["iw", "dev", interface_name, "link"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3).stdout.decode(errors="ignore")
        ssid_m = re.search(r"SSID:\s*(.+)", out)
        signal_m = re.search(r"signal:\s*(-?\d+)\s*dBm", out)
        freq_m = re.search(r"freq:\s*(\d+)", out)
        rate_m = re.search(r"tx bitrate:\s*([\d.]+)\s*MBit/s", out)
        if ssid_m:
            info["ssid"] = ssid_m.group(1).strip()
        if signal_m:
            info["signal_dbm"] = int(signal_m.group(1))
        if freq_m:
            info["frequency_mhz"] = int(freq_m.group(1))
        if rate_m:
            info["link_speed_mbps"] = float(rate_m.group(1))
    except Exception:
        pass
    return info


def traceroute(target, max_hops=30):
    hops = []
    try:
        proc = subprocess.run(
            ["traceroute", "-n", "-m", str(max_hops), "-w", "2", target],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max_hops * 2 + 10,
        )
        output = proc.stdout.decode(errors="ignore")
        for line in output.splitlines():
            m = re.match(r"\s*(\d+)\s+(.*)", line)
            if not m:
                continue
            hop_num = int(m.group(1))
            rest = m.group(2)
            if "* * *" in rest or rest.strip() == "*":
                hops.append({"hop": hop_num, "ip": None, "hostname": None, "latency_ms": None, "status": "no_response"})
                continue
            ip_m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", rest)
            time_m = re.findall(r"([\d.]+)\s*ms", rest)
            hops.append({
                "hop": hop_num,
                "ip": ip_m.group(1) if ip_m else None,
                "hostname": None,
                "latency_ms": round(float(time_m[0]), 1) if time_m else None,
                "status": "responded" if ip_m else "no_response",
            })
    except FileNotFoundError:
        return {"supported": False, "hops": [], "error": "traceroute binary not available on this system"}
    except Exception as exc:
        return {"supported": False, "hops": [], "error": str(exc)}
    return {"supported": True, "hops": hops}


def active_connections():
    def endpoint(value, remote=False):
        if value in {"", "*:*"}:
            return None, None
        if value.startswith("[") and "]:" in value:
            address, port = value[1:].split("]:", 1)
        else:
            address, separator, port = value.rpartition(":")
            if not separator:
                return None, None
        if remote and address in {"*", "0.0.0.0", "::"} and port in {"0", "*"}:
            return None, None
        return address, port if port.isdigit() else None

    conns = []
    try:
        out = subprocess.run(["ss", "-tunap"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5).stdout.decode(errors="ignore")
        lines = out.splitlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) < 6:
                continue
            proto = parts[0].upper()
            state = parts[1].upper() if proto == "TCP" else "STATELESS"
            state = {
                "ESTAB": "ESTABLISHED", "LISTEN": "LISTENING",
                "TIME-WAIT": "TIME_WAIT", "CLOSE-WAIT": "CLOSE_WAIT",
                "FIN-WAIT-1": "FIN_WAIT_1", "FIN-WAIT-2": "FIN_WAIT_2",
                "SYN-SENT": "SYN_SENT", "SYN-RECV": "SYN_RECV",
            }.get(state, state)
            local = parts[4] if len(parts) > 4 else ""
            remote = parts[5] if len(parts) > 5 else ""
            local_ip, local_port = endpoint(local)
            remote_ip, remote_port = endpoint(remote, remote=True)
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
        return {"supported": False, "connections": [], "error": "ss binary not available on this system"}
    except Exception as exc:
        return {"supported": False, "connections": [], "error": str(exc)}
    return {"supported": True, "connections": conns}
