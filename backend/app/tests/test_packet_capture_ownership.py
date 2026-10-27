from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import packet_capture


def test_capture_data_is_only_visible_to_owning_user():
    capture_id = "ownership-test"
    packet_capture._captures[capture_id] = {
        "sniffer": SimpleNamespace(running=True),
        "packets": [{"protocol": "TCP"}],
        "started_at": "2026-01-01T00:00:00+00:00",
        "status": "running",
        "interface": None,
        "owner_id": 10,
    }
    try:
        assert packet_capture.get_status(capture_id, owner_id=11) is None
        assert packet_capture.get_packets(capture_id, owner_id=11) == []
        assert packet_capture.stop_capture(capture_id, owner_id=11)["stopped"] is False

        assert packet_capture.get_status(capture_id, owner_id=10)["status"] == "running"
        assert packet_capture.get_packets(capture_id, owner_id=10) == [{"protocol": "TCP"}]
    finally:
        packet_capture._captures.pop(capture_id, None)


def test_packet_capture_concurrency_is_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(packet_capture, "SCAPY_AVAILABLE", True)
    monkeypatch.setattr(packet_capture, "CAPTURE_DIR", str(tmp_path))
    packet_capture._captures.clear()
    for index in range(packet_capture.MAX_ACTIVE_CAPTURES):
        packet_capture._captures[f"active-{index}"] = {
            "sniffer": SimpleNamespace(running=True),
            "packets": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "interface": None,
            "owner_id": index,
        }
    try:
        result = packet_capture.start_capture(owner_id=99)
        assert result["supported"] is False
        assert "may run at once" in result["error"]
    finally:
        packet_capture._captures.clear()


def test_expired_packet_capture_records_and_files_are_pruned(monkeypatch, tmp_path):
    capture_id = "expired"
    capture_file = tmp_path / f"{capture_id}.json"
    capture_file.write_text("{}")
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    monkeypatch.setattr(packet_capture, "CAPTURE_DIR", str(tmp_path))
    packet_capture._captures[capture_id] = {
        "sniffer": SimpleNamespace(running=False),
        "packets": [],
        "started_at": old_time.isoformat(),
        "status": "stopped",
        "interface": None,
        "owner_id": 5,
    }
    try:
        packet_capture._prune_expired_captures()
        assert capture_id not in packet_capture._captures
        assert not capture_file.exists()
    finally:
        packet_capture._captures.pop(capture_id, None)
