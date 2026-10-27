from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.analytics import summarize


def test_analytics_identifies_simulated_and_real_series_points():
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            created_at=now - timedelta(minutes=2),
            health_score=95,
            latency_avg_ms=20,
            packet_loss_pct=0,
            dns_response_ms=5,
            result_json={"simulated": True},
        ),
        SimpleNamespace(
            created_at=now - timedelta(minutes=1),
            health_score=90,
            latency_avg_ms=30,
            packet_loss_pct=0,
            dns_response_ms=10,
            result_json={"simulated": False},
        ),
    ]

    result = summarize(rows, range_key="today")

    assert result["stats_source"] == "mixed"
    assert [point["simulated"] for point in result["series"]] == [True, False]
