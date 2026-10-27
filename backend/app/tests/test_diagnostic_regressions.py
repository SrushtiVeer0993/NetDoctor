import socket
import subprocess
from ipaddress import IPv4Network
from types import SimpleNamespace

import requests

from app.services import legacy_diagnostics as diagnostics


def _healthy_inputs():
    return {
        "gateway": {"reachable": True, "icmp_unavailable": False},
        "internet": {"reachable": True},
        "latency": {"avg_ms": 30},
        "packet_loss": {"loss_pct": 0},
        "dns": {"success": True, "response_ms": 20},
    }


def test_http_403_is_site_access_error_not_network_failure_or_dns_issue(monkeypatch):
    monkeypatch.setattr(
        diagnostics.requests, "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=403),
    )
    result = diagnostics.test_websites(["https://example.test"])
    diagnosis = diagnostics.diagnose(**_healthy_inputs(), websites=result)
    codes = {finding["code"] for finding in diagnosis["findings"]}
    recommendations = diagnostics.recommend(diagnosis["findings"])

    assert "website_http_error" in codes
    assert "connectivity_local" not in codes
    assert not any("DNS" in item or "Wi-Fi" in item for item in recommendations)


def test_http_status_categories_and_final_redirect_response(monkeypatch):
    monkeypatch.setattr(
        diagnostics.requests, "get",
        lambda url, timeout: SimpleNamespace(status_code={"ok": 204, "redirect": 302, "server": 503}[url]),
    )
    results = diagnostics.test_websites(["ok", "redirect", "server"])

    assert [(r["successful_request"], r["http_category"]) for r in results] == [
        (True, "success"), (False, "redirect"), (False, "server_error"),
    ]


def test_website_transport_failure_types_are_distinguished(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(diagnostics.requests, "get", timeout)
    assert diagnostics.test_websites(["https://example.test"])[0]["error_type"] == "timeout"

    def tls_failure(*args, **kwargs):
        raise requests.exceptions.SSLError("TLS handshake failed")

    monkeypatch.setattr(diagnostics.requests, "get", tls_failure)
    assert diagnostics.test_websites(["https://example.test"])[0]["error_type"] == "tls_error"

    def dns_failure(*args, **kwargs):
        raise requests.ConnectionError("NameResolutionError: getaddrinfo failed")

    monkeypatch.setattr(diagnostics.requests, "get", dns_failure)
    assert diagnostics.test_websites(["https://example.test"])[0]["error_type"] == "dns_resolution"


def test_dns_resolution_failure_is_reported(monkeypatch):
    def fail_resolution(_):
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(diagnostics.socket, "gethostbyname", fail_resolution)
    assert diagnostics.measure_dns_response_time("invalid.example")["success"] is False


def test_discovery_skipped_is_explicit(monkeypatch):
    monkeypatch.setattr(diagnostics, "check_gateway_connectivity", lambda: {"reachable": True})
    monkeypatch.setattr(diagnostics, "check_internet_connectivity", lambda _host: {"reachable": True})
    monkeypatch.setattr(diagnostics, "measure_latency", lambda _host: {"avg_ms": 25})
    monkeypatch.setattr(diagnostics, "measure_packet_loss", lambda _host: {"loss_pct": 0})
    monkeypatch.setattr(diagnostics, "measure_dns_response_time", lambda _domain: {"success": True, "response_ms": 10})
    result = diagnostics.run_full_diagnosis(discover_devices=False)

    assert result["devices"]["status"] == "skipped"
    assert result["devices"]["devices"] == []


def test_empty_device_scan_is_completed_and_limited_to_private_subnet(monkeypatch):
    monkeypatch.setattr(diagnostics, "_get_local_ipv4_network", lambda: IPv4Network("192.168.10.0/29"))
    monkeypatch.setattr(diagnostics, "_get_local_ipv4_address", lambda: "192.168.10.2")
    scanned = []

    def fake_run(command, **kwargs):
        if command[0] in ("ping", "arp"):
            if command[0] == "ping":
                scanned.append(command[-1])
            return SimpleNamespace(stdout=b"")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    result = diagnostics.discover_local_devices(max_hosts=3)

    assert result["status"] == "empty"
    assert result["devices"] == []
    assert result["scanned_hosts"] == 3
    assert len(scanned) == 3
    assert all(ip.startswith("192.168.10.") for ip in scanned)
    assert "192.168.10.2" not in scanned


def test_discovery_permission_failure_is_reported(monkeypatch):
    monkeypatch.setattr(diagnostics, "_get_local_ipv4_network", lambda: IPv4Network("192.168.1.0/24"))
    monkeypatch.setattr(diagnostics, "_get_local_ipv4_address", lambda: "192.168.1.2")
    monkeypatch.setattr(diagnostics, "IS_WINDOWS", True)
    monkeypatch.setattr(
        diagnostics.subprocess, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    result = diagnostics.discover_local_devices()

    assert result["status"] == "permission_denied"
    assert result["devices"] == []


def test_discovery_uses_actual_subnet_mask(monkeypatch):
    from app.network import windows

    monkeypatch.setattr(diagnostics, "IS_WINDOWS", True)
    monkeypatch.setattr(
        windows, "get_default_route",
        lambda: {"local_ip": "192.168.20.7", "prefix": 20},
    )

    assert str(diagnostics._get_local_ipv4_network()) == "192.168.16.0/20"


def test_discovery_reports_unsupported_when_no_private_subnet_is_available(monkeypatch):
    monkeypatch.setattr(diagnostics, "_get_local_ipv4_network", lambda: None)

    result = diagnostics.discover_local_devices()

    assert result["status"] == "unsupported"
    assert result["supported"] is False
    assert result["devices"] == []
