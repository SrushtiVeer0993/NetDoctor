from app.services import legacy_diagnostics as diagnostics


def _healthy_measurements():
    return {
        "gateway": {"reachable": True, "icmp_unavailable": False},
        "internet": {"reachable": True},
        "latency": {"avg_ms": 40},
        "packet_loss": {"loss_pct": 0},
        "dns": {"success": True, "response_ms": 20},
    }


def test_findings_include_structured_codes_and_relevant_recommendations():
    measurements = _healthy_measurements()
    measurements["latency"]["avg_ms"] = 180
    measurements["packet_loss"]["loss_pct"] = 8

    result = diagnostics.diagnose(
        **measurements,
        websites=[],
    )
    finding = next(f for f in result["findings"] if f["code"] == "unstable_connection")

    assert finding["severity"] == "warning"
    assert finding["evidence"] == "avg latency 180 ms, packet loss 8%."
    assert finding["recommendations"]
    assert set(finding["recommendations"]).issubset(
        set(diagnostics.recommend(result["findings"]))
    )


def test_gateway_icmp_silence_does_not_claim_local_failure_when_internet_is_unknown():
    result = diagnostics.diagnose(
        gateway={"reachable": False, "icmp_unavailable": True},
        internet={"reachable": False},
        latency={"avg_ms": None},
        packet_loss={"loss_pct": None},
        dns={"success": None},
        websites=[],
    )

    assert [f["code"] for f in result["findings"]] == ["connectivity_inconclusive"]
    assert result["findings"][0]["severity"] == "info"


def test_missing_measurements_are_inconclusive_not_dns_or_zero_loss_failures():
    measurements = _healthy_measurements()
    measurements["latency"] = {"avg_ms": None}
    measurements["packet_loss"] = {"loss_pct": None}
    measurements["dns"] = {"success": None, "response_ms": None}

    result = diagnostics.diagnose(**measurements, websites=[])
    score = diagnostics.calculate_health_score(
        measurements["gateway"], measurements["internet"], measurements["latency"],
        measurements["packet_loss"], measurements["dns"], [],
    )

    assert [f["code"] for f in result["findings"]] == ["measurements_inconclusive"]
    assert score["factors"]["packet_loss"] == 0
    assert score["factors"]["dns"] == 0


def test_http_error_status_is_not_reported_as_unreachable(monkeypatch):
    class Response:
        status_code = 503

    monkeypatch.setattr(diagnostics.requests, "get", lambda *args, **kwargs: Response())
    websites = diagnostics.test_websites(["https://example.test"])
    result = diagnostics.diagnose(**_healthy_measurements(), websites=websites)
    codes = [finding["code"] for finding in result["findings"]]

    assert websites[0]["reachable"] is True
    assert websites[0]["successful_request"] is False
    assert "website_http_error" in codes
    assert "websites_unavailable" not in codes


def test_http_response_proves_network_access_when_ping_target_does_not_respond(monkeypatch):
    class Response:
        status_code = 404

    monkeypatch.setattr(diagnostics.requests, "get", lambda *args, **kwargs: Response())
    websites = diagnostics.test_websites(["https://example.test/missing"])
    measurements = _healthy_measurements()
    measurements["internet"]["reachable"] = False
    result = diagnostics.diagnose(**measurements, websites=websites)
    score = diagnostics.calculate_health_score(
        measurements["gateway"], measurements["internet"], measurements["latency"],
        measurements["packet_loss"], measurements["dns"], websites,
    )
    codes = [finding["code"] for finding in result["findings"]]

    assert "internet_icmp_unavailable" in codes
    assert "connectivity_upstream" not in codes
    assert "connectivity_local" not in codes
    assert "website_http_error" in codes
    assert score["factors"]["connectivity"] == 0


def test_http_connection_failure_is_reported_as_unreachable(monkeypatch):
    def fail_request(*args, **kwargs):
        raise diagnostics.requests.ConnectionError("unavailable")

    monkeypatch.setattr(diagnostics.requests, "get", fail_request)
    websites = diagnostics.test_websites(["https://example.test"])
    result = diagnostics.diagnose(**_healthy_measurements(), websites=websites)

    assert websites[0]["reachable"] is False
    assert any(f["code"] == "websites_unavailable" for f in result["findings"])


def test_unknown_internet_status_does_not_receive_a_down_or_healthy_diagnosis():
    result = diagnostics.diagnose(
        gateway={"reachable": True},
        internet={},
        latency={"avg_ms": None},
        packet_loss={"loss_pct": None},
        dns={"success": None},
        websites=[],
    )
    score = diagnostics.calculate_health_score({}, {}, {}, {}, {}, [])

    assert result["findings"][0]["code"] == "connectivity_inconclusive"
    assert score == {"score": 50, "factors": {"connectivity": -50}}
