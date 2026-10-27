import json
import subprocess
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import requests

from app.network import windows
from app.services import host_agent, legacy_diagnostics as diagnostics
from host_agent import windows_agent


def _route(name, gateway, local_ip, prefix, metric, physical=True):
    return {
        "name": name,
        "description": name,
        "status": "Up",
        "physical": physical,
        "interface_index": metric,
        "gateway": gateway,
        "local_ip": local_ip,
        "prefix": prefix,
        "metric": metric,
        "dns": ["192.0.2.53"],
    }


def test_windows_gateway_selects_active_non_docker_route_and_tracks_changes(monkeypatch):
    data = {
        "ipv4": [
            _route("vEthernet (Docker)", "172.19.0.1", "172.19.0.2", 16, 1, False),
            _route("Wi-Fi", "192.168.1.1", "192.168.1.5", 24, 20),
            _route("Ethernet", "10.4.0.1", "10.4.0.5", 24, 40),
        ],
        "ipv6": {"gateway": "fe80::1", "name": "Wi-Fi", "metric": 20},
    }
    monkeypatch.setattr(windows_agent, "_run_powershell", lambda _script: data)

    selected = windows_agent._get_network()
    assert selected["source"] == "windows_host"
    assert selected["gateway_ip"] == "192.168.1.1"
    assert selected["local_ip"] == "192.168.1.5"
    assert selected["subnet"] == "192.168.1.0/24"
    assert selected["gateway_ipv6"] == "fe80::1"

    data["ipv4"][1].update(
        gateway="192.168.50.1", local_ip="192.168.50.9", prefix=23, metric=10
    )
    selected = windows_agent._get_network()
    assert selected["gateway_ip"] == "192.168.50.1"
    assert selected["subnet"] == "192.168.50.0/23"


def test_windows_gateway_route_uses_route_metric_and_does_not_guess(monkeypatch):
    routes = [
        _route("Wi-Fi", "192.168.9.1", "192.168.9.10", 24, 25),
        _route("Ethernet", "10.10.1.1", "10.10.1.7", 20, 10),
        _route("vEthernet (WSL)", "172.20.0.1", "172.20.0.2", 16, 1, False),
    ]
    output = json.dumps({"ipv4": routes, "ipv6": None}).encode()
    monkeypatch.setattr(
        windows.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=output)
    )

    assert windows.get_default_route()["gateway"] == "10.10.1.1"

    monkeypatch.setattr(
        windows.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=b'{"ipv4":[],"ipv6":null}'),
    )
    assert windows.get_default_route() == {"gateway_ipv6": None}


def test_gateway_icmp_unavailable_is_not_a_connectivity_failure(monkeypatch):
    monkeypatch.setattr(diagnostics, "IS_WINDOWS", True)
    monkeypatch.setattr(
        windows, "get_default_route",
        lambda: {"gateway": "192.168.8.1", "local_ip": "192.168.8.4"},
    )
    monkeypatch.setattr(
        diagnostics, "_ping_with_status",
        lambda *_args, **_kwargs: {"output": "", "error_type": None, "error": None},
    )
    monkeypatch.setattr(
        diagnostics.socket, "create_connection",
        lambda *_args, **_kwargs: nullcontext(),
    )

    gateway = diagnostics.check_gateway_connectivity()
    internet = diagnostics.check_internet_connectivity()
    result = diagnostics.diagnose(
        gateway=gateway,
        internet=internet,
        latency={"avg_ms": None},
        packet_loss={"loss_pct": None, "icmp_unavailable": True},
        dns={"success": True, "response_ms": 10},
        websites=[],
    )

    assert gateway["gateway_ip"] == "192.168.8.1"
    assert gateway["reachable"] is False
    assert gateway["icmp_unavailable"] is True
    assert internet["reachable"] is True
    assert "connectivity_local" not in {finding["code"] for finding in result["findings"]}


def test_packet_loss_uses_actual_reply_count_and_labels_blocked_icmp(monkeypatch):
    monkeypatch.setattr(
        diagnostics, "_ping_with_status",
        lambda *_args, **_kwargs: {
            "output": "time=4ms\ntime<1ms", "error_type": None, "error": None,
        },
    )
    measured = diagnostics.measure_packet_loss("198.51.100.2", count=4)
    assert measured["target"] == "198.51.100.2"
    assert measured["sent"] == 4
    assert measured["received"] == 2
    assert measured["loss_pct"] == 50.0
    assert measured["icmp_unavailable"] is False

    monkeypatch.setattr(
        diagnostics, "_ping_with_status",
        lambda *_args, **_kwargs: {"output": "", "error_type": None, "error": None},
    )
    blocked = diagnostics.measure_packet_loss(count=3)
    assert blocked["loss_pct"] == 100.0
    assert blocked["icmp_unavailable"] is True


def test_ping_tool_failure_is_not_reported_as_100_percent_packet_loss(monkeypatch):
    monkeypatch.setattr(
        diagnostics.subprocess, "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("ping missing")),
    )

    result = diagnostics.measure_packet_loss("8.8.8.8", count=4)
    assert result["sent"] == 0
    assert result["received"] == 0
    assert result["loss_pct"] is None
    assert result["error_type"] == "unsupported"


def test_dns_failure_does_not_override_successful_internet_probe():
    findings = diagnostics.diagnose(
        gateway={"reachable": True, "icmp_unavailable": False},
        internet={"reachable": True, "icmp_unavailable": False},
        latency={"avg_ms": 20},
        packet_loss={"loss_pct": 0},
        dns={"success": False, "error": "name resolution failed"},
        websites=[],
    )["findings"]
    codes = {finding["code"] for finding in findings}
    assert "dns_failure" in codes
    assert "connectivity_local" not in codes
    assert "connectivity_upstream" not in codes


def _network_summary():
    return {
        "interface_name": "Wi-Fi",
        "interface_index": 8,
        "local_ip": "192.168.10.2",
        "subnet": "192.168.10.0/29",
    }


@pytest.mark.parametrize(
    ("ping_result", "neighbor_result", "expected"),
    [
        ({"error": "probe timed out", "error_type": "timeout"}, [], "failed"),
        ({"error": "access denied", "error_type": "permission_denied"}, [], "permission_denied"),
        ({}, [], "empty"),
        ({"error": "probe timed out", "error_type": "timeout"}, [
            {"InterfaceIndex": 8, "IPAddress": "192.168.10.3", "LinkLayerAddress": "aa-bb-cc-00-00-03"},
        ], "partial"),
        ({}, [
            {"InterfaceIndex": 8, "IPAddress": "192.168.10.3", "LinkLayerAddress": "aa-bb-cc-00-00-03"},
        ], "success"),
    ],
)
def test_host_discovery_reports_timeout_permission_empty_partial_and_success(
    monkeypatch, ping_result, neighbor_result, expected
):
    monkeypatch.setattr(windows_agent, "_get_network", _network_summary)
    monkeypatch.setattr(windows_agent, "_ping", lambda *_args: ping_result)
    monkeypatch.setattr(windows_agent, "_run_powershell", lambda _script: neighbor_result)

    result = windows_agent._discovery(max_hosts=4)

    assert result["status"] == expected
    if expected in {"partial", "success"}:
        assert result["devices"] == [{"ip": "192.168.10.3", "mac": "aa:bb:cc:00:00:03"}]
    else:
        assert result["devices"] == []
    assert result["subnet"] == "192.168.10.0/29"


@pytest.mark.parametrize(
    ("error", "detail", "expected_status"),
    [
        (PermissionError("denied"), "Permission", "permission_denied"),
        (subprocess.TimeoutExpired("powershell", 8), "timed out", "failed"),
    ],
)
def test_host_neighbor_table_read_failures_are_explicit(
    monkeypatch, error, detail, expected_status
):
    monkeypatch.setattr(windows_agent, "_get_network", _network_summary)
    monkeypatch.setattr(windows_agent, "_ping", lambda *_args: {})
    monkeypatch.setattr(
        windows_agent, "_run_powershell",
        lambda _script: (_ for _ in ()).throw(error),
    )

    result = windows_agent._discovery(max_hosts=2)
    assert result["status"] == expected_status
    assert detail.lower() in result["detail"].lower()


def test_host_discovery_preserves_responsive_devices_when_neighbor_read_fails(monkeypatch):
    monkeypatch.setattr(windows_agent, "_get_network", _network_summary)
    monkeypatch.setattr(windows_agent, "_ping", lambda *_args: {"received": 1})
    monkeypatch.setattr(
        windows_agent, "_run_powershell",
        lambda _script: (_ for _ in ()).throw(subprocess.TimeoutExpired("powershell", 8)),
    )

    result = windows_agent._discovery(max_hosts=2)

    assert result["status"] == "partial"
    assert result["devices"] == [
        {"ip": "192.168.10.1", "mac": None},
        {"ip": "192.168.10.3", "mac": None},
    ]


def test_host_agent_client_reports_unavailable_and_rejects_malformed_results(monkeypatch):
    monkeypatch.setattr(host_agent.settings, "HOST_AGENT_URL", "http://host.docker.internal:8765")
    monkeypatch.setattr(
        host_agent.settings, "HOST_AGENT_TOKEN",
        "test-token-that-is-at-least-thirty-two-characters",
    )
    monkeypatch.setattr(
        host_agent.requests, "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(host_agent.requests.ConnectionError("offline")),
    )
    with pytest.raises(host_agent.HostAgentError, match="unavailable"):
        host_agent.run_diagnostics("8.8.8.8", "example.com", [], False)

    monkeypatch.setattr(
        host_agent.requests, "post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200, content=b"{}", json=lambda: {},
        ),
    )
    with pytest.raises(host_agent.HostAgentError, match="malformed"):
        host_agent.run_diagnostics("8.8.8.8", "example.com", [], False)


def test_measurement_source_does_not_confuse_docker_with_windows_host(monkeypatch):
    exists = lambda path: path == "/.dockerenv"
    monkeypatch.setattr(diagnostics.os.path, "exists", exists)
    assert diagnostics.measurement_source() == "docker_container"

    monkeypatch.setattr(diagnostics.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    assert diagnostics.measurement_source() == "windows_host"


def test_host_agent_accepts_only_predefined_operations_and_bounded_scans():
    assert windows_agent._valid_request("interface", {}) == {}
    assert windows_agent._valid_request("discovery", {"max_hosts": 64}) == {"max_hosts": 64}
    with pytest.raises(windows_agent.AgentError):
        windows_agent._valid_request("execute", {"command": "whoami"})
    with pytest.raises(windows_agent.AgentError):
        windows_agent._valid_request("discovery", {"max_hosts": 65})


def test_host_agent_requires_bearer_auth_and_rejects_arbitrary_options(monkeypatch):
    monkeypatch.setattr(windows_agent, "_TOKEN", "a-test-token-that-is-at-least-32-chars")
    server = windows_agent.BoundedThreadingHTTPServer(("127.0.0.1", 0), windows_agent.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1/interface"
    try:
        unauthenticated = requests.post(endpoint, json={}, timeout=2)
        assert unauthenticated.status_code == 401

        invalid = requests.post(
            endpoint,
            json={"command": "whoami"},
            headers={"Authorization": "Bearer a-test-token-that-is-at-least-32-chars"},
            timeout=2,
        )
        assert invalid.status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
