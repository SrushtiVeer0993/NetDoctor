"""
Alert evaluation (spec section 17).

Alerts only fire after N consecutive breaching measurements (default 3),
to avoid false alarms from a single noisy sample — and only fire once per
breach episode (not on every tick while still breaching), resetting once
the metric recovers.
"""


class ConsecutiveTracker:
    """Per-monitoring-session, in-memory breach counters. Not persisted —
    a fresh monitoring session starts with a clean slate, matching how the
    Live Monitor page is used (short, ad-hoc sessions)."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.fired: dict[str, bool] = {}

    def observe(self, metric: str, breaching: bool, required: int) -> bool:
        """Returns True exactly once per breach episode, when the
        consecutive count first reaches `required`."""
        if not breaching:
            self.counts[metric] = 0
            self.fired[metric] = False
            return False

        self.counts[metric] = self.counts.get(metric, 0) + 1
        if self.counts[metric] >= required and not self.fired.get(metric, False):
            self.fired[metric] = True
            return True
        return False

    def interrupt(self, metric: str) -> None:
        """An unknown sample breaks a streak without marking the metric recovered."""
        self.counts[metric] = 0


def evaluate_measurement(measurement: dict, user_settings, tracker: ConsecutiveTracker) -> list[dict]:
    """
    measurement: {"latency_ms": float|None, "packet_loss_pct": float|None,
                   "dns_ms": float|None, "dns_success": bool, "internet_up": bool|None}
    Returns a list of newly-fired alert dicts: {metric, current_value, baseline_value, message}.
    """
    required = user_settings.alert_consecutive_checks
    fired = []

    latency_ms = measurement.get("latency_ms")
    if latency_ms is not None:
        breaching = latency_ms > user_settings.latency_alert_ms
        if tracker.observe("latency_ms", breaching, required):
            fired.append({
                "metric": "latency_ms", "current_value": latency_ms,
                "baseline_value": user_settings.latency_alert_ms,
                "message": f"High latency detected: {latency_ms} ms (threshold {user_settings.latency_alert_ms} ms) for {required} consecutive checks.",
            })
    else:
        tracker.interrupt("latency_ms")

    packet_loss_pct = measurement.get("packet_loss_pct")
    if packet_loss_pct is not None:
        breaching = packet_loss_pct > user_settings.packet_loss_alert_pct
        if tracker.observe("packet_loss_pct", breaching, required):
            fired.append({
                "metric": "packet_loss_pct", "current_value": packet_loss_pct,
                "baseline_value": user_settings.packet_loss_alert_pct,
                "message": f"Elevated packet loss: {packet_loss_pct}% (threshold {user_settings.packet_loss_alert_pct}%) for {required} consecutive checks.",
            })
    else:
        tracker.interrupt("packet_loss_pct")

    internet_up = measurement.get("internet_up")
    if internet_up is not None:
        if tracker.observe("internet_down", not internet_up, required):
            fired.append({
                "metric": "internet_down", "current_value": 0, "baseline_value": 1,
                "message": f"Internet unreachable for {required} consecutive checks.",
            })
    else:
        tracker.interrupt("internet_down")

    dns_success = measurement.get("dns_success")
    if dns_success is None:
        tracker.interrupt("dns_failure")
    elif tracker.observe("dns_failure", not dns_success, required):
        fired.append({
            "metric": "dns_failure", "current_value": 0, "baseline_value": 1,
            "message": f"DNS resolution failing for {required} consecutive checks.",
        })

    return fired
