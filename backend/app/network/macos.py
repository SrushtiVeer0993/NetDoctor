"""macOS-specific commands: ifconfig, traceroute, netstat."""
import re
import subprocess


def list_interfaces():
    interfaces = []
    try:
        out = subprocess.run(["ifconfig"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        blocks = re.split(r"\n(?=\S)", out)
        for block in blocks:
            name_m = re.match(r"^(\w+):", block)
            ip_m = re.search(r"inet (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", block)
            if name_m and ip_m and name_m.group(1) != "lo0":
                interfaces.append({"name": name_m.group(1), "ip": ip_m.group(1)})
    except Exception:
        pass
    return interfaces


def get_mac_address(interface_name):
    try:
        out = subprocess.run(["ifconfig", interface_name], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        m = re.search(r"ether ([0-9a-f:]{17})", out)
        return m.group(1) if m else None
    except Exception:
        return None


def get_dns_servers():
    servers = []
    try:
        out = subprocess.run(["scutil", "--dns"], stdout=subprocess.PIPE, timeout=5).stdout.decode(errors="ignore")
        servers = list(dict.fromkeys(re.findall(r"nameserver\[\d+\]\s*:\s*([\d.]+)", out)))
    except Exception:
        pass
    return servers


def get_wifi_info(interface_name):
    info = {"ssid": None, "signal_dbm": None, "frequency_mhz": None, "link_speed_mbps": None}
    airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    try:
        out = subprocess.run([airport, "-I"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5).stdout.decode(errors="ignore")
        ssid_m = re.search(r"\bSSID:\s*(.+)", out)
        rssi_m = re.search(r"agrCtlRSSI:\s*(-?\d+)", out)
        rate_m = re.search(r"lastTxRate:\s*(\d+)", out)
        chan_m = re.search(r"channel:\s*(\d+)", out)
        if ssid_m:
            info["ssid"] = ssid_m.group(1).strip()
        if rssi_m:
            info["signal_dbm"] = int(rssi_m.group(1))
        if rate_m:
            info["link_speed_mbps"] = float(rate_m.group(1))
        if chan_m:
            info["frequency_mhz"] = None  # channel number, not frequency
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
            if "* * *" in rest:
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
    conns = []
    try:
        for protocol in ("tcp", "udp"):
            out = subprocess.run(
                ["netstat", "-anv", "-p", protocol], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=5, check=True,
            ).stdout.decode(errors="ignore")
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].lower() not in {f"{protocol}4", f"{protocol}6"}:
                    continue
                local, remote = parts[3], parts[4]
                state = parts[5].upper() if protocol == "tcp" and len(parts) > 5 else "STATELESS"
                state = {"LISTEN": "LISTENING", "TIME-WAIT": "TIME_WAIT"}.get(state, state)
                local_ip, _, local_port = local.rpartition(".")
                remote_ip, _, remote_port = remote.rpartition(".")
                if not local_ip:
                    continue
                if remote_ip in {"*", "0.0.0.0", "::"} and remote_port in {"*", "0"}:
                    remote_ip = remote_port = None
                conns.append({
                    "protocol": protocol.upper(),
                    "local_ip": local_ip,
                    "local_port": local_port if local_port.isdigit() else None,
                    "remote_ip": remote_ip,
                    "remote_port": remote_port if remote_port and remote_port.isdigit() else None,
                    "state": state,
                })
    except FileNotFoundError:
        return {"supported": False, "connections": [], "error": "netstat binary not available on this system"}
    except Exception as exc:
        return {"supported": False, "connections": [], "error": str(exc)}
    return {"supported": True, "connections": conns}
