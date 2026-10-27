"""
Integration tests for Phase 3-9 endpoints. Uses DEMO MODE throughout so
the suite is deterministic and doesn't depend on real ICMP/ARP/HTTP access
being available in the CI/test environment (see app.services.demo_data).
"""
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app


def _register_and_login(client, email="phase39@example.com", password="TestPassword123!"):
    local, domain = email.split("@", 1)
    email = f"{local}-{uuid4().hex[:12]}@{domain}"
    client.post("/api/auth/register", json={"email": email, "password": password})
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_network_endpoints_demo_mode():
    with TestClient(app) as client:
        headers = _register_and_login(client, "network@example.com")
        client.put("/api/settings", json={"demo_mode": True}, headers=headers)

        assert client.get("/api/network/interfaces", headers=headers).status_code == 200
        assert client.get("/api/network/connections", headers=headers).status_code == 200

        tr = client.post("/api/network/traceroute", json={"target": "8.8.8.8"}, headers=headers)
        assert tr.status_code == 200
        assert tr.json()["supported"] is True
        assert len(tr.json()["hops"]) > 0

        disc = client.post("/api/network/discover", json={"max_hosts": 10}, headers=headers)
        assert disc.status_code == 200
        assert len(disc.json()["devices"]) > 0

        assert client.get("/api/network/map", headers=headers).status_code == 200


def test_speed_test_demo_mode():
    with TestClient(app) as client:
        headers = _register_and_login(client, "speed@example.com")
        client.put("/api/settings", json={"demo_mode": True}, headers=headers)

        res = client.post("/api/speedtest", json={}, headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["simulated"] is True
        assert body["download"]["mbps"] is not None

        history = client.get("/api/speedtest/history", headers=headers)
        assert history.status_code == 200
        assert len(history.json()) == 1


def test_monitoring_session_and_websocket(monkeypatch):
    from app.api import monitoring

    monkeypatch.setattr(
        monitoring.engine,
        "measure_latency",
        lambda target, count: {"received": 3, "avg_ms": 1.0},
    )
    monkeypatch.setattr(
        monitoring.engine,
        "measure_packet_loss",
        lambda target, count: {"loss_pct": 0.0},
    )
    monkeypatch.setattr(
        monitoring.engine,
        "measure_dns_response_time",
        lambda: {"response_ms": 1.0, "success": True},
    )
    monkeypatch.setattr(
        monitoring.engine,
        "check_internet_connectivity",
        lambda target: {"reachable": True},
    )

    with TestClient(app) as client:
        headers = _register_and_login(client, "monitor@example.com")
        token = headers["Authorization"].split(" ")[1]

        start = client.post("/api/monitoring/start?interval_seconds=1&target=8.8.8.8", headers=headers)
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        with client.websocket_connect(f"/ws/monitor?session_id={session_id}&token={token}") as ws:
            msg = ws.receive_json()
            assert "latency_ms" in msg
            assert "internet" in msg

        measurements = client.get(f"/api/monitoring/{session_id}/measurements", headers=headers)
        assert measurements.status_code == 200
        assert len(measurements.json()["measurements"]) >= 1


def test_packet_capture_demo_mode():
    with TestClient(app) as client:
        headers = _register_and_login(client, "packets@example.com")

        start = client.post("/api/packet-capture/start?demo=true", json={}, headers=headers)
        assert start.status_code == 200
        assert start.json()["supported"] is True

        packets = client.get("/api/packet-capture/packets/demo", headers=headers)
        assert packets.status_code == 200
        assert len(packets.json()["packets"]) > 0


def test_analytics_and_anomalies_need_history():
    with TestClient(app) as client:
        headers = _register_and_login(client, "analytics@example.com")
        client.put("/api/settings", json={"demo_mode": True}, headers=headers)

        # No diagnostic runs yet -> has_data should be False, not an error
        empty = client.get("/api/analytics?range=30d", headers=headers)
        assert empty.status_code == 200
        assert empty.json()["has_data"] is False

        client.post(
            "/api/diagnostics/full",
            json={"external_host": "8.8.8.8", "dns_domain": "google.com", "websites": [], "discover_devices": False},
            headers=headers,
        )

        with_data = client.get("/api/analytics?range=30d", headers=headers)
        assert with_data.status_code == 200
        assert with_data.json()["has_data"] is True

        anomalies = client.get("/api/analytics/anomalies", headers=headers)
        assert anomalies.status_code == 200


def test_reports_pdf_csv_json():
    with TestClient(app) as client:
        headers = _register_and_login(client, "reports@example.com")
        client.put("/api/settings", json={"demo_mode": True}, headers=headers)
        run = client.post(
            "/api/diagnostics/full",
            json={"external_host": "8.8.8.8", "dns_domain": "google.com", "websites": [], "discover_devices": False},
            headers=headers,
        )
        run_id = run.json()["id"]

        for fmt in ("pdf", "csv", "json"):
            gen = client.post(f"/api/reports/{run_id}/{fmt}", headers=headers)
            assert gen.status_code == 200
            download_url = gen.json()["download_url"]
            dl = client.get(download_url, headers=headers)
            assert dl.status_code == 200
            assert len(dl.content) > 0
            if fmt == "csv":
                assert b"measurement_source,simulated_demo_mode" in dl.content
            elif fmt == "json":
                assert b'"simulated": true' in dl.content


def test_settings_defaults_and_update():
    with TestClient(app) as client:
        headers = _register_and_login(client, "settings@example.com")

        defaults = client.get("/api/settings", headers=headers)
        assert defaults.status_code == 200
        assert defaults.json()["demo_mode"] is False

        updated = client.put("/api/settings", json={"latency_alert_ms": 200, "demo_mode": True}, headers=headers)
        assert updated.status_code == 200
        assert updated.json()["latency_alert_ms"] == 200
        assert updated.json()["demo_mode"] is True


def test_alerts_list_empty_by_default():
    with TestClient(app) as client:
        headers = _register_and_login(client, "alerts@example.com")
        res = client.get("/api/alerts", headers=headers)
        assert res.status_code == 200
        assert res.json() == []
