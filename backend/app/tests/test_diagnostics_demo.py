from datetime import datetime, timezone
from types import SimpleNamespace

from app.api import diagnostics
from app.schemas.diagnostics import DiagnosisRequest


class FakeDB:
    pass


def _stored_run(result):
    return SimpleNamespace(
        id=42,
        created_at=datetime.now(timezone.utc),
        health_score=result["health_score"],
        gateway_reachable=bool(result["gateway"].get("reachable")),
        internet_reachable=bool(result["internet"].get("reachable")),
        latency_avg_ms=result["latency"].get("avg_ms"),
        packet_loss_pct=result["packet_loss"].get("loss_pct"),
        dns_response_ms=result["dns"].get("response_ms"),
        top_finding=result["findings"][0]["text"] if result.get("findings") else None,
        result_json=result,
    )


def test_full_diagnosis_demo_mode_returns_labeled_simulated_result(monkeypatch):
    monkeypatch.setattr(diagnostics, "_persist", lambda db, user, result: _stored_run(result))

    result = diagnostics.run_full_diagnosis(
        DiagnosisRequest(websites=[]),
        demo=True,
        db=FakeDB(),
        user=SimpleNamespace(id=1),
    )

    assert result.result_json["simulated"] is True
    assert result.result_json["devices"]["status"] == "skipped"


def test_full_diagnosis_real_mode_does_not_fallback_to_demo(monkeypatch):
    real_result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gateway": {"reachable": True},
        "internet": {"reachable": True},
        "latency": {"avg_ms": 12},
        "packet_loss": {"loss_pct": 0},
        "dns": {"response_ms": 4},
        "websites": [],
        "devices": {"supported": None, "devices": []},
        "health_score": 100,
        "findings": [{"text": "real measurement"}],
        "recommendations": [],
    }
    monkeypatch.setattr(diagnostics.engine, "run_full_diagnosis", lambda **kwargs: real_result.copy())
    monkeypatch.setattr(diagnostics, "_persist", lambda db, user, result: _stored_run(result))

    result = diagnostics.run_full_diagnosis(
        DiagnosisRequest(websites=[]),
        demo=False,
        db=FakeDB(),
        user=SimpleNamespace(id=1),
    )

    assert result.result_json["simulated"] is False
    assert result.result_json["findings"][0]["text"] == "real measurement"
    assert result.result_json["devices"]["status"] == "skipped"
