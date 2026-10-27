"""Authenticated client for the optional Windows host diagnostics agent."""

import ipaddress
import logging
import math
import os
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


class HostAgentError(RuntimeError):
    pass


class AgentGateway(BaseModel):
    model_config = ConfigDict(extra="allow")

    reachable: bool | None
    gateway_ip: str | None
    avg_ms: float | None = None
    icmp_unavailable: bool
    source: str


class AgentInternet(BaseModel):
    model_config = ConfigDict(extra="allow")

    reachable: bool | None
    target: str
    avg_ms: float | None = None
    method: str
    source: str


class AgentLatency(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str
    min_ms: float | None
    max_ms: float | None
    avg_ms: float | None
    jitter_ms: float | None
    sent: int
    received: int
    samples: list[float]
    source: str


class AgentPacketLoss(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str
    sent: int
    received: int
    loss_pct: float | None
    icmp_unavailable: bool = False
    source: str


class AgentDns(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain: str
    resolved_ip: str | None
    response_ms: float | None
    success: bool
    source: str


class AgentWebsite(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    reachable: bool
    status_code: int | None
    successful_request: bool
    response_ms: float | None
    source: str


class AgentDeviceDiscovery(BaseModel):
    model_config = ConfigDict(extra="allow")

    supported: bool | None
    status: Literal[
        "success", "empty", "partial", "failed", "skipped", "unsupported",
        "permission_denied",
    ]
    detail: str | None = None
    devices: list[dict[str, str | None]]
    subnet: str | None = None
    scan_complete: bool | None = None
    source: str


class AgentSpeedTestTransfer(BaseModel):
    success: bool
    mbps: float | None
    bytes: int | None = None
    seconds: float | None = None
    error: str | None = None
    samples_mbps: list[float] = Field(default_factory=list)


class AgentSpeedTest(BaseModel):
    source: str
    methodology: str
    download: AgentSpeedTestTransfer
    upload: AgentSpeedTestTransfer
    latency_ms: float | None
    jitter_ms: float | None


class AgentMonitorMeasurement(BaseModel):
    source: str
    target: str
    latency_ms: float | None
    packet_loss_pct: float | None
    sent: int
    received: int
    icmp_unavailable: bool
    dns_ms: float | None
    dns_success: bool
    internet: bool | None


class AgentConnection(BaseModel):
    protocol: Literal["TCP", "UDP"]
    local_ip: str
    local_port: str | None
    remote_ip: str | None
    remote_port: str | None
    state: str


class AgentConnections(BaseModel):
    source: Literal["windows_host"]
    connections: list[AgentConnection]


class AgentDiagnostics(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    gateway: AgentGateway
    internet: AgentInternet
    latency: AgentLatency
    packet_loss: AgentPacketLoss
    dns: AgentDns
    websites: list[AgentWebsite]
    devices: AgentDeviceDiscovery
    interface: dict[str, Any]


class AgentInterface(BaseModel):
    model_config = ConfigDict(extra="allow")

    interface_name: str | None
    connection_type: str
    local_ip: str | None
    subnet: str | None
    gateway: str | None
    gateway_ipv6: str | None = None
    dns_servers: list[str]
    source: str


def is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def _validate_interface_values(interface: dict[str, Any]) -> None:
    try:
        address = interface.get("local_ip")
        subnet = interface.get("subnet")
        if address:
            parsed_address = ipaddress.ip_address(address)
            if parsed_address.version != 4:
                raise ValueError("Local interface address must be IPv4.")
            if subnet and parsed_address not in ipaddress.ip_network(subnet, strict=False):
                raise ValueError("Local interface address is outside its reported subnet.")
        elif subnet:
            raise ValueError("A subnet cannot be present without a local address.")
        gateway = interface.get("gateway") or interface.get("gateway_ip")
        if gateway:
            ipaddress.ip_address(gateway)
        gateway6 = interface.get("gateway_ipv6")
        if gateway6 and ipaddress.ip_address(gateway6).version != 6:
            raise ValueError("IPv6 gateway must be an IPv6 address.")
        for dns_server in interface.get("dns_servers", []):
            ipaddress.ip_address(dns_server)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid host interface address data: {exc}") from exc


def _validate_devices(devices: AgentDeviceDiscovery) -> None:
    network = ipaddress.ip_network(devices.subnet, strict=False) if devices.subnet else None
    if network is not None and network.version != 4:
        raise ValueError("Discovered subnet must be IPv4.")
    for device in devices.devices:
        address = ipaddress.ip_address(device.get("ip", ""))
        if address.version != 4:
            raise ValueError("Discovered device address must be IPv4.")
        if network is not None and address not in network:
            raise ValueError("Discovered device is outside the reported subnet.")
        mac = device.get("mac")
        if mac is not None and not re.fullmatch(
            r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac
        ):
            raise ValueError("Discovered device has an invalid MAC address.")


def _validate_operation(operation: str, payload: dict[str, Any]) -> None:
    if operation not in {"diagnostics", "interface", "discovery", "speedtest", "monitor", "connections"}:
        raise ValueError("Unsupported host-agent operation.")

    if operation == "diagnostics":
        if set(payload) - {
            "external_host", "dns_domain", "websites", "discover_devices", "max_hosts",
        }:
            raise ValueError("Unexpected diagnostics request fields.")
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
                raise ValueError("Invalid external diagnostic target.") from None
        domain = payload.get("dns_domain", "google.com")
        if not isinstance(domain, str) or not re.fullmatch(
            r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
            r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?",
            domain,
        ):
            raise ValueError("Invalid DNS domain.")
        websites = payload.get("websites", [])
        if not isinstance(websites, list) or len(websites) > 10:
            raise ValueError("At most 10 website checks are supported.")
        for website in websites:
            parsed = urlsplit(website) if isinstance(website, str) else None
            if (
                parsed is None or parsed.scheme not in {"http", "https"}
                or not parsed.hostname or parsed.username or parsed.password
                or len(website) > 2048
            ):
                raise ValueError("Website checks require valid HTTP or HTTPS URLs.")
        if not isinstance(payload.get("discover_devices", False), bool):
            raise ValueError("discover_devices must be a boolean.")
        max_hosts = payload.get("max_hosts", 32)
        if not isinstance(max_hosts, int) or isinstance(max_hosts, bool) or not 1 <= max_hosts <= 64:
            raise ValueError("max_hosts must be between 1 and 64.")
    elif operation == "interface":
        if payload:
            raise ValueError("The interface operation does not accept options.")
    elif operation == "connections":
        if payload:
            raise ValueError("The connections operation does not accept options.")
    elif operation == "discovery":
        if set(payload) - {"max_hosts"}:
            raise ValueError("Unexpected discovery request fields.")
        max_hosts = payload.get("max_hosts", 32)
        if not isinstance(max_hosts, int) or isinstance(max_hosts, bool) or not 1 <= max_hosts <= 1024:
            raise ValueError("max_hosts must be between 1 and 1024.")
    elif operation == "speedtest":
        if set(payload) - {"download_bytes", "upload_bytes"}:
            raise ValueError("Unexpected speed-test request fields.")
        download_bytes = payload.get("download_bytes", 10_000_000)
        upload_bytes = payload.get("upload_bytes", 5_000_000)
        if not isinstance(download_bytes, int) or isinstance(download_bytes, bool) or not 100_000 <= download_bytes <= 100_000_000:
            raise ValueError("download_bytes must be between 100 KB and 100 MB.")
        if not isinstance(upload_bytes, int) or isinstance(upload_bytes, bool) or not 100_000 <= upload_bytes <= 25_000_000:
            raise ValueError("upload_bytes must be between 100 KB and 25 MB.")
    else:
        if set(payload) - {"target"}:
            raise ValueError("Unexpected monitoring request fields.")
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
                raise ValueError("Invalid monitoring target.") from None


def _validate_diagnostics(data: Any) -> AgentDiagnostics:
    try:
        result = AgentDiagnostics.model_validate(data)
        if result.source != "windows_host":
            raise ValueError("The agent did not identify its measurement source.")
        checks = (
            result.gateway, result.internet, result.latency, result.packet_loss,
            result.dns, result.devices, result.interface,
            *result.websites,
        )
        if any(
            (check.get("source") if isinstance(check, dict) else check.source)
            != "windows_host"
            for check in checks
        ):
            raise ValueError("Inconsistent measurement source in host-agent response.")
        _validate_interface_values(result.interface)
        _validate_devices(result.devices)
        if result.latency.sent < 0 or not 0 <= result.latency.received <= result.latency.sent:
            raise ValueError("Invalid packet counts in host-agent latency result.")
        if len(result.latency.samples) != result.latency.received:
            raise ValueError("Latency samples do not match the received packet count.")
        if result.packet_loss.sent < 0 or not 0 <= result.packet_loss.received <= result.packet_loss.sent:
            raise ValueError("Invalid packet counts in host-agent packet-loss result.")
        if result.packet_loss.icmp_unavailable:
            if result.packet_loss.loss_pct is not None:
                raise ValueError("Packet loss must be unavailable when ICMP receives no replies.")
        elif result.packet_loss.sent:
            expected_loss = round(
                (result.packet_loss.sent - result.packet_loss.received)
                / result.packet_loss.sent * 100, 1
            )
            if result.packet_loss.loss_pct != expected_loss:
                raise ValueError("Inconsistent packet-loss result from host agent.")
        elif result.packet_loss.loss_pct is not None:
            raise ValueError("Packet loss must be unavailable when no probes were sent.")
        if result.packet_loss.icmp_unavailable != (
            result.packet_loss.sent > 0 and result.packet_loss.received == 0
        ):
            raise ValueError("Inconsistent ICMP status in host-agent packet-loss result.")
        values = [
            result.gateway.avg_ms, result.internet.avg_ms,
            result.latency.min_ms, result.latency.max_ms, result.latency.avg_ms,
            result.latency.jitter_ms, *result.latency.samples,
            result.packet_loss.loss_pct, result.dns.response_ms,
        ]
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("Non-finite measurements in host-agent response.")
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed data: {exc}") from exc


def _post(operation: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.HOST_AGENT_URL or not settings.HOST_AGENT_TOKEN:
        raise HostAgentError("Windows host diagnostics agent is not configured.")
    if len(settings.HOST_AGENT_TOKEN) < 32:
        raise HostAgentError("Windows host agent token must contain at least 32 characters.")
    agent_url = urlsplit(settings.HOST_AGENT_URL)
    if (
        agent_url.scheme not in {"http", "https"} or not agent_url.hostname
        or agent_url.username or agent_url.password or agent_url.query or agent_url.fragment
    ):
        raise HostAgentError("Windows host agent URL is invalid.")
    _validate_operation(operation, payload or {})
    url = settings.HOST_AGENT_URL.rstrip("/") + "/v1/" + operation
    try:
        response = requests.post(
            url,
            json=payload or {},
            headers={"Authorization": f"Bearer {settings.HOST_AGENT_TOKEN}"},
            timeout=settings.HOST_AGENT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("Windows host agent request failed: %s", exc)
        raise HostAgentError("Windows host diagnostics agent is unavailable.") from exc
    if response.status_code != 200:
        raise HostAgentError(
            f"Windows host diagnostics agent returned HTTP {response.status_code}."
        )
    if len(response.content) > 1_000_000:
        raise HostAgentError("Windows host diagnostics agent response is too large.")
    try:
        data = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise HostAgentError("Windows host diagnostics agent returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise HostAgentError("Windows host diagnostics agent returned an invalid response.")
    return data


def run_diagnostics(
    external_host: str, dns_domain: str, websites: list[str],
    discover_devices: bool, max_hosts: int = 32,
) -> AgentDiagnostics:
    data = _post("diagnostics", {
        "external_host": external_host,
        "dns_domain": dns_domain,
        "websites": websites,
        "discover_devices": discover_devices,
        "max_hosts": max_hosts,
    })
    return _validate_diagnostics(data)


def get_interface() -> AgentInterface:
    try:
        result = AgentInterface.model_validate(_post("interface"))
        if result.source != "windows_host":
            raise ValueError("The agent did not identify its measurement source.")
        _validate_interface_values(result.model_dump())
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed interface data: {exc}") from exc


def discover_devices(max_hosts: int) -> AgentDeviceDiscovery:
    data = _post("discovery", {"max_hosts": max_hosts})
    try:
        result = AgentDeviceDiscovery.model_validate(data)
        if result.source != "windows_host":
            raise ValueError("The agent did not identify its measurement source.")
        _validate_devices(result)
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed discovery data: {exc}") from exc


def run_speed_test(download_bytes: int, upload_bytes: int) -> AgentSpeedTest:
    data = _post("speedtest", {
        "download_bytes": download_bytes,
        "upload_bytes": upload_bytes,
    })
    try:
        result = AgentSpeedTest.model_validate(data)
        if result.source != "windows_host":
            raise ValueError("The agent did not identify its measurement source.")
        if not result.methodology:
            raise ValueError("The agent did not report its measurement methodology.")
        transfers = (
            (result.download, download_bytes),
            (result.upload, upload_bytes),
        )
        for transfer, expected_bytes in transfers:
            if transfer.success:
                if transfer.bytes != expected_bytes or len(transfer.samples_mbps) != 3:
                    raise ValueError("Successful speed-test transfer has inconsistent byte or sample counts.")
                if transfer.mbps is None or transfer.seconds is None or transfer.seconds <= 0:
                    raise ValueError("Successful speed-test transfer is missing a valid measurement.")
            elif transfer.mbps is not None or not transfer.error:
                raise ValueError("Failed speed-test transfer must include an error and no Mbps value.")
        values = [
            result.download.mbps, result.upload.mbps, result.latency_ms,
            result.jitter_ms, *result.download.samples_mbps,
            *result.upload.samples_mbps,
        ]
        if any(value is not None and (not math.isfinite(value) or value < 0) for value in values):
            raise ValueError("Non-finite or negative measurement in speed-test response.")
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed speed-test data: {exc}") from exc


def run_monitor_measurement(target: str) -> AgentMonitorMeasurement:
    data = _post("monitor", {"target": target})
    try:
        result = AgentMonitorMeasurement.model_validate(data)
        if result.source != "windows_host" or result.target != target:
            raise ValueError("The host agent returned an inconsistent monitoring source or target.")
        if result.sent < 0 or not 0 <= result.received <= result.sent:
            raise ValueError("The host agent returned invalid monitoring packet counts.")
        expected_loss = (
            round((result.sent - result.received) / result.sent * 100, 1)
            if result.sent and result.received > 0 else None
        )
        if result.packet_loss_pct != expected_loss:
            raise ValueError("The host agent returned inconsistent packet-loss data.")
        if result.icmp_unavailable != (result.received == 0):
            raise ValueError("The host agent returned inconsistent ICMP status.")
        values = (result.latency_ms, result.packet_loss_pct, result.dns_ms)
        if any(value is not None and (not math.isfinite(value) or value < 0) for value in values):
            raise ValueError("The host agent returned invalid monitoring measurements.")
        if bool(result.received) != (result.latency_ms is not None):
            raise ValueError("The host agent returned inconsistent latency data.")
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed monitoring data: {exc}") from exc


def get_connections() -> AgentConnections:
    data = _post("connections")
    try:
        result = AgentConnections.model_validate(data)
        for connection in result.connections:
            for address in (connection.local_ip, connection.remote_ip):
                if address and address not in {"*", "any"}:
                    ipaddress.ip_address(address.split("%", 1)[0])
            for port in (connection.local_port, connection.remote_port):
                if port is not None and not port.isdigit():
                    raise ValueError("Host agent returned a non-numeric connection port.")
        if len(result.connections) > 5000:
            raise ValueError("Host agent returned too many connections.")
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise HostAgentError(f"Windows host agent returned malformed connection data: {exc}") from exc
