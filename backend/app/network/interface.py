"""
OS abstraction layer (spec section 28).

The rest of the application imports ONLY from this module — never from
windows.py / linux.py / macos.py directly — so no `if IS_WINDOWS` checks
leak into services/api code. Ping/DNS/ARP stayed in
app.services.legacy_diagnostics (ported as-is from the original project);
everything added from Phase 3 onward (interfaces, traceroute, connections)
lives in the per-OS modules and is dispatched from here.
"""
import ipaddress
import platform

from app.services import legacy_diagnostics as _legacy

CURRENT_OS = platform.system().lower()  # "windows" | "linux" | "darwin"

if CURRENT_OS == "windows":
    from app.network import windows as _impl
elif CURRENT_OS == "darwin":
    from app.network import macos as _impl
else:
    from app.network import linux as _impl


def get_default_gateway() -> str | None:
    return _legacy._get_default_gateway()


def get_local_subnet_prefix() -> str | None:
    return _legacy._get_local_subnet_prefix()


def list_interfaces() -> list[dict]:
    return _impl.list_interfaces()


def get_mac_address(interface_name: str) -> str | None:
    return _impl.get_mac_address(interface_name)


def get_dns_servers() -> list[str]:
    return _impl.get_dns_servers()


def get_wifi_info(interface_name: str) -> dict:
    return _impl.get_wifi_info(interface_name)


def traceroute(target: str, max_hops: int = 30) -> dict:
    return _impl.traceroute(target, max_hops=max_hops)


def active_connections() -> dict:
    return _impl.active_connections()


def get_active_interface_summary() -> dict:
    """
    One combined summary for the Network Interface / Wi-Fi page: whichever
    interface owns the default route, plus its IP/subnet/gateway/DNS/MAC
    and (if available) SSID/signal/frequency/link speed.
    """
    gateway = get_default_gateway()
    subnet_prefix = get_local_subnet_prefix()
    interfaces = list_interfaces()

    active = None
    route = _impl.get_default_route() if CURRENT_OS == "windows" else None
    if route and route.get("local_ip"):
        active = next(
            (iface for iface in interfaces if iface.get("ip") == route["local_ip"]),
            None,
        )
    if active is None and route and route.get("name"):
        active = next(
            (iface for iface in interfaces if iface.get("name") == route["name"]),
            None,
        )
    if subnet_prefix:
        subnet = ipaddress.ip_network(subnet_prefix, strict=False)
        if active is None:
            for iface in interfaces:
                try:
                    if ipaddress.ip_address(iface.get("ip", "")) in subnet:
                        active = iface
                        break
                except ValueError:
                    continue

    # The route lookup is authoritative for the address bound to the default
    # route. `ipconfig` parsing is only a secondary source and may fail on
    # localized Windows output or adapter names it does not recognize. Keep
    # the active route's values instead of discarding them in that case.
    if active is None and route and route.get("local_ip"):
        active = {
            "name": route.get("name") or route.get("description") or "Active interface",
            "ip": route["local_ip"],
        }

    if active is None:
        return {
            "interface_name": None, "connection_type": "unknown", "local_ip": None,
            "subnet": subnet_prefix, "gateway": gateway, "dns_servers": get_dns_servers(),
            "gateway_ipv6": route.get("gateway_ipv6") if route else None,
            "mac_address": None, "ssid": None, "signal_dbm": None,
            "frequency_mhz": None, "link_speed_mbps": None,
        }

    wifi = get_wifi_info(active["name"])
    route_name = f"{active['name']} {route.get('description', '') if route else ''}".lower()
    connection_type = (
        "wifi" if wifi.get("ssid") or any(token in route_name for token in ("wi-fi", "wireless", "wlan"))
        else "vpn" if any(token in route_name for token in ("vpn", "wireguard", "tunnel"))
        else "ethernet"
    )
    return {
        "interface_name": active["name"],
        "connection_type": connection_type,
        "local_ip": active.get("ip"),
        "subnet": subnet_prefix,
        "gateway": gateway,
        "gateway_ipv6": route.get("gateway_ipv6") if route else None,
        "dns_servers": get_dns_servers(),
        "mac_address": get_mac_address(active["name"]),
        **wifi,
    }
