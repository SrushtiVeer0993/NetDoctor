import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import monitoring
from app.main import app


def _login(client, email):
    password = "Monitoring-test-password-123!"
    client.post("/api/auth/register", json={"email": email, "password": password})
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_sync_measurements_are_offloaded_and_bounded(monkeypatch):
    lock = threading.Lock()
    running = 0
    peak_running = 0

    def slow_latency(target, count):
        nonlocal running, peak_running
        with lock:
            running += 1
            peak_running = max(peak_running, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return {"received": 3, "avg_ms": 1.0}

    monkeypatch.setattr(monitoring.engine, "measure_latency", slow_latency)
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

    async def exercise_measurements():
        tasks = [
            asyncio.create_task(monitoring._measure_target_async("example.test"))
            for _ in range(8)
        ]
        ticks = 0
        while not all(task.done() for task in tasks):
            ticks += 1
            await asyncio.sleep(0.01)
        return await asyncio.gather(*tasks), ticks

    results, ticks = asyncio.run(exercise_measurements())

    assert len(results) == 8
    assert ticks > 1
    assert 1 < peak_running <= monitoring._MAX_CONCURRENT_MEASUREMENTS


def test_stop_ends_active_websocket_promptly(monkeypatch):
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
        headers = _login(client, "monitor-stop@example.com")
        token = headers["Authorization"].split(" ")[1]
        start = client.post(
            "/api/monitoring/start?interval_seconds=3600",
            headers=headers,
        )
        assert start.status_code == 200
        session_id = start.json()["session_id"]

        with client.websocket_connect(
            f"/ws/monitor?session_id={session_id}&token={token}"
        ) as websocket:
            first_measurement = websocket.receive_json()
            assert "latency_ms" in first_measurement

            stopped = client.post(
                f"/api/monitoring/stop?session_id={session_id}",
                headers=headers,
            )
            assert stopped.status_code == 200
            assert stopped.json() == {"stopped": True}

            with pytest.raises(WebSocketDisconnect):
                websocket.receive_json()

        measurements = client.get(
            f"/api/monitoring/{session_id}/measurements",
            headers=headers,
        )
        assert len(measurements.json()["measurements"]) == 1


def test_monitoring_interval_is_bounded():
    with TestClient(app) as client:
        headers = _login(client, "monitor-interval@example.com")
        too_short = client.post(
            "/api/monitoring/start?interval_seconds=0",
            headers=headers,
        )
        too_long = client.post(
            "/api/monitoring/start?interval_seconds=3601",
            headers=headers,
        )

    assert too_short.status_code == 422
    assert too_long.status_code == 422


def test_monitoring_session_persists_demo_mode():
    with TestClient(app) as client:
        headers = _login(client, "monitor-demo-mode@example.com")
        updated = client.put(
            "/api/settings", json={"demo_mode": True}, headers=headers
        )
        assert updated.status_code == 200

        started = client.post("/api/monitoring/start", headers=headers)
        assert started.status_code == 200
        assert started.json()["simulated"] is True

        stopped = client.post(
            f"/api/monitoring/stop?session_id={started.json()['session_id']}",
            headers=headers,
        )
        assert stopped.json()["stopped"] is True
